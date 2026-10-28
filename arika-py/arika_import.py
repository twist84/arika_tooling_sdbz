#!/usr/bin/env python3
"""Import fixed-topology model edits and existing animation-track edits."""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
from urllib.parse import unquote
import arika_models as models

require = models.require
u32 = models.u32


def floats(values, count):
    require(isinstance(values, (list, tuple)) and len(values) == count, 'incorrect float vector length')
    require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in values), 'non-finite float edit')
    try:
        return struct.pack('<' + 'f' * count, *values)
    except (OverflowError, struct.error):
        raise ValueError('float edit is outside float32 range')


def patch_floats(data, offset, values):
    packed = floats(values, len(values))
    # Preserve original signed zeros for unchanged numeric values.
    original = struct.unpack_from('<' + 'f' * len(values), data, offset)
    if list(original) != list(values):
        data[offset:offset + len(packed)] = packed


def children_with_offsets(data, base, directory_magic):
    size = u32(data, base + 4)
    chunks = models.directory(data[base:base + size], directory_magic)
    count = u32(data, base + 8)
    offsets = struct.unpack_from('<' + 'I' * count, data, base + 32)
    return [(base + off, chunk) for off, chunk in zip(offsets, chunks)]


def model_layout(data):
    meta = models.archive.container(data)
    top = {c['magic']:c for c in meta['chunks']}
    meshes = children_with_offsets(data, top['DMOD']['offset'], b'DMOD')
    hierarchy = None
    if 'DHIE' in top:
        hierarchy = next(off for off, chunk in children_with_offsets(data, top['DHIE']['offset'], b'DHIE') if chunk[:4] == b'XHIE')
    materials = next(off for off, chunk in children_with_offsets(data, top['DMAT']['offset'], b'DMAT') if chunk[:4] == b'XMAT')
    return top, meshes, hierarchy, materials


def vertex_offsets(chunk):
    flags = u32(chunk, 12)
    stride = 3 + 2 * bool(flags & 2) + bool(flags & 4)
    dma = 0x1A0
    result = []
    while dma < len(chunk):
        end = dma + 16 + (u32(chunk, dma) & 65535) * 16
        at = dma + 16
        while at < end:
            command = u32(chunk, at)
            at += 4
            if command >> 24 & 127 != 0x6C:
                continue
            count = (command >> 16 & 255) or 256
            n = u32(chunk, at + 16) & 32767
            result.extend(at + 32 + i * stride * 16 for i in range(n))
            at += count * 16
        dma = end
    return result


def check_source(data, edited):
    digest = edited.get('source_sha256')
    require(digest is None or digest == hashlib.sha256(data).hexdigest(), 'JSON was exported from a different source file')


def model_from_json(original, edited):
    source = models.parse_model(original)
    check_source(original, edited)
    require(edited.get('format') == 'FMDL', 'expected model-json data')
    for field in ('nodes', 'meshes', 'materials'):
        require(len(edited[field]) == len(source[field]), 'cannot add/remove ' + field)
    output = bytearray(original)
    top, mesh_chunks, hierarchy, materials = model_layout(original)
    for before, after in zip(source['nodes'], edited['nodes']):
        for key in ('index', 'name', 'parent', 'child', 'sibling'):
            require(after[key] == before[key], 'skeleton links/names cannot change')
        rotation = after['euler_degrees']
        if after['rotation'] != before['rotation']:
            require(rotation == before['euler_degrees'], 'edit Euler angles or quaternion, not both')
            x,y,z,w = models.normalized(after['rotation'])
            rotation = [math.degrees(math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))),
                math.degrees(math.asin(max(-1,min(1,2*(w*y-z*x))))),
                math.degrees(math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))]
        floats(after['scale'],3);floats(rotation,3);floats(after['translation'],3)
        at = hierarchy + 32 + before['index'] * 64
        patch_floats(output, at + 16, after['scale'])
        patch_floats(output, at + 32, rotation)
        patch_floats(output, at + 48, after['translation'])
    for before, after in zip(source['materials'], edited['materials']):
        require(before['index'] == after['index'], 'material order cannot change')
        at = materials + 32 + before['index'] * 48
        floats(after['color_a'],4);floats(after['color_b'],4)
        patch_floats(output, at, after['color_a'])
        patch_floats(output, at + 16, after['color_b'])
        texture = after['texture']
        require(isinstance(texture, int) and -1 <= texture < u32(original, top['XTEX']['offset'] + 8), 'texture index outside XTEX')
        struct.pack_into('<i', output, at + 32, texture)
    for before, after, (base, chunk) in zip(source['meshes'], edited['meshes'], mesh_chunks):
        for key in ('index', 'name', 'flags', 'skinned', 'morph', 'primitives', 'palette'):
            require(after[key] == before[key], 'mesh structure/topology cannot change: ' + key)
        require(len(after['vertices']) == len(before['vertices']), 'vertex count cannot change')
        offsets = vertex_offsets(chunk)
        palette = list(before['palette'])
        geometry_changed = False
        for bv, av, local in zip(before['vertices'], after['vertices'], offsets):
            require(av['adc'] == bv['adc'] and av['orientation'] == bv['orientation'], 'strip controls cannot change')
            at = base + local
            colored = bool(before['flags'] & 4)
            for key, off, count in [('position',0,3),('normal',16,3),('uv',48 if colored else 32,2)]:
                require(len(av[key]) == count, 'invalid ' + key)
                patch_floats(output, at + off, av[key])
            geometry_changed |= av['position'] != bv['position']
            if colored:
                floats(av['color_ps2'],4)
                patch_floats(output, at + 32, av['color_ps2'])
            if before['morph']:
                floats(av['morph_position'],3);floats(av['morph_normal'],3)
                patch_floats(output, at + 48, av['morph_position'])
                patch_floats(output, at + 64, av['morph_normal'])
                geometry_changed |= av['morph_position'] != bv['morph_position']
            if before['skinned']:
                weights = av['weights']
                floats(weights, 4)
                require(abs(sum(weights)-1) < 1e-4, 'skin weights must sum to one')
                joints = av['joints']
                require(len(joints)==4 and all(isinstance(j,int) and 0 <= j < len(source['nodes']) for j in joints), 'invalid joint indices')
                joint_at = at + (64 if colored else 48)
                raw = list(struct.unpack_from('<4I', output, joint_at))
                for slot, (joint, weight) in enumerate(zip(joints, weights)):
                    if weight != 0:
                        if joint not in palette:
                            require(-1 in palette, 'mesh palette is full (32 bones)')
                            palette[palette.index(-1)] = joint
                        raw[slot] = palette.index(joint) * 4
                struct.pack_into('<4I', output, joint_at, *raw)
                patch_floats(output, joint_at + 16, weights)
        if palette != before['palette']:
            require('XMTX' in top, 'model has no matrix palette chunk')
            struct.pack_into('<32i', output, top['XMTX']['offset'] + 32 + before['index']*128, *palette)
            mask = sum(1 << i for i,v in enumerate(palette) if v >= 0)
            struct.pack_into('<I', output, base + 60, mask)
        if geometry_changed:
            points = [v['position'] for v in after['vertices']]
            if before['morph']:
                points += [v['morph_position'] for v in after['vertices']]
            center = [(min(p[i] for p in points)+max(p[i] for p in points))*.5 for i in range(3)]
            radius = max(math.sqrt(sum((p[i]-center[i])**2 for i in range(3))) for p in points)
            require('XCUD' in top, 'cannot update culling sphere without XCUD')
            patch_floats(output, top['XCUD']['offset'] + 32 + before['index']*28 + 4, center + [radius])
    models.parse_model(output)
    return bytes(output)


def motion_from_json(original, edited):
    source = models.parse_motion(original)
    check_source(original, edited)
    require(edited.get('format') == 'MOT2', 'expected MOT2 JSON')
    for field in ('frame_count', 'fps', 'channel_counts', 'constant_vector_count', 'duration', 'last_frame_time'):
        require(edited[field] == source[field], 'motion timing/header structure cannot change: ' + field)
    require(len(edited['nodes']) == len(source['nodes']), 'motion node count cannot change')
    require(edited['constant_vectors'] == source['constant_vectors'], 'constant_vectors is an inspection pool; edit nodes[].tracks[].values instead')
    output = bytearray(original)
    table, pool = struct.unpack_from('<II', original, 20)
    constant_count = u32(original, 16) & 65535
    additions = []
    indices = []
    group_times = {}
    for before, after in zip(source['nodes'], edited['nodes']):
        require(after['index'] == before['index'] and after['flags'] == before['flags'] and after['indices'] == before['indices'], 'motion nodes/animated flags/indices cannot change')
        row = list(before['indices'])
        for typ, path in enumerate(('translation','rotation','scale')):
            bt, at = before['tracks'][path], after['tracks'][path]
            require(at['animated'] == bt['animated'] and at['channel'] == bt['channel'], 'channel identity cannot change')
            require(len(at['times']) == len(bt['times']) and len(at['values']) == len(bt['values']), 'key count cannot change')
            width = 4 if path == 'rotation' else 3
            for v in at['values']:
                floats(v, width)
                if width == 4:
                    require(abs(sum(x*x for x in v)-1)<.01, 'rotation quaternion must be unit length')
            if bt['animated']:
                _, keys, values_at, times_at = struct.unpack_from('<HHII', original, 28+typ*12)
                times = at['times']
                require(all(math.isfinite(t) and t >= 0 for t in times) and all(b>a for a,b in zip(times,times[1:])), 'key times must increase')
                if typ in group_times:
                    require(times == group_times[typ], 'channels in a group must share the same time array')
                group_times[typ] = times
                for k,v in enumerate(at['values']):
                    patch_floats(output, values_at + (before['indices'][typ]+k)*16, v)
                patch_floats(output, times_at, times)
            else:
                require(at['times'] == bt['times'], 'constant time must remain zero')
                if at['values'] != bt['values']:
                    old = list(struct.unpack_from('<4f', original, pool + before['indices'][typ]*16))
                    value = list(at['values'][0]) + old[width:]
                    row[typ] = constant_count + len(additions)
                    require(row[typ] < 65535, 'constant vector pool exceeds u16 capacity')
                    additions.append(floats(value,4))
        indices.append(row)
    if additions:
        extra = b''.join(additions)
        output[table:table] = extra
        for off in (20,24,32,36,44,48,56,60):
            old = u32(original,off)
            if old >= table:
                struct.pack_into('<I',output,off,old+len(extra))
        struct.pack_into('<H',output,16,constant_count+len(additions))
        struct.pack_into('<I',output,4,len(output))
        table += len(extra)
    for i,row in enumerate(indices):
        struct.pack_into('<3H',output,table+i*8+2,*row)
    models.parse_motion(output)
    return bytes(output)


def motions_from_json(original, edited):
    check_source(original, edited)
    if original[:4] == b'MOT2':
        return motion_from_json(original,edited)
    source = models.parse_motions(original)
    require(edited.get('format') == 'RFSM/MOT2', 'expected package motion JSON')
    require(edited['bones'] == source['bones'] and len(edited['motions']) == len(source['motions']), 'package bone/motion structure cannot change')
    meta = models.archive.motion_archive(original)
    bodies = []
    for before, after, entry in zip(source['motions'],edited['motions'],meta['motions']):
        for key in ('name','package_index','forward_bone_bindings','reverse_node_bindings'):
            require(before[key] == after[key], 'motion binding identity cannot change')
        bodies.append(motion_from_json(original[entry['offset']:entry['offset']+entry['size']], after))
    if all(body == original[e['offset']:e['offset']+e['size']] for body,e in zip(bodies,meta['motions'])):
        return original
    first = meta['motions'][0]['offset']
    output = bytearray(original[:first])
    for i,body in enumerate(bodies):
        while len(output)%16:
            output.append(0)
        struct.pack_into('<II',output,16+i*32+16,len(output),len(body))
        output.extend(body)
    while len(output)%16:
        output.append(0)
    models.parse_motions(output)
    return bytes(output)


def write_output(path, data, inputs):
    target = Path(path)
    require(all(target.resolve()!=Path(p).resolve() for p in inputs), 'output must differ from every input')
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name+'.', suffix='.tmp', delete=False) as f:
        temporary = Path(f.name)
        try:
            f.write(data)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


class c_gltf_reader:
    def __init__(self, path):
        self.m_path = Path(path)
        raw = self.m_path.read_bytes()
        binary = None
        if raw[:4] == b'glTF':
            require(len(raw)>=12 and u32(raw,4)==2 and u32(raw,8)==len(raw), 'invalid GLB header')
            at = 12
            document = None
            while at < len(raw):
                length, kind = struct.unpack_from('<II',raw,at)
                at += 8
                require(at+length<=len(raw), 'truncated GLB chunk')
                if kind == 0x4E4F534A:
                    require(document is None, 'duplicate GLB JSON')
                    document = json.loads(raw[at:at+length].decode('utf-8'))
                elif kind == 0x004E4942:
                    require(binary is None, 'duplicate GLB BIN')
                    binary = raw[at:at+length]
                at += length
            require(document is not None, 'GLB has no JSON')
            self.m_document = document
        else:
            self.m_document = json.loads(raw.decode('utf-8'))
        require(self.m_document.get('asset',{}).get('version') == '2.0', 'expected glTF 2.0')
        require(not self.m_document.get('extensionsRequired'), 'required glTF extensions are unsupported for import')
        self.m_buffers = []
        for item in self.m_document.get('buffers',[]):
            uri = item.get('uri')
            if uri is None:
                require(binary is not None, 'missing GLB binary buffer')
                blob = binary
            elif uri.startswith('data:'):
                require(';base64,' in uri, 'buffer data URI must be base64')
                blob = base64.b64decode(uri.split(',',1)[1],validate=True)
            else:
                uri = unquote(uri)
                require(':' not in uri and not Path(uri).is_absolute(), 'buffer URI must be a relative local file')
                target = self.m_path.parent / uri
                require(target.resolve().is_relative_to(self.m_path.parent.resolve()), 'buffer path escapes glTF folder')
                blob = target.read_bytes()
            require(len(blob) >= item['byteLength'], 'truncated glTF buffer')
            self.m_buffers.append(blob)
        self.m_parents = {}
        for i,n in enumerate(self.m_document.get('nodes',[])):
            for child in n.get('children',[]):
                require(0<=child<len(self.m_document['nodes']) and child not in self.m_parents, 'invalid glTF hierarchy')
                self.m_parents[child] = i
        self.m_worlds = {}

    def accessor(self, index):
        d = self.m_document
        a = d['accessors'][index]
        require('sparse' not in a, 'sparse accessors are unsupported; expand them before import')
        width = dict(SCALAR=1,VEC2=2,VEC3=3,VEC4=4,MAT4=16)[a['type']]
        fmt, size = {5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}[a['componentType']]
        view = d['bufferViews'][a['bufferView']]
        blob = self.m_buffers[view['buffer']]
        stride = view.get('byteStride',width*size)
        require(stride>=width*size and a['count']>=0, 'invalid accessor stride/count')
        start = view.get('byteOffset',0)+a.get('byteOffset',0)
        end = start+(a['count']-1)*stride+width*size if a['count'] else start
        require(start>=view.get('byteOffset',0) and end<=view.get('byteOffset',0)+view['byteLength']<=len(blob), 'accessor outside buffer view')
        result = [list(struct.unpack_from('<'+fmt*width,blob,start+i*stride)) for i in range(a['count'])]
        if a.get('normalized'):
            require(a['componentType'] in (5120,5121,5122,5123), 'invalid normalized accessor')
            maximum = {5120:127,5121:255,5122:32767,5123:65535}[a['componentType']]
            result = [[max(-1,v/maximum) for v in row] for row in result]
        require(all(math.isfinite(v) for row in result for v in row), 'non-finite accessor')
        return result

    def world(self, index, visiting=None):
        if index in self.m_worlds:
            return self.m_worlds[index]
        visiting = set() if visiting is None else visiting
        require(index not in visiting, 'glTF hierarchy cycle')
        visiting.add(index)
        n = self.m_document['nodes'][index]
        if 'matrix' in n:
            require(len(n['matrix'])==16, 'invalid node matrix')
            matrix = [[n['matrix'][c*4+r] for c in range(4)] for r in range(4)]
        else:
            matrix = models.local_matrix(dict(translation=n.get('translation',[0,0,0]),
                rotation=n.get('rotation',[0,0,0,1]),scale=n.get('scale',[1,1,1])))
        if index in self.m_parents:
            matrix = models.multiply(self.world(self.m_parents[index],visiting),matrix)
        self.m_worlds[index] = matrix
        visiting.remove(index)
        return matrix


def close_values(a,b,tolerance=1e-6):
    return len(a)==len(b) and all(abs(x-y)<=tolerance*max(1,abs(x),abs(y)) for x,y in zip(a,b))


def preserve_noise(value, original):
    return list(original) if close_values(value,original) else list(value)


def transform_point(matrix, value):
    return [sum(matrix[r][c]*(list(value)+[1])[c] for c in range(4)) for r in range(3)]


def transform_normal(matrix, value):
    inv = models.inverse(matrix)
    return models.normalized([sum(inv[c][r]*value[c] for c in range(3)) for r in range(3)])


def cyclic_face(face):
    return min(tuple(face[i:]+face[:i]) for i in range(3))


def model_from_gltf(original, path):
    from collections import Counter
    reader = c_gltf_reader(path)
    d = reader.m_document
    require(not d.get('extras',{}).get('baked_facial_playback'), 'baked playback is not an edit template; re-export an unbaked model')
    digest = d.get('extras',{}).get('source_sha256')
    require(digest is None or digest==hashlib.sha256(original).hexdigest(), 'glTF source hash does not match original model')
    source = models.parse_model(original)
    edited = copy.deepcopy(source)
    worlds = models.world_matrices(source['nodes'])
    by_name = {m['name']:m['index'] for m in source['meshes']}
    bones_by_name = {n['name']:i for i,n in enumerate(source['nodes'])}
    updated = set()
    for node_index, node in enumerate(d.get('nodes',[])):
        if 'mesh' not in node:
            continue
        gm = d['meshes'][node['mesh']]
        mi = gm.get('extras',{}).get('source_index',by_name.get(gm.get('name')))
        require(isinstance(mi,int) and 0<=mi<len(source['meshes']), 'cannot identify source mesh; preserve its name or source_index extras')
        require(mi not in updated, 'multiple scene nodes reference the same source mesh')
        updated.add(mi)
        before, after = source['meshes'][mi], edited['meshes'][mi]
        require(not any(gm.get('weights',[])) and not any(node.get('weights',[])), 'morph pose weights are runtime controls; import endpoint geometry or edit ANI instead')
        require(not gm.get('extras',{}).get('negative_skin_weights_clamped'), 'clamped negative-weight exports cannot be imported losslessly; use model-json')
        if before['skinned']:
            require('skin' in node, 'skinned source mesh lost its skin')
            skin = d['skins'][node['skin']]
            require('inverseBindMatrices' in skin, 'skin must contain inverse bind matrices')
            bind = reader.accessor(skin['inverseBindMatrices'])
            require(len(bind)==len(skin['joints']), 'inverse bind count mismatch')
            joint_mapping = []
            for j,ib in zip(skin['joints'],bind):
                name = d['nodes'][j].get('name')
                require(name in bones_by_name, 'unknown skin joint: '+str(name))
                source_joint = bones_by_name[name]
                actual = reader.world(j)
                require(close_values(sum(actual,[]),sum(worlds[source_joint],[]),2e-5), 'armature rest transforms changed; import those separately using model-json')
                expected = models.inverse(worlds[source_joint])
                actual_ib = [[ib[c*4+r] for c in range(4)] for r in range(4)]
                require(close_values(sum(actual_ib,[]),sum(expected,[]),2e-5), 'inverse bind matrices changed')
                joint_mapping.append(source_joint)
            require(close_values(sum(reader.world(node_index),[]),sum(models.identity(),[]),2e-5), 'apply skinned mesh object transforms before import')
            matrix = models.identity()
        else:
            joint_mapping = []
            attached = before['palette'][0]
            parent = worlds[attached] if 0<=attached<len(worlds) else models.identity()
            matrix = models.multiply(models.inverse(parent),reader.world(node_index))
        assignments = []
        seen_vertices = {}
        for primitive in gm['primitives']:
            require(primitive.get('mode',4)==4, 'import requires triangle primitives')
            attributes = primitive['attributes']
            require('_ARIKA_VERTEX' in attributes, 'missing _ARIKA_VERTEX: export with the current tools and retain that custom vertex attribute')
            ids = reader.accessor(attributes['_ARIKA_VERTEX'])
            require(all(len(v)==1 and int(v[0])==v[0] and 0<=v[0]<len(before['vertices']) for v in ids), 'invalid source vertex IDs')
            ids = [int(v[0]) for v in ids]
            require('POSITION' in attributes, 'mesh has no POSITION')
            values = {key:reader.accessor(ix) for key,ix in attributes.items() if key in ('POSITION','NORMAL','TEXCOORD_0','COLOR_0','JOINTS_0','WEIGHTS_0')}
            require(all(len(v)==len(ids) for v in values.values()), 'attribute count mismatch')
            indices = [v[0] for v in reader.accessor(primitive['indices'])] if 'indices' in primitive else list(range(len(ids)))
            require(len(indices)%3==0 and all(int(i)==i and 0<=i<len(ids) for i in indices), 'invalid triangle indices')
            assignments.append(Counter(cyclic_face([ids[int(indices[i+j])] for j in range(3)]) for i in range(0,len(indices),3)))
            targets = primitive.get('targets',[])
            require(len(targets)<=1, 'only the existing source morph target can be imported')
            morph_values = {key:reader.accessor(ix) for key,ix in targets[0].items()} if targets else {}
            require(all(len(v)==len(ids) for v in morph_values.values()), 'morph count mismatch')
            for i,vid in enumerate(ids):
                bv = before['vertices'][vid]
                av = copy.deepcopy(bv)
                pos = transform_point(matrix,values['POSITION'][i])
                av['position'] = preserve_noise(pos,bv['position'])
                if 'NORMAL' in values:
                    normal = transform_normal(matrix,values['NORMAL'][i])
                    av['normal'] = bv['normal'] if close_values(normal,models.normalized(bv['normal']) if any(bv['normal']) else [0,1,0]) else normal
                if 'TEXCOORD_0' in values:
                    av['uv'] = preserve_noise(values['TEXCOORD_0'][i],bv['uv'])
                if 'COLOR_0' in values and 'color_ps2' in bv:
                    color = values['COLOR_0'][i]
                    color = color+[1] if len(color)==3 else color
                    original_color=[max(0,min(1,c/128)) for c in bv['color_ps2']]
                    av['color_ps2'] = bv['color_ps2'] if close_values(color,original_color) else [v*128 for v in color]
                if before['skinned']:
                    require('JOINTS_0' in values and 'WEIGHTS_0' in values, 'skin attributes are missing')
                    gj = values['JOINTS_0'][i]
                    require(all(int(j)==j and 0<=j<len(joint_mapping) for j in gj), 'joint accessor index out of range')
                    joints = [joint_mapping[int(j)] for j in gj]
                    weights = values['WEIGHTS_0'][i]
                    require(len(weights)==4 and all(w>=0 for w in weights) and sum(weights)>0, 'invalid glTF skin weights')
                    weights = [w/sum(weights) for w in weights]
                    # Editors may reorder influence slots; retain exact original data if equivalent.
                    def influences(js,ws):
                        result={}
                        for j,w in zip(js,ws):
                            if w: result[j]=result.get(j,0)+w
                        return result
                    old= influences(bv['joints'],bv['weights']); new=influences(joints,weights)
                    if old.keys()!=new.keys() or not all(close_values([old[k]],[new[k]]) for k in old):
                        av.update(joints=joints,weights=weights)
                if before['morph']:
                    if 'POSITION' in morph_values:
                        target=[values['POSITION'][i][j]+morph_values['POSITION'][i][j] for j in range(3)]
                        av['morph_position']=preserve_noise(transform_point(matrix,target),bv['morph_position'])
                    if 'NORMAL' in morph_values and 'NORMAL' in values:
                        target=[values['NORMAL'][i][j]+morph_values['NORMAL'][i][j] for j in range(3)]
                        target=transform_normal(matrix,target)
                        av['morph_normal']=bv['morph_normal'] if close_values(target,models.normalized(bv['morph_normal']) if any(bv['morph_normal']) else [0,1,0]) else target
                if vid in seen_vertices:
                    require(av==seen_vertices[vid], 'split editor vertices disagree for source vertex %d'%vid)
                seen_vertices[vid]=av
                after['vertices'][vid]=av
        expected = [Counter(cyclic_face(face) for face in p['triangles']) for p in before['primitives'] if p['triangles']]
        require(len(assignments)==len(expected), 'primitive/material section count changed')
        # Editors may reorder material sections, but not move/add/remove triangles.
        remaining = list(expected)
        for actual in assignments:
            require(actual in remaining, 'triangle topology/winding/material grouping changed')
            remaining.remove(actual)
    require(updated, 'no source meshes found')
    return model_from_json(original,edited)


def slerp(a,b,t):
    a,b=models.normalized(a),models.normalized(b)
    dot=sum(x*y for x,y in zip(a,b))
    if dot<0:
        b=[-v for v in b];dot=-dot
    if dot>.9995:
        return models.normalized([(1-t)*x+t*y for x,y in zip(a,b)])
    angle=math.acos(max(-1,min(1,dot)))
    return [(math.sin((1-t)*angle)*x+math.sin(t*angle)*y)/math.sin(angle) for x,y in zip(a,b)]


def sample_track(times,values,time,path,interpolation):
    import bisect
    i=max(0,min(len(times)-1,bisect.bisect_right(times,time)-1))
    if i==len(times)-1 or interpolation=='STEP':
        return list(values[i])
    t=max(0,min(1,(time-times[i])/(times[i+1]-times[i])))
    return slerp(values[i],values[i+1],t) if path=='rotation' else [(1-t)*a+t*b for a,b in zip(values[i],values[i+1])]


def motions_from_gltf(original,path,animation_names=None):
    require(original[:4]==b'RFSM', 'named glTF animation import requires the original RFSM .pmt package')
    reader=c_gltf_reader(path);d=reader.m_document
    edited=models.parse_motions(original)
    by_name={m['name']:m for m in edited['motions']}
    changed=set()
    for animation in d.get('animations',[]):
        name=animation.get('name')
        if animation_names and name not in animation_names:
            continue
        require(name in by_name, 'unknown animation name: '+str(name))
        require(name not in changed, 'duplicate animation name')
        changed.add(name)
        motion=by_name[name]
        digest=animation.get('extras',{}).get('source_mot2_sha256')
        require(digest is None or digest==motion['source_sha256'], 'animation was exported from a different MOT2 payload')
        nodes={n['name']:n for n in motion['nodes'] if 'name' in n}
        seen=set()
        for channel in animation['channels']:
            target=channel['target'];node=d['nodes'][target['node']].get('name');path=target['path']
            require(path in ('translation','rotation','scale'), 'morph/visibility channels are not MOT2 skeletal tracks')
            require(node in nodes, 'animation target has no RFSM binding: '+str(node))
            require((node,path) not in seen, 'duplicate animation target channel')
            seen.add((node,path))
            sampler=animation['samplers'][channel['sampler']]
            interpolation=sampler.get('interpolation','LINEAR')
            require(interpolation in ('LINEAR','STEP'), 'use LINEAR or STEP animation samplers for import')
            times=[v[0] for v in reader.accessor(sampler['input'])]
            values=reader.accessor(sampler['output'])
            require(times and len(times)==len(values) and all(t>=0 for t in times) and all(b>a for a,b in zip(times,times[1:])), 'invalid animation sampler times')
            require(all(len(v)==(4 if path=='rotation' else 3) for v in values), 'animation value width mismatch')
            track=nodes[node]['tracks'][path]
            if not track['animated']:
                reference=models.normalized(values[0]) if path=='rotation' else values[0]
                for value in values:
                    value=models.normalized(value) if path=='rotation' else value
                    if path=='rotation' and sum(a*b for a,b in zip(value,reference))<0: value=[-v for v in value]
                    require(close_values(value,reference), 'source component is constant; adding a new animated channel is unsupported')
            require(times[0]<=track['times'][0]+1e-5 and times[-1]>=track['times'][-1]-1e-5, 'sampler must cover original track times')
            imported=[]
            for time,old in zip(track['times'],track['values']):
                value=sample_track(times,values,time,path,interpolation)
                if path=='rotation':
                    value=models.normalized(value)
                    normalized_old=models.normalized(old)
                    if sum(a*b for a,b in zip(value,normalized_old))<0:value=[-v for v in value]
                    imported.append(old if close_values(value,normalized_old) else value)
                else:
                    imported.append(preserve_noise(value,old))
            track['values']=imported
    require(changed and (not animation_names or set(animation_names)<=changed), 'requested animations were not found')
    return motions_from_json(original,edited)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('model-json','motion-json','model-gltf','motion-gltf'):
        p=sub.add_parser(command)
        p.add_argument('original');p.add_argument('edited');p.add_argument('output')
        if command=='motion-gltf':p.add_argument('--animation',action='append')
    args=parser.parse_args()
    try:
        source=Path(args.original).read_bytes()
        if args.command.endswith('-json'):
            edited=json.loads(Path(args.edited).read_text(encoding='utf-8'))
            result=model_from_json(source,edited) if args.command=='model-json' else motions_from_json(source,edited)
        elif args.command=='model-gltf':
            result=model_from_gltf(source,args.edited)
        else:
            result=motions_from_gltf(source,args.edited,args.animation)
        write_output(args.output,result,[args.original,args.edited])
        print('Wrote %s (%d bytes; %s)'%(args.output,len(result),'unchanged' if result==source else 'modified'))
    except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error) as error:
        print('error: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
