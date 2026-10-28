#!/usr/bin/env python3
"""Super Dragon Ball Z FMDL geometry and RFSM/MOT2 animation exporters."""
import argparse
import array as _array
import base64
import fnmatch
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import arika_dat as archive


def require(condition, message):
    if not condition:
        raise ValueError(message)


def u32(data, offset):
    require(0 <= offset <= len(data) - 4, 'truncated u32')
    return struct.unpack_from('<I', data, offset)[0]


def vectors(data, offset, count):
    require(0 <= offset <= len(data) and count >= 0 and offset + count * 16 <= len(data), 'truncated vector array')
    result = [list(v) for v in struct.iter_unpack('<4f', data[offset:offset + count * 16])]
    require(all(math.isfinite(x) for v in result for x in v), 'non-finite vector')
    return result


def directory(data, magic):
    require(len(data) >= 32 and data[:4] == magic, 'expected ' + magic.decode())
    require(u32(data, 4) == len(data), 'chunk size mismatch')
    count = u32(data, 8)
    require(32 + count * 4 <= len(data), 'truncated chunk directory')
    offsets = list(struct.unpack_from('<' + 'I' * count, data, 32))
    require(not offsets or offsets[0] == 32 + count * 4, 'unexpected directory start')
    result = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < count else len(data)
        require(start + 32 <= end <= len(data), 'invalid child extent')
        require(u32(data, start + 4) == end - start, 'child size mismatch')
        result.append(data[start:end])
    return result


def quaternion(euler):
    # Verified against the half-angle formula at EE 0x1A0244..0x1A0300.
    x, y, z = [math.radians(v) * .5 for v in euler]
    sx, sy, sz = math.sin(x), math.sin(y), math.sin(z)
    cx, cy, cz = math.cos(x), math.cos(y), math.cos(z)
    return [sx * cy * cz - cx * sy * sz, cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz, cx * cy * cz + sx * sy * sz]


def euler_radians(rotation):
    """Convert a glTF/Arika quaternion to XYZ Euler angles in radians."""
    x, y, z, w = normalized(rotation)
    sin_x = 2 * (w * x + y * z)
    cos_x = 1 - 2 * (x * x + y * y)
    angle_x = math.atan2(sin_x, cos_x)
    sin_y = 2 * (w * y - z * x)
    angle_y = math.asin(max(-1.0, min(1.0, sin_y)))
    sin_z = 2 * (w * z + x * y)
    cos_z = 1 - 2 * (y * y + z * z)
    angle_z = math.atan2(sin_z, cos_z)
    return [angle_x, angle_y, angle_z]


def normalized(v):
    length = math.sqrt(sum(x * x for x in v))
    require(length > 1e-12, 'zero length vector/quaternion')
    return [x / length for x in v]


def local_matrix(node):
    x, y, z, w = node['rotation']
    sx, sy, sz = node['scale']
    tx, ty, tz = node['translation']
    return [[(1 - 2 * (y*y + z*z))*sx, 2*(x*y - z*w)*sy, 2*(x*z + y*w)*sz, tx],
        [2*(x*y + z*w)*sx, (1 - 2*(x*x + z*z))*sy, 2*(y*z - x*w)*sz, ty],
        [2*(x*z - y*w)*sx, 2*(y*z + x*w)*sy, (1 - 2*(x*x + y*y))*sz, tz], [0, 0, 0, 1]]


def identity():
    return [[int(r == c) for c in range(4)] for r in range(4)]


def multiply(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def inverse(a):
    rows = [list(a[r]) + identity()[r] for r in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(rows[r][col]))
        require(abs(rows[pivot][col]) > 1e-12, 'singular bind matrix')
        rows[pivot], rows[col] = rows[col], rows[pivot]
        divisor = rows[col][col]
        rows[col] = [v / divisor for v in rows[col]]
        for r in range(4):
            if r != col:
                factor = rows[r][col]
                rows[r] = [v - factor*w for v, w in zip(rows[r], rows[col])]
    return [r[4:] for r in rows]


def quaternion_from_matrix(matrix):
    """Extract a quaternion from a 3x3 rotation matrix (rows)."""
    from arika_gizmo import quaternion_from_matrix as _qfm
    return _qfm(matrix)

    result = [None] * len(nodes)
    visiting = set()
    def visit(i):
        require(i not in visiting, 'skeleton parent cycle')
        if result[i] is not None:
            return result[i]
        visiting.add(i)
        node = nodes[i]
        parent = identity() if node['parent'] < 0 else visit(node['parent'])
        result[i] = multiply(parent, local_matrix(node))
        visiting.remove(i)
        return result[i]
    for i in range(len(nodes)):
        visit(i)
    return result


def world_matrices(nodes):
    result=[None]*len(nodes)
    visiting=set()
    def visit(i):
        require(i not in visiting,'skeleton parent cycle')
        if result[i] is not None:return result[i]
        visiting.add(i)
        node=nodes[i]
        parent=identity() if node['parent']<0 else visit(node['parent'])
        result[i]=multiply(parent,local_matrix(node))
        visiting.remove(i)
        return result[i]
    for i in range(len(nodes)):visit(i)
    return result


def string_list(data, count):
    parts = data[32:].split(b'\0')
    require(len(parts) >= count, 'truncated name list')
    return [s.decode('cp932') for s in parts[:count]]


def skeleton(chunks):
    if 'DHIE' not in chunks:
        return []
    children = directory(chunks['DHIE'], b'DHIE')
    hierarchy = next((c for c in children if c[:4] == b'XHIE'), None)
    require(hierarchy is not None, 'DHIE has no XHIE')
    count = u32(hierarchy, 8)
    require(len(hierarchy) == 32 + count * 64, 'unexpected XHIE record size')
    names = string_list(chunks['XNON'], count)
    nodes = []
    for i in range(count):
        offset = 32 + i * 64
        index, parent, child, sibling = struct.unpack_from('<4i', hierarchy, offset)
        require(index == i and all(-1 <= j < count for j in (parent, child, sibling)), 'invalid skeleton links')
        s, r, t = vectors(hierarchy, offset + 16, 3)
        nodes.append(dict(index=i, name=names[i], parent=parent, child=child, sibling=sibling,
            scale=s[:3], euler_degrees=r[:3], rotation=quaternion(r[:3]), translation=t[:3]))
    world_matrices(nodes)
    return nodes


def mesh_geometry(data, palette, materials, bone_count):
    require(data[:4] == b'XMOD' and len(data) >= 0x1B0, 'invalid XMOD')
    flags = u32(data, 12)
    require(flags in (0, 1, 2, 3, 4, 6, 11), 'unsupported XMOD flags')
    skin = bool(flags & 2) and not flags & 8
    morph = bool(flags & 8)
    colored = bool(flags & 4)
    stride = 3 + 2 * bool(flags & 2) + colored
    vertices, primitives = [], []
    dma = 0x1A0
    material_index = 0
    while dma < len(data):
        tag = u32(data, dma)
        require(tag >> 28 == 6 and u32(data, dma + 4) == 0, 'unsupported DMA tag')
        end = dma + 16 + (tag & 0xFFFF) * 16
        require(end <= len(data) and material_index < len(materials), 'invalid DMA/material extent')
        at = dma + 16
        faces = []
        while at < end:
            word = u32(data, at)
            command = word >> 24 & 127
            at += 4
            if command in (0, 1, 0x17):
                continue
            require(command == 0x6C, 'unsupported VIF command 0x%02X' % command)
            count = (word >> 16 & 255) or 256
            payload_end = at + count * 16
            require(payload_end <= end and count >= 2, 'truncated VIF UNPACK')
            n = u32(data, at + 16) & 32767
            require(n > 0 and count == 2 + n * stride, 'unexpected vertex packet layout')
            for i in range(n):
                off = at + 32 + i * stride * 16
                values = vectors(data, off, stride)
                pos, normal = values[:2]
                adc = u32(data, off + 12)
                uv = values[3 if colored else 2]
                vertex = dict(position=pos[:3], normal=normal[:3], uv=uv[:2], adc=adc,
                    orientation=normal[3])
                if colored:
                    vertex['color_ps2'] = values[2]
                if skin:
                    joint_at = off + (4 if colored else 3) * 16
                    raw_joints = struct.unpack_from('<4I', data, joint_at)
                    weights = values[-1]
                    require(all(math.isfinite(w) for w in weights), 'invalid skin weights')
                    joints = []
                    for raw, weight in zip(raw_joints, weights):
                        if weight != 0:
                            require(raw % 4 == 0 and raw // 4 < 32, 'invalid palette address')
                            joint = palette[raw // 4]
                            require(0 <= joint < bone_count, 'skin references missing bone')
                        else:
                            joint = 0
                        joints.append(joint)
                    require(abs(sum(weights) - 1) < 1e-4, 'skin weights do not sum to one')
                    vertex.update(joints=joints, weights=weights)
                if morph:
                    vertex.update(morph_position=values[-2][:3], morph_normal=values[-1][:3])
                vertices.append(vertex)
                if not adc & 0x8000:
                    require(len(vertices) >= 3, 'triangle before two preceding vertices')
                    # The authored normal.w records the source strip orientation.
                    face = [len(vertices) - 3, len(vertices) - 2, len(vertices) - 1]
                    if normal[3] < 0:
                        face[0], face[1] = face[1], face[0]
                    faces.append(face)
            at = payload_end
        primitives.append(dict(material=materials[material_index], triangles=faces))
        dma = end
        material_index += 1
    require(material_index == len(materials), 'DMA/material count mismatch')
    require(len(vertices) == u32(data, 48), 'XMOD vertex count mismatch')
    require(sum(len(p['triangles']) for p in primitives) == u32(data, 52), 'XMOD triangle count mismatch')
    return dict(flags=flags, skinned=skin, morph=morph, palette=palette, vertices=vertices, primitives=primitives)


def parse_model(data):
    meta = archive.container(data)
    require(meta['magic'] == 'FMDL', 'expected FMDL')
    chunks = {c['magic']:data[c['offset']:c['offset'] + c['size']] for c in meta['chunks']}
    nodes = skeleton(chunks)
    mesh_data = directory(chunks['DMOD'], b'DMOD')
    names = string_list(chunks['XMON'], len(mesh_data))
    mat_children = directory(chunks['DMAT'], b'DMAT')
    material_data = next(c for c in mat_children if c[:4] == b'XMAT')
    assignments = next(c for c in mat_children if c[:4] == b'XMAL')
    material_count = u32(material_data, 8)
    require(len(material_data) == 32 + material_count * 48, 'unexpected material size')
    require(len(assignments) == 32 + len(mesh_data) * 128, 'unexpected material assignment size')
    materials = []
    for i in range(material_count):
        off = 32 + i * 48
        materials.append(dict(index=i, color_a=vectors(material_data, off, 1)[0],
            color_b=vectors(material_data, off + 16, 1)[0], texture=struct.unpack_from('<i', material_data, off + 32)[0]))
    meshes = []
    for i, child in enumerate(mesh_data):
        palette = list(struct.unpack_from('<32i', chunks['XMTX'], 32 + i * 128)) if 'XMTX' in chunks else [-1] * 32
        row = list(struct.unpack_from('<32i', assignments, 32 + i * 128))
        assigned = [v for v in row if v >= 0]
        require(all(v < material_count for v in assigned), 'material out of range')
        mesh = mesh_geometry(child, palette, assigned, len(nodes))
        mesh.update(index=i, name=names[i])
        meshes.append(mesh)
    return dict(format='FMDL', source_sha256=hashlib.sha256(data).hexdigest(), nodes=nodes, materials=materials, meshes=meshes)


def parse_motion(data):
    require(len(data) >= 64 and data[:4] == b'MOT2' and u32(data, 4) == len(data), 'invalid MOT2')
    fps, = struct.unpack_from('<f', data, 8)
    frame_count, node_count, constants, channel_count = struct.unpack_from('<4H', data, 12)
    require(math.isfinite(fps) and fps > 0 and frame_count > 0, 'invalid motion timing')
    table, pool = struct.unpack_from('<II', data, 20)
    require(pool + constants * 16 == table and table + node_count * 8 <= len(data), 'invalid MOT2 table')
    constant_values = vectors(data, pool, constants)
    arrays = []
    for offset in (28, 40, 52):
        channels, keys, pointer, time_pointer = struct.unpack_from('<HHII', data, offset)
        times, values = [], []
        if channels:
            require(keys > 0 and time_pointer + keys * 4 <= len(data), 'invalid key times')
            times = list(struct.unpack_from('<' + 'f' * keys, data, time_pointer))
            require(all(math.isfinite(t) and t >= 0 for t in times) and all(b > a for a, b in zip(times, times[1:])), 'non-increasing key times')
            values = vectors(data, pointer, channels * keys)
        arrays.append(dict(channels=channels, keys=keys, times=times, values=values))
    require(sum(a['channels'] for a in arrays) == channel_count, 'motion channel count mismatch')
    nodes = []
    observed = [set(), set(), set()]
    for i in range(node_count):
        flags, *indices = struct.unpack_from('<4H', data, table + i * 8)
        require(flags <= 7, 'unknown MOT2 node flags')
        node = dict(index=i, flags=flags, indices=indices, tracks={})
        for typ, path in enumerate(('translation', 'rotation', 'scale')):
            array, index = arrays[typ], indices[typ]
            animated = bool(flags & (1 << typ))
            if animated:
                count = array['keys']
                require(count > 0 and index % count == 0 and index // count < array['channels'], 'motion track index out of range')
                times = array['times']
                values = array['values'][index:index + count]
                observed[typ].add(index // count)
                channel = index // count
            else:
                require(index < constants, 'constant vector index out of range')
                times, values, channel = [0.0], [constant_values[index]], None
            values = [v[:3] if typ != 1 else list(v) for v in values]
            if typ == 1:
                require(all(abs(sum(x*x for x in v) - 1) < .01 for v in values), 'non-unit rotation quaternion')
            node['tracks'][path] = dict(animated=animated, channel=channel, times=times, values=values)
        nodes.append(node)
    require(all(len(observed[i]) == arrays[i]['channels'] for i in range(3)), 'missing/duplicate motion channels')
    return dict(format='MOT2', source_sha256=hashlib.sha256(data).hexdigest(), fps=fps, frame_count=frame_count, duration=frame_count / fps,
        last_frame_time=(frame_count - 1) / fps, constant_vector_count=constants, constant_vectors=constant_values,
        channel_counts=[v['channels'] for v in arrays], nodes=nodes)


def parse_motions(data):
    shared = archive.motion_archive(data)
    result = []
    for i, entry in enumerate(shared['motions']):
        motion = parse_motion(data[entry['offset']:entry['offset'] + entry['size']])
        unknown, forward, reverse = struct.unpack_from('<III', data, shared['bindings_offset'] + i * 12)
        require(unknown == 0, 'unsupported RFSM binding header')
        total = sum(motion['channel_counts'])
        require(forward + total * 2 <= len(data) and reverse + len(shared['bones']) * 2 <= len(data), 'truncated RFSM binding arrays')
        fwd = list(struct.unpack_from('<' + 'H' * total, data, forward))
        rev = list(struct.unpack_from('<' + 'h' * len(shared['bones']), data, reverse))
        require(all(0 <= v < len(shared['bones']) for v in fwd), 'invalid forward binding')
        for bone, node in zip(shared['bones'], rev):
            require(-1 <= node < len(motion['nodes']), 'invalid reverse binding')
            if node >= 0:
                motion['nodes'][node]['name'] = bone['name']
        for node in motion['nodes']:
            for typ, path in enumerate(('translation', 'rotation', 'scale')):
                track = node['tracks'][path]
                if track['animated']:
                    bone_index = fwd[sum(motion['channel_counts'][:typ]) + track['channel']]
                    require(rev[bone_index] == node['index'], 'forward/reverse binding mismatch')
        motion.update(name=entry['name'], package_index=i, forward_bone_bindings=fwd, reverse_node_bindings=rev)
        result.append(motion)
    return dict(format='RFSM/MOT2', bones=shared['bones'], motions=result)


def selected_meshes(model, patterns):
    meshes = [m for m in model['meshes'] if not patterns or any(fnmatch.fnmatchcase(m['name'], p) for p in patterns)]
    require(bool(meshes), 'no meshes matched')
    return meshes


def export_obj(model, output, patterns=()):
    worlds = world_matrices(model['nodes'])
    lines = ['# Super Dragon Ball Z: static authored bind pose; OBJ does not preserve skin/animation.']
    offset = 1
    for mesh in selected_meshes(model, patterns):
        lines.append('o ' + mesh['name'].replace(' ', '_'))
        joint = mesh['palette'][0]
        transform = worlds[joint] if not mesh['skinned'] and 0 <= joint < len(worlds) else identity()
        normal_transform = inverse(transform)
        for v in mesh['vertices']:
            p = [sum(transform[r][c] * (v['position'] + [1])[c] for c in range(4)) for r in range(3)]
            lines.append('v ' + ' '.join('%.9g' % x for x in p))
        for v in mesh['vertices']:
            lines.append('vt %.9g %.9g' % (v['uv'][0], 1-v['uv'][1]))
        for v in mesh['vertices']:
            n = [sum(normal_transform[c][r] * v['normal'][c] for c in range(3)) for r in range(3)]
            length = math.sqrt(sum(x*x for x in n))
            n = [x / length for x in n] if length else [0, 1, 0]
            lines.append('vn ' + ' '.join('%.9g' % x for x in n))
        for part in mesh['primitives']:
            lines.append('g %s_material_%d' % (mesh['name'].replace(' ', '_'), part['material']))
            for face in part['triangles']:
                lines.append('f ' + ' '.join('%d/%d/%d' % ((offset + index,) * 3) for index in face))
        offset += len(mesh['vertices'])
    Path(output).write_text('\n'.join(lines) + '\n', encoding='utf-8')


class c_gltf:
    def __init__(self):
        self.m_blob = bytearray()
        self.m_document = dict(asset=dict(version='2.0', generator='arika_models.py'), scene=0,
            scenes=[dict(nodes=[])], nodes=[], meshes=[], materials=[], accessors=[], bufferViews=[])

    def array(self, values, kind, component=5126, bounds=False):
        width = dict(SCALAR=1, VEC2=2, VEC3=3, VEC4=4, MAT4=16)[kind]
        values = [[v] for v in values] if width == 1 else values
        require(bool(values) and all(len(v) == width for v in values), 'invalid glTF array')
        while len(self.m_blob) % 4:
            self.m_blob.append(0)
        start = len(self.m_blob)
        fmt = {5126:'f', 5125:'I', 5123:'H'}[component]
        typecode = {5126:'f', 5125:'I', 5123:'H'}[component]
        flat = [value for row in values for value in row]
        packed = _array.array(typecode, flat)
        expected_itemsize = {5126:4, 5125:4, 5123:2}[component]
        if packed.itemsize == expected_itemsize:
            if sys.byteorder != 'little':
                packed.byteswap()
            self.m_blob.extend(memoryview(packed).cast('B'))
        else:
            for row in values:
                self.m_blob.extend(struct.pack('<' + fmt * width, *row))
        doc = self.m_document
        view = len(doc['bufferViews'])
        doc['bufferViews'].append(dict(buffer=0, byteOffset=start, byteLength=len(self.m_blob)-start))
        accessor = dict(bufferView=view, componentType=component, count=len(values), type=kind)
        if bounds:
            accessor.update(min=[min(v[i] for v in values) for i in range(width)], max=[max(v[i] for v in values) for i in range(width)])
        doc['accessors'].append(accessor)
        return len(doc['accessors'])-1

    def to_document(self):
        """Return the JSON document with its binary buffer embedded once."""
        self.m_document['buffers'] = [dict(byteLength=len(self.m_blob), uri='data:application/octet-stream;base64,' + base64.b64encode(self.m_blob).decode())]
        return self.m_document

    def save(self, output):
        Path(output).write_text(json.dumps(self.to_document(), ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')


def build_gltf(model, motions=(), patterns=(), texture_path=None, clamp_skin_weights=False):
    """Build a glTF in memory; callers can save it or compose it into a stage."""
    gltf = c_gltf()
    doc = gltf.m_document
    doc['extras'] = dict(source_sha256=model.get('source_sha256'), note='All authored mesh variants are included unless --mesh filters them. Native model units; authored bind pose. PS2 shader and variant-selection logic are not reproduced.')
    doc['nodes'] = [dict(name=n['name'], translation=n['translation'], rotation=n['rotation'], scale=n['scale']) for n in model['nodes']]
    for i, n in enumerate(model['nodes']):
        if n['parent'] < 0:
            doc['scenes'][0]['nodes'].append(i)
        else:
            doc['nodes'][n['parent']].setdefault('children', []).append(i)
    root_index = len(doc['nodes'])
    roots = doc['scenes'][0]['nodes']
    doc['nodes'].append(dict(name='model_root', children=roots))
    doc['scenes'][0]['nodes'] = [root_index]
    texture_count = 0
    if texture_path:
        # Read the FPIX archive once and decode only embedded XPIX/TIM2 chunks.
        # The old path split every chunk to a temporary directory, wrote each
        # TIM2 image again as PNG, then read those PNGs back into the glTF JSON.
        data = Path(texture_path).read_bytes()
        metadata = archive.container(data)
        require(metadata['magic'] == 'FPIX', 'texture file must be FPIX')
        doc['images'], doc['textures'] = [], []
        doc['samplers'] = [dict(magFilter=9729, minFilter=9729, wrapS=10497, wrapT=10497)]
        for chunk in metadata['chunks']:
            if chunk['magic'] != 'XPIX':
                continue
            start = chunk['offset']
            body = data[start:start + chunk['size']]
            if len(body) < 36 or body[32:36] != b'TIM2':
                continue
            png = archive.tim2_png_bytes(body[32:])
            doc['images'].append(dict(uri='data:image/png;base64,' + base64.b64encode(png).decode()))
            doc['textures'].append(dict(source=texture_count, sampler=0))
            texture_count += 1
    for material in model['materials']:
        pbr = dict(baseColorFactor=[1, 1, 1, 1], metallicFactor=0, roughnessFactor=1)
        if 0 <= material['texture'] < texture_count:
            pbr['baseColorTexture'] = dict(index=material['texture'])
        doc['materials'].append(dict(name='material_%d' % material['index'], pbrMetallicRoughness=pbr,
            doubleSided=True, alphaMode='MASK', alphaCutoff=.5, extras=material))
    worlds = world_matrices(model['nodes'])
    if worlds:
        matrices = [inverse(m) for m in worlds]
        ibm = gltf.array([[m[r][c] for c in range(4) for r in range(4)] for m in matrices], 'MAT4')
        doc['skins'] = [dict(name='authored_skeleton', inverseBindMatrices=ibm, joints=list(range(len(worlds))), skeleton=root_index)]
    for mesh in selected_meshes(model, patterns):
        vertices = mesh['vertices']
        attributes = dict(_ARIKA_VERTEX=gltf.array(list(range(len(vertices))), 'SCALAR'), POSITION=gltf.array([v['position'] for v in vertices], 'VEC3', bounds=True),
            NORMAL=gltf.array([normalized(v['normal']) if any(v['normal']) else [0,1,0] for v in vertices], 'VEC3'),
            TEXCOORD_0=gltf.array([v['uv'] for v in vertices], 'VEC2'))
        if vertices and 'color_ps2' in vertices[0]:
            attributes['COLOR_0'] = gltf.array([[max(0, min(1, c/128)) for c in v['color_ps2']] for v in vertices], 'VEC4')
        if mesh['skinned']:
            has_negative = any(w < 0 for v in vertices for w in v['weights'])
            require(not has_negative or clamp_skin_weights, 'negative authored skin weights require --clamp-skin-weights for glTF; JSON preserves them exactly')
            weights = [[max(0, w) for w in v['weights']] for v in vertices]
            attributes['JOINTS_0'] = gltf.array([[joint if weight > 0 else 0 for joint, weight in zip(v['joints'], row)] for v, row in zip(vertices, weights)], 'VEC4', 5123)
            attributes['WEIGHTS_0'] = gltf.array([[w/sum(row) for w in row] for row in weights], 'VEC4')
        targets = []
        if mesh['morph']:
            targets = [dict(POSITION=gltf.array([[v['morph_position'][i]-v['position'][i] for i in range(3)] for v in vertices], 'VEC3', bounds=True),
                NORMAL=gltf.array([[v['morph_normal'][i]-v['normal'][i] for i in range(3)] for v in vertices], 'VEC3'))]
        primitives = []
        for part in mesh['primitives']:
            if not part['triangles']:
                continue
            primitive = dict(attributes=attributes, indices=gltf.array([i for face in part['triangles'] for i in face], 'SCALAR', 5125), material=part['material'], mode=4)
            if targets:
                primitive['targets'] = targets
            primitives.append(primitive)
        if not primitives:
            continue
        gltf_mesh = dict(name=mesh['name'], primitives=primitives, extras=dict(source_index=mesh['index'], flags=mesh['flags']))
        if mesh['skinned'] and has_negative:
            gltf_mesh['extras']['negative_skin_weights_clamped'] = True
            print('Warning: clamped negative skin weights in ' + mesh['name'])
        if targets:
            gltf_mesh['weights'] = [mesh.get('default_morph_weight',0.0)]
        mesh_index = len(doc['meshes'])
        doc['meshes'].append(gltf_mesh)
        node = dict(name=mesh['name'] + '_geometry', mesh=mesh_index)
        if mesh['skinned']:
            node['skin'] = 0
        node_index = len(doc['nodes'])
        doc['nodes'].append(node)
        parent = mesh['palette'][0]
        if not mesh['skinned'] and 0 <= parent < len(model['nodes']):
            doc['nodes'][parent].setdefault('children', []).append(node_index)
        elif mesh['skinned']:
            doc['scenes'][0]['nodes'].append(node_index)
        else:
            doc['nodes'][root_index]['children'].append(node_index)
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            for accessor in primitive['attributes'].values():
                doc['bufferViews'][doc['accessors'][accessor]['bufferView']]['target'] = 34962
            doc['bufferViews'][doc['accessors'][primitive['indices']]['bufferView']]['target'] = 34963
            for target in primitive.get('targets', []):
                for accessor in target.values():
                    doc['bufferViews'][doc['accessors'][accessor]['bufferView']]['target'] = 34962
    by_name = {n['name']:i for i, n in enumerate(model['nodes'])}
    animations = []
    for motion in motions:
        animation = dict(name=motion['name'], channels=[], samplers=[], extras=dict(fps=motion['fps'], frame_count=motion['frame_count'], source_mot2_sha256=motion.get('source_sha256')))
        missing = []
        for source in motion['nodes']:
            name = source.get('name')
            if name is None:
                continue
            if name not in by_name:
                missing.append(name)
                continue
            for path, track in source['tracks'].items():
                times, values = list(track['times']), list(track['values'])
                if path == 'rotation':
                    values = [normalized(v) for v in values]
                    for k in range(1, len(values)):
                        if sum(a*b for a, b in zip(values[k-1], values[k])) < 0:
                            values[k] = [-v for v in values[k]]
                # Hold through the last authored frame when a track has only a constant/shorter span.
                if times[-1] < motion['last_frame_time'] - 1e-5:
                    times.append(motion['last_frame_time'])
                    values.append(values[-1])
                sampler = len(animation['samplers'])
                animation['samplers'].append(dict(input=gltf.array(times, 'SCALAR', bounds=True), output=gltf.array(values, 'VEC4' if path=='rotation' else 'VEC3'), interpolation='LINEAR'))
                animation['channels'].append(dict(sampler=sampler, target=dict(node=by_name[name], path=path)))
        if missing:
            animation['extras']['unmatched_bone_names'] = missing
        if animation['channels']:
            animations.append(animation)
    if animations:
        doc['animations'] = animations
    return gltf


def export_gltf(model, output, motions=(), patterns=(), texture_path=None, clamp_skin_weights=False):
    require(not texture_path or Path(output).resolve() != Path(texture_path).resolve(), 'output must differ from texture input')
    build_gltf(model, motions, patterns, texture_path, clamp_skin_weights).save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('model-json', 'model-obj', 'model-gltf', 'motion-json'):
        p = sub.add_parser(command)
        p.add_argument('input')
        p.add_argument('output')
        if command in ('model-obj', 'model-gltf'):
            p.add_argument('--mesh', action='append', default=[], help='mesh name/glob; repeat to include several')
        if command == 'model-gltf':
            p.add_argument('--motion', action='append', default=[], help='RFSM .pmt package; repeat for more packages')
            p.add_argument('--motion-index', type=int, action='append', help='package motion index; default all')
            p.add_argument('--clamp-skin-weights', action='store_true', help='allow glTF approximation for assets with negative skin weights')
            p.add_argument('--textures', help='FPIX file; default adjacent model basename .pix if present')
    args = parser.parse_args()
    try:
        require(Path(args.input).resolve() != Path(args.output).resolve(), 'output must differ from input')
        data = Path(args.input).read_bytes()
        if args.command == 'motion-json':
            result = parse_motions(data) if data[:4] == b'RFSM' else parse_motion(data)
            result['source_sha256'] = hashlib.sha256(data).hexdigest()
            Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        else:
            model = parse_model(data)
            if args.command == 'model-json':
                Path(args.output).write_text(json.dumps(model, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            elif args.command == 'model-obj':
                export_obj(model, args.output, args.mesh)
            else:
                motions = []
                require(args.motion_index is None or args.motion, '--motion-index requires --motion')
                for path in args.motion:
                    require(Path(path).resolve() != Path(args.output).resolve(), 'output must differ from motion input')
                    package = parse_motions(Path(path).read_bytes())
                    require(args.motion_index is None or all(0 <= i < len(package['motions']) for i in args.motion_index), 'motion index out of range')
                    for motion in package['motions']:
                        if args.motion_index is None or motion['package_index'] in args.motion_index:
                            motions.append(motion)
                texture_path = args.textures
                if texture_path is None and Path(args.input).with_suffix('.pix').exists():
                    texture_path = Path(args.input).with_suffix('.pix')
                export_gltf(model, args.output, motions, args.mesh, texture_path, args.clamp_skin_weights)
        print('Wrote ' + args.output)
    except (OSError, ValueError, struct.error, StopIteration) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
