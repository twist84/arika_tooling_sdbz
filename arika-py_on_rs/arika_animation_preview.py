"""Read-only glTF animation preview built on native MOT2-style pose sampling.

Preview documents clone nodes, but share immutable mesh/buffer resources with the
source project. A pose never edits the original scene or its undo history.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace

from arika_import import c_gltf_reader
from arika_models import sample_motion_pose


def geometry_resources_shared(previous, current):
    """Whether two glTF documents can share already-uploaded GPU resources.

    Animation previews shallow-copy immutable geometry data and deep-copy only
    nodes. Arbitrary new projects must rebuild their buffers even when their
    mesh indices happen to coincide.
    """
    if previous is current:
        return True
    if previous is None or current is None:
        return False
    for key in ('meshes', 'buffers', 'bufferViews', 'accessors',
                'images', 'textures', 'samplers', 'materials', 'skins', 'scenes'):
        if previous.get(key) is not current.get(key):
            return False
    old_nodes = previous.get('nodes', [])
    new_nodes = current.get('nodes', [])
    if len(old_nodes) != len(new_nodes):
        return False
    for old, new in zip(old_nodes, new_nodes):
        if old.get('mesh') != new.get('mesh') or old.get('skin') != new.get('skin'):
            return False
        if old.get('children', []) != new.get('children', []):
            return False
    return True


class c_animation_preview:
    def __init__(self, document, animation_index):
        animations = document.get('animations', [])
        if not 0 <= animation_index < len(animations):
            raise ValueError('invalid animation index')
        self.m_animation = animations[animation_index]
        self.m_document = dict(document)
        self.m_document['nodes'] = copy.deepcopy(document['nodes'])
        self.m_project = SimpleNamespace(m_document=self.m_document)
        self.m_targets = []
        self.m_duration = 0.0
        motion_nodes = []
        # Source accessors are decoded once, never on a render tick.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'preview.gltf'
            path.write_text(json.dumps(document), encoding='utf-8')
            reader = c_gltf_reader(path)
            tracks = {}
            for channel in self.m_animation.get('channels', []):
                target = channel['target']
                index = target.get('node')
                component = target.get('path')
                if type(index) is not int or not 0 <= index < len(document['nodes']):
                    raise ValueError('animation target is outside the scene')
                if component not in ('translation', 'rotation', 'scale'):
                    raise ValueError('unsupported animation target path')
                sampler = self.m_animation['samplers'][channel['sampler']]
                if sampler.get('interpolation', 'LINEAR') != 'LINEAR':
                    raise ValueError('preview supports LINEAR animation samplers')
                times = [row[0] for row in reader.accessor(sampler['input'])]
                values = reader.accessor(sampler['output'])
                if not times or len(times) != len(values):
                    raise ValueError('invalid animation key counts')
                if not all(math.isfinite(t) and t >= 0 for t in times):
                    raise ValueError('invalid animation key time')
                if (index, component) in tracks:
                    raise ValueError('duplicate animation target')
                tracks[index, component] = dict(times=times, values=values)
                self.m_duration = max(self.m_duration, times[-1])
        for index in sorted({node for node, _ in tracks}):
            source = document['nodes'][index]
            defaults = {
                'translation': source.get('translation', [0.0, 0.0, 0.0]),
                'rotation': source.get('rotation', [0.0, 0.0, 0.0, 1.0]),
                'scale': source.get('scale', [1.0, 1.0, 1.0]),
            }
            node_tracks = {}
            for component, default in defaults.items():
                node_tracks[component] = tracks.get(
                    (index, component),
                    dict(times=[0.0], values=[list(default)]),
                )
            motion_nodes.append(dict(tracks=node_tracks))
            self.m_targets.append(index)
        self.m_motion = dict(nodes=motion_nodes)

    @property
    def name(self):
        return self.m_animation.get('name') or 'Animation'

    def seek(self, seconds):
        if not math.isfinite(seconds):
            raise ValueError('invalid preview time')
        time = max(0.0, min(float(seconds), self.m_duration))
        poses = sample_motion_pose(self.m_motion, time)
        for index, pose in zip(self.m_targets, poses):
            node = self.m_document['nodes'][index]
            for component in ('translation', 'rotation', 'scale'):
                node[component] = pose[component]
        return time
