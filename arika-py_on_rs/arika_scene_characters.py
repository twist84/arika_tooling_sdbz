"""Static character previews: bake authored skin/morph pose into rigid meshes."""
import base64
import copy
import io
from pathlib import Path
import tempfile
from urllib.parse import unquote
import numpy as np
from PIL import Image
from arika_import import c_gltf_reader
from arika_models import c_gltf,parse_model,export_gltf,build_gltf,require


def embedded_image(reader,image):
    uri=image.get('uri')
    if uri and uri.startswith('data:'):
        require(';base64,' in uri,'character image must use base64')
        raw=base64.b64decode(uri.split(',',1)[1],validate=True)
    elif uri:
        uri=unquote(uri);require(':' not in uri and not Path(uri).is_absolute(),'character image must be local')
        target=(reader.m_path.parent/uri).resolve()
        require(target.is_relative_to(reader.m_path.parent.resolve()),'image escapes character folder')
        raw=target.read_bytes()
    else:
        view=reader.m_document['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
        raw=reader.m_buffers[view['buffer']][start:start+view['byteLength']]
        require(len(raw)==view['byteLength'],'truncated character image')
    with Image.open(io.BytesIO(raw)) as source:
        require(source.width<=16384 and source.height<=16384,'character texture too large')
        output=io.BytesIO();source.convert('RGBA').save(output,format='PNG')
    return dict(name=image.get('name','Character texture'),uri='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode())


def bake_character(reader):
    source=reader.m_document;g=c_gltf();doc=g.m_document
    doc['images']=[embedded_image(reader,image) for image in source.get('images',[])]
    doc['textures']=copy.deepcopy(source.get('textures',[]));doc['samplers']=copy.deepcopy(source.get('samplers',[]))
    for material in source.get('materials',[]):
        pbr=material.get('pbrMetallicRoughness',{})
        flat=dict(name=material.get('name','Character material'),doubleSided=material.get('doubleSided',True),alphaMode=material.get('alphaMode','OPAQUE'),alphaCutoff=material.get('alphaCutoff',.5),pbrMetallicRoughness=dict(baseColorFactor=pbr.get('baseColorFactor',[1,1,1,1]),metallicFactor=0,roughnessFactor=1))
        if 'baseColorTexture' in pbr:flat['pbrMetallicRoughness']['baseColorTexture']=copy.deepcopy(pbr['baseColorTexture'])
        doc['materials'].append(flat)
    scene=source['scenes'][source.get('scene',0)];visited=set()
    def walk(index):
        require(index not in visited,'character scene repeats a node');visited.add(index)
        node=source['nodes'][index]
        if 'mesh' in node:
            mesh=source['meshes'][node['mesh']];parts=[];world=np.asarray(reader.world(index),dtype='f8')
            skin=source['skins'][node['skin']] if 'skin' in node else None
            matrices=None
            if skin:
                bind=reader.accessor(skin['inverseBindMatrices']) if 'inverseBindMatrices' in skin else [np.eye(4).reshape(-1).tolist() for _ in skin['joints']]
                require(len(bind)==len(skin['joints']),'character inverse bind count mismatch')
                matrices=np.asarray([np.asarray(reader.world(joint))@np.asarray(matrix).reshape(4,4).T for joint,matrix in zip(skin['joints'],bind)])
            for primitive in mesh['primitives']:
                require(primitive.get('mode',4)==4,'character preview requires triangle meshes')
                attrs=primitive['attributes'];positions=np.asarray(reader.accessor(attrs['POSITION']),dtype='f8')
                require(positions.ndim==2 and positions.shape[1]==3 and len(positions)>0,'invalid character positions')
                weights=node.get('weights',mesh.get('weights',[]))
                for weight,target in zip(weights,primitive.get('targets',[])):
                    if weight and 'POSITION' in target:positions=positions+float(weight)*np.asarray(reader.accessor(target['POSITION']))
                homogeneous=np.column_stack((positions,np.ones(len(positions))))
                if skin:
                    require('JOINTS_0' in attrs and 'WEIGHTS_0' in attrs,'skinned character has no influences')
                    require('JOINTS_1' not in attrs,'more than four skin influences are unsupported')
                    joints=np.asarray(reader.accessor(attrs['JOINTS_0']));influences=np.asarray(reader.accessor(attrs['WEIGHTS_0']),dtype='f8')
                    require(joints.shape==influences.shape==(len(positions),4),'invalid character skin influences')
                    require(np.all(joints==joints.astype('i8')) and np.all(joints>=0) and np.all(joints<len(matrices)),'invalid character skin joint')
                    require(np.all(influences>=0) and np.all(influences.sum(axis=1)>1e-8),'invalid character skin weights')
                    influences=influences/influences.sum(axis=1)[:,None]
                    positions=np.einsum('nijk,nk,ni->nj',matrices[joints.astype('i8')],homogeneous,influences)[:,:3]
                else:positions=(world@homogeneous.T).T[:,:3]
                require(np.isfinite(positions).all(),'invalid baked character pose')
                uv=np.asarray(reader.accessor(attrs['TEXCOORD_0'])) if 'TEXCOORD_0' in attrs else np.zeros((len(positions),2))
                require(uv.shape==(len(positions),2),'invalid character UVs')
                indices=[row[0] for row in reader.accessor(primitive['indices'])] if 'indices' in primitive else list(range(len(positions)))
                require(indices and len(indices)%3==0 and all(int(i)==i and 0<=i<len(positions) for i in indices),'invalid character triangles')
                part=dict(attributes=dict(POSITION=g.array(positions.tolist(),'VEC3',bounds=True),TEXCOORD_0=g.array(uv.tolist(),'VEC2')),indices=g.array(indices,'SCALAR',5125),mode=4)
                if 'material' in primitive:
                    require(0<=primitive['material']<len(doc['materials']),'invalid character material');part['material']=primitive['material']
                parts.append(part)
            require(parts,'character mesh has no triangles')
            mi=len(doc['meshes']);doc['meshes'].append(dict(name=mesh.get('name',node.get('name','Character mesh')),primitives=parts))
            doc['nodes'].append(dict(name=node.get('name',mesh.get('name','Character mesh')),mesh=mi,extras=dict(character_part=True)))
            doc['scenes'][0]['nodes'].append(len(doc['nodes'])-1)
        for child in node.get('children',[]):walk(child)
    for root in scene['nodes']:walk(root)
    require(doc['meshes'],'character contains no visible meshes')
    doc['buffers']=[dict(byteLength=len(g.m_blob),uri='data:application/octet-stream;base64,'+base64.b64encode(g.m_blob).decode())]
    return doc


def load_character(path,texture_path=None):
    path=Path(path);sources=[str(path.resolve())]
    if path.suffix.lower() in ('.gltf','.glb'):
        result=bake_character(c_gltf_reader(path))
    else:
        model=parse_model(path.read_bytes())
        if texture_path is None:
            candidate=path.with_suffix('.pix')
            texture_path=candidate if candidate.exists() else None
        if texture_path:sources.append(str(Path(texture_path).resolve()))
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'character.gltf'
            export_gltf(model,target,texture_path=texture_path,clamp_skin_weights=True)
            result=bake_character(c_gltf_reader(target))
    result['extras']=dict(character_preview=True,source_paths=sources,note='Authored static pose; animation and PS2 material logic are not reproduced.')
    return result


def load_skinned_character(path,texture_path=None):
    """Load a character without baking: keep nodes, skins, joints and skin attributes."""
    path=Path(path);sources=[str(path.resolve())]
    if path.suffix.lower() in ('.gltf','.glb'):
        reader=c_gltf_reader(path)
        doc=copy.deepcopy(reader.m_document)
        # Project files are self-contained. Embed GLB/external buffers and
        # normalize images into inline PNG before merging with the scene.
        for index, buffer in enumerate(doc.get('buffers', [])):
            data=reader.m_buffers[index]
            buffer['uri']='data:application/octet-stream;base64,'+base64.b64encode(data).decode()
        doc['images']=[embedded_image(reader, image) for image in doc.get('images',[])]
    else:
        model=parse_model(path.read_bytes())
        if texture_path is None:
            candidate=path.with_suffix('.pix')
            texture_path=candidate if candidate.exists() else None
        if texture_path:sources.append(str(Path(texture_path).resolve()))
        doc=build_gltf(model,motions=(),texture_path=texture_path,clamp_skin_weights=True).to_document()
    extras=doc.setdefault('extras',{})
    extras['skinned_character']=True
    extras['source_paths']=sources
    for node in doc.get('nodes',[]):
        if 'skin' in node:
            node.setdefault('extras',{})['skinned_preview']=True
    return doc


def merge_character(document,character,name,mesh_indices=None,translation=(0,0,0),hidden_indices=None,skinned=False):
    """Return a merged document; caller commits once after complete validation."""
    selected=set(range(len(character['meshes']))) if mesh_indices is None else set(mesh_indices)
    hidden=set(hidden_indices or ())
    require(selected and all(type(i)is int and 0<=i<len(character['meshes']) for i in selected),'select at least one valid character mesh')
    require(len(translation)==3 and all(np.isfinite(v) for v in translation),'invalid character position')
    doc=copy.deepcopy(document);source=copy.deepcopy(character)
    offsets={key:len(doc.get(key,[])) for key in ('buffers','bufferViews','accessors','images','textures','samplers','materials','meshes','nodes')}
    for view in source['bufferViews']:view['buffer']+=offsets['buffers']
    for accessor in source['accessors']:accessor['bufferView']+=offsets['bufferViews']
    for texture in source.get('textures',[]):
        texture['source']+=offsets['images']
        if 'sampler' in texture:texture['sampler']+=offsets['samplers']
    for material in source['materials']:
        info=material.get('pbrMetallicRoughness',{}).get('baseColorTexture')
        if info is not None:info['index']+=offsets['textures']
    mesh_mapping={}
    for index in sorted(selected):
        mesh=source['meshes'][index]
        for primitive in mesh['primitives']:
            primitive['attributes']={key:value+offsets['accessors'] for key,value in primitive['attributes'].items()}
            primitive['indices']+=offsets['accessors']
            if 'material' in primitive:primitive['material']+=offsets['materials']
        mesh_mapping[index]=len(doc.setdefault('meshes',[]));doc['meshes'].append(mesh)
    actor=offsets['nodes']
    root_extras=dict(character_preview=dict(rotation_radians=[0,0,0],source_paths=source.get('extras',{}).get('source_paths',[])),skinned=bool(skinned))
    root=dict(name=name,translation=list(translation),rotation=[0,0,0,1],scale=[1,1,1],children=[],extras=root_extras)
    doc['nodes'].append(root)
    skin_offset=len(doc.get('skins',[]))
    node_mapping={}
    if skinned:
        # Preserve the skeleton hierarchy: add every source node, remap meshes,
        # skin joints and children so bones and skinned meshes stay valid.
        for i,node in enumerate(source['nodes']):
            if 'mesh' in node and node['mesh'] not in mesh_mapping:
                node_mapping[i]=None
                continue
            new_node=copy.deepcopy(node)
            if 'mesh' in new_node:
                new_node['mesh']=mesh_mapping[new_node['mesh']]
            if 'skin' in new_node:
                new_node.setdefault('extras',{})['skinned_preview']=True
            node_mapping[i]=len(doc['nodes'])
            doc['nodes'].append(new_node)
        for new_node in doc['nodes'][actor+1:]:
            if 'children' in new_node:
                new_node['children']=[node_mapping[c] for c in new_node.get('children',[]) if node_mapping.get(c) is not None]
            if 'skin' in new_node:
                new_node['skin']+=skin_offset
        for skin in source.get('skins',[]):
            new_skin=copy.deepcopy(skin)
            new_skin['joints']=[node_mapping[j] for j in new_skin.get('joints',[]) if node_mapping.get(j) is not None]
            if 'inverseBindMatrices' in new_skin:
                new_skin['inverseBindMatrices']+=offsets['accessors']
            if 'skeleton' in new_skin:
                if new_skin['skeleton'] in node_mapping and node_mapping[new_skin['skeleton']] is not None:
                    new_skin['skeleton']=node_mapping[new_skin['skeleton']]
                else:new_skin.pop('skeleton')
            doc.setdefault('skins',[]).append(new_skin)
        scene_index=source.get('scene',0)
        scene_roots=source['scenes'][scene_index]['nodes'] if 0<=scene_index<len(source.get('scenes',[])) else []
        root['children']=[node_mapping[i] for i in scene_roots if node_mapping.get(i) is not None]
    else:
        children=[]
        for node in source['nodes']:
            if node['mesh'] in selected:
                orig_mesh=node['mesh']
                node['mesh']=mesh_mapping[node['mesh']]
                if orig_mesh in hidden:
                    node.setdefault('extras',{}).setdefault('arika_editor',{})['hidden']=True
                children.append(len(doc['nodes']))
                doc['nodes'].append(node)
        root['children']=children
    doc['scenes'][doc.get('scene',0)]['nodes'].append(actor)
    if skinned:
        for animation in source.get('animations',[]):
            copy_animation=copy.deepcopy(animation)
            channels=[]
            for channel in copy_animation.get('channels',[]):
                target=channel.get('target',{})
                mapped=node_mapping.get(target.get('node'))
                if mapped is not None:
                    target['node']=mapped
                    channels.append(channel)
            if not channels:
                continue
            copy_animation['channels']=channels
            for sampler in copy_animation.get('samplers',[]):
                sampler['input']+=offsets['accessors']
                sampler['output']+=offsets['accessors']
            doc.setdefault('animations',[]).append(copy_animation)
    for key in ('buffers','bufferViews','accessors','images','textures','samplers','materials'):doc.setdefault(key,[]).extend(source.get(key,[]))
    return doc,actor
