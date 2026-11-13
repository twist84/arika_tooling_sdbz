"""Animation preview and character clip remapping regression tests."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from arika_models import c_gltf
from arika_animation_preview import c_animation_preview, geometry_resources_shared
from arika_scene_characters import load_skinned_character, merge_character


def fixture():
    gltf=c_gltf()
    doc=gltf.m_document
    positions=gltf.array([[0,0,0],[1,0,0],[0,1,0]],'VEC3')
    indices=gltf.array([0,1,2],'SCALAR',5125)
    times=gltf.array([0.0,1.0],'SCALAR')
    positions_keys=gltf.array([[0,0,0],[2,4,6]],'VEC3')
    rotation_keys=gltf.array([[0,0,0,1],[0,0,1,0]],'VEC4')
    doc['nodes']=[dict(name='bone',translation=[1,0,0],rotation=[0,0,0,1],scale=[1,1,1]),
                  dict(name='mesh',mesh=0)]
    doc['scenes'][0]['nodes']=[0,1]
    doc['meshes']=[dict(primitives=[dict(attributes=dict(POSITION=positions),indices=indices)])]
    doc['animations']=[dict(name='Rotate and move',samplers=[
        dict(input=times,output=positions_keys,interpolation='LINEAR'),
        dict(input=times,output=rotation_keys,interpolation='LINEAR'),
    ],channels=[
        dict(sampler=0,target=dict(node=0,path='translation')),
        dict(sampler=1,target=dict(node=0,path='rotation')),
    ])]
    return gltf.to_document()


class AnimationPreviewTests(unittest.TestCase):
    def test_scrub_and_restore_without_modifying_original(self):
        doc=fixture()
        original=copy.deepcopy(doc)
        preview=c_animation_preview(doc,0)
        self.assertEqual(preview.name,'Rotate and move')
        self.assertAlmostEqual(preview.m_duration,1.0)
        preview.seek(0.5)
        posed=preview.m_document['nodes'][0]
        self.assertEqual(posed['translation'],[1.0,2.0,3.0])
        self.assertAlmostEqual(posed['rotation'][2],math.sqrt(.5),places=6)
        self.assertAlmostEqual(posed['rotation'][3],math.sqrt(.5),places=6)
        self.assertEqual(doc,original)
        preview.seek(10)
        self.assertEqual(posed['translation'],[2.0,4.0,6.0])
        preview.seek(-10)
        self.assertEqual(posed['translation'],[0.0,0.0,0.0])
        self.assertEqual(doc,original)

    def test_character_animation_remaps_targets_and_accessors(self):
        character=fixture()
        base=fixture()
        base.pop('animations')
        base['nodes'][0]['name']='existing'
        document,actor=merge_character(base,character,'Animated actor',skinned=True)
        self.assertEqual(len(document['animations']),1)
        clip=document['animations'][0]
        target=clip['channels'][0]['target']['node']
        self.assertNotEqual(target,0)
        self.assertIn(target,document['nodes'][actor]['children'])
        self.assertEqual(document['nodes'][target]['name'],'bone')
        self.assertGreater(clip['samplers'][0]['input'],character['animations'][0]['samplers'][0]['input'])
        preview=c_animation_preview(document,0)
        preview.seek(.5)
        self.assertEqual(preview.m_document['nodes'][target]['translation'],[1.0,2.0,3.0])
        self.assertEqual(document['nodes'][target]['translation'],[1,0,0])

    def test_loader_embeds_external_gltf_buffer(self):
        document=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            uri=document['buffers'][0]['uri']
            import base64
            blob=base64.b64decode(uri.split(',',1)[1])
            (directory/'geometry.bin').write_bytes(blob)
            document['buffers'][0]['uri']='geometry.bin'
            path=directory/'character.gltf'
            path.write_text(json.dumps(document),encoding='utf-8')
            loaded=load_skinned_character(path)
            self.assertTrue(loaded['buffers'][0]['uri'].startswith('data:'))
            self.assertEqual(len(loaded['animations']),1)
            preview=c_animation_preview(loaded,0)
            preview.seek(.5)
            self.assertEqual(preview.m_document['nodes'][0]['translation'],[1.0,2.0,3.0])

    def test_preview_geometry_is_shared_but_nodes_are_not(self):
        document = fixture()
        preview = c_animation_preview(document, 0)
        self.assertTrue(geometry_resources_shared(document, preview.m_document))
        self.assertTrue(geometry_resources_shared(preview.m_document, document))
        self.assertIsNot(preview.m_document['nodes'], document['nodes'])
        self.assertIs(preview.m_document['meshes'], document['meshes'])
        preview.seek(.5)
        self.assertTrue(geometry_resources_shared(document, preview.m_document))
        self.assertNotEqual(
            document['nodes'][0]['translation'],
            preview.m_document['nodes'][0]['translation'],
        )

    def test_geometry_changes_force_rebuild(self):
        document = fixture()
        preview = c_animation_preview(document, 0)
        changed = dict(preview.m_document)
        changed['meshes'] = copy.deepcopy(document['meshes'])
        self.assertFalse(geometry_resources_shared(document, changed))
        changed = dict(preview.m_document)
        changed['buffers'] = copy.deepcopy(document['buffers'])
        self.assertFalse(geometry_resources_shared(document, changed))
        changed = dict(preview.m_document)
        changed['nodes'] = copy.deepcopy(preview.m_document['nodes'])
        changed['nodes'][1]['mesh'] = 999
        self.assertFalse(geometry_resources_shared(document, changed))
        changed = dict(preview.m_document)
        changed['nodes'] = copy.deepcopy(preview.m_document['nodes'])
        changed['nodes'][0]['children'] = [1]
        self.assertFalse(geometry_resources_shared(document, changed))
        self.assertFalse(geometry_resources_shared(None, preview.m_document))

    def test_renderer_reuses_existing_instances_when_pose_changes(self):
        # Bypass GPU initialization; this regression exercises the resource
        # lifecycle branch and world-matrix update without requiring Vulkan.
        from types import SimpleNamespace
        from unittest.mock import patch
        from arika_webgpu import c_webgpu_renderer

        document = fixture()
        preview = c_animation_preview(document, 0)
        renderer = c_webgpu_renderer.__new__(c_webgpu_renderer)
        instance = dict(
            index=1, mesh=0, collision=False, matrix=None,
            bindings={}, skinned=False,
        )
        renderer.m_project = SimpleNamespace(m_document=document)
        renderer.m_meshes = {0: []}
        renderer.m_textures = []
        renderer.m_bounds = {}
        renderer.m_instances = [instance]
        renderer.m_device = object()
        renderer.m_selection_cache = {}
        renderer.m_hidden = set()
        renderer.m_dirty = False

        with patch.object(renderer, '_destroy_geometry_resources') as destroy:
            with patch.object(renderer, '_destroy_instance_resources') as release:
                preview.seek(.5)
                renderer.set_project(preview.m_project, geometry=False)
                self.assertIs(renderer.m_instances[0], instance)
                self.assertEqual(renderer.m_node_worlds[0][0][3], 1.0)
                self.assertEqual(renderer.m_node_worlds[0][1][3], 2.0)
                self.assertEqual(renderer.m_node_worlds[0][2][3], 3.0)
                renderer.set_project(SimpleNamespace(m_document=document), geometry=False)
                self.assertIs(renderer.m_instances[0], instance)
                destroy.assert_not_called()
                release.assert_not_called()

    def test_rejects_unsupported_interpolation(self):
        document=fixture()
        document['animations'][0]['samplers'][0]['interpolation']='STEP'
        with self.assertRaises(ValueError):
            c_animation_preview(document,0)


if __name__=='__main__':
    unittest.main()
