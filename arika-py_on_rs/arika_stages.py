#!/usr/bin/env python3
"""Inspect STG scenes, export HIT polygons, and assemble authored stage previews."""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from arika_models import require,parse_model,build_gltf,c_gltf,quaternion
from arika_import import write_output


def names_at(data,offset,count):
    require(count<=len(data)//16 and offset+count*16<=len(data),'truncated name table')
    names=[]
    for i in range(count):
        raw=data[offset+i*16:offset+(i+1)*16]
        require(b'\0' in raw,'unterminated stage name')
        names.append(raw.split(b'\0',1)[0].decode('cp932'))
    return names


def finite(values):
    require(all(math.isfinite(v) for v in values),'nonfinite stage values')
    return list(values)


def parse_stg(data):
    require(len(data)>=16 and data[:8]==b'\x00\x01\x00\x00STG ','expected reference STG version')
    count,templates=struct.unpack_from('<2I',data,8);names=names_at(data,16,count)
    cursor=16+16*count;nodes=[];pending=[];roots=[]
    while cursor<len(data):
        require(cursor+8<=len(data),'truncated STG node')
        kind,reference_count,links,flags=data[cursor:cursor+4];name_index=struct.unpack_from('<I',data,cursor+4)[0]
        require(kind in (1,2,3,4,5,6) and links<4 and name_index<count,'invalid STG node tag/name')
        require(not reference_count or kind==3,'unexpected STG inline references')
        size={4:60,5:96,6:60}.get(kind,44+reference_count*8)
        require(cursor+size<=len(data),'truncated STG node body')
        index=len(nodes);parent=pending.pop() if pending else -1
        if parent<0:roots.append(index)
        node=dict(index=index,offset=cursor,size=size,kind=kind,flags=flags,links=links,name_index=name_index,
            name=names[name_index],parent=parent,children=[],references=[])
        if parent>=0:nodes[parent]['children'].append(index)
        if kind in (1,2,3):
            values=finite(struct.unpack_from('<9f',data,cursor+8))
            node.update(translation=values[:3],rotation_radians=values[3:6],scale=values[6:9])
            for j in range(reference_count):
                ni,bits=struct.unpack_from('<2I',data,cursor+44+8*j)
                require(ni<count,'invalid STG collision name reference')
                node['references'].append(dict(name_index=ni,name=names[ni],flags=bits))
        else:
            node['opaque_words']=list(struct.unpack_from('<%dI'%((size-8)//4),data,cursor+8))
            if kind==6:
                first,second,parameter,handler=struct.unpack_from('<4i',data,cursor+44)
                require(all(i==-1 or 0<=i<count for i in (first,second)),'invalid state target name')
                node['state_control']=dict(primary_name=None if first==-1 else names[first],secondary_name=None if second==-1 else names[second],parameter_index=parameter,handler_index=handler,native_setup='primary enabled; secondary hidden',source='0x23C8E0 / 0x240290')
        nodes.append(node)
        if links&2:pending.append(parent)
        if links&1:pending.append(index)
        cursor+=size
    require(not pending,'STG hierarchy ends before promised child/sibling')
    require(len(roots)==templates+2,'unexpected STG root/template count')
    require([nodes[i]['name'] for i in roots[-2:]]==['EFFECT','STAGE'],'unexpected STG live root names')
    for node in nodes:
        if 'state_control' not in node:continue
        control=node['state_control']
        order=[];todo=[node['index']]
        while todo:
            index=todo.pop();order.append(index);todo.extend(reversed(nodes[index]['children']))
        for role in ('primary','secondary'):
            name=control[role+'_name']
            matches=[i for i in order if nodes[i]['name']==name] if name is not None else []
            control[role+'_node']=matches[0] if matches else None
            control[role+'_matches']=matches
        control['lookup_scope']='self and descendants; first depth-first name match'
    return dict(format='ARIKA_STG',source_sha256=hashlib.sha256(data).hexdigest(),byte_size=len(data),names=names,
        template_count=templates,roots=roots,effect_root=roots[-2],stage_root=roots[-1],nodes=nodes,
        scope='Structurally inferred authored forest and local TRS; kinds 4/5/6 remain opaque runtime controls. Root/template and record extents checked; runtime scripts/visibility are not executed.')


def parse_hit(data):
    require(len(data)>=32 and data[:8]==b'\0\0\x02\0HIT ','expected reference HIT version')
    count,objects_at,polygons_at,vertices_at=struct.unpack_from('<4I',data,8)
    require(objects_at==32+16*count and polygons_at==objects_at+64*count,'invalid HIT object/name extents')
    require(polygons_at<=vertices_at<=len(data) and (vertices_at-polygons_at)%32==0 and (len(data)-vertices_at)%16==0,'invalid HIT polygon/vertex extents')
    names=names_at(data,32,count);vertices=[finite(struct.unpack_from('<4f',data,i)) for i in range(vertices_at,len(data),16)]
    polygons=[];expected_first=0
    for at in range(polygons_at,vertices_at,32):
        n,first,a,b=struct.unpack_from('<4I',data,at)
        require(n>=3 and first==expected_first and first+n<=len(vertices),'invalid HIT polygon vertex range')
        polygons.append(dict(index=len(polygons),offset=at,vertex_count=n,first_vertex=first,unknown_words=[a,b],
            normal=finite(struct.unpack_from('<4f',data,at+16))))
        expected_first=first+n
    require(expected_first==len(vertices),'unreferenced HIT vertex tail')
    objects=[]
    for i,name in enumerate(names):
        at=objects_at+64*i;flags,n,first=struct.unpack_from('<3I',data,at)
        require(first+n<=len(polygons),'invalid HIT object polygon range')
        objects.append(dict(index=i,name=name,offset=at,flags=flags,polygon_count=n,first_polygon=first,
            radius=finite([struct.unpack_from('<f',data,at+12)[0]])[0],
            vectors=[finite(struct.unpack_from('<4f',data,at+16+j*16)) for j in range(3)]))
    return dict(format='ARIKA_HIT',source_sha256=hashlib.sha256(data).hexdigest(),objects=objects,polygons=polygons,vertices=vertices,
        scope='Resource-local polygon soup and named object ranges. Object flags/bounds and polygon metadata retained; no collision solver or runtime attachment is emulated.')


def hit_obj(document):
    lines=['# Resource-local HIT polygons; STG placement is not applied.']
    lines+=['v '+' '.join(format(v,'.9g') for v in vertex[:3]) for vertex in document['vertices']]
    for obj in document['objects']:
        lines.append('o '+obj['name'].replace(' ','_'))
        for poly in document['polygons'][obj['first_polygon']:obj['first_polygon']+obj['polygon_count']]:
            lines.append('f '+' '.join(str(i+1) for i in range(poly['first_vertex'],poly['first_vertex']+poly['vertex_count'])))
    return ('\n'.join(lines)+'\n').encode()


def inventory(root):
    root=Path(root);base=root/'stg' if (root/'stg').is_dir() else root;rows=[]
    for folder in sorted(base.iterdir()):
        if folder.is_dir() and folder.name.startswith('s') and folder.name[1:].isdecimal():
            rows.append(dict(stage=folder.name,assets=[dict(name=p.name,bytes=p.stat().st_size) for p in sorted(folder.iterdir()) if p.is_file()]))
    require(bool(rows),'no stage folders found')
    return dict(format='ARIKA_STAGE_INVENTORY',stages=rows,scope='Asset inventory only; folder numbers are not inferred display names. ASE assets are audio banks.')


def assemble_document(scene,model,base_document,hit=None):
    require(not model['nodes'] and not any(m['skinned'] for m in model['meshes']),'stage assembly currently requires a rigid stage model')
    if isinstance(base_document, c_gltf):
        # Fast path: compose directly into the model builder and reuse its binary blob.
        gltf=base_document;doc=gltf.m_document
    else:
        # Backwards-compatible path for callers supplying an already-serialized glTF dict.
        doc=copy.deepcopy(base_document);gltf=c_gltf();gltf.m_document=doc
        buffers=doc.get('buffers',[])
        gltf.m_blob=bytearray(base64.b64decode(buffers[0]['uri'].split(',',1)[1])) if buffers else bytearray()
    doc['nodes']=[];doc['scenes']=[];doc['scene']=0
    by_mesh={m['name']:i for i,m in enumerate(doc['meshes'])};unresolved=[];instances=0
    for node in scene['nodes']:
        out=dict(name=node['name'],extras=dict(stg_offset=node['offset'],kind=node['kind'],flags=node['flags']))
        if 'translation' in node:
            out.update(translation=node['translation'],rotation=quaternion([math.degrees(a) for a in node['rotation_radians']]),scale=node['scale'])
        else:out['extras']['opaque_runtime_control']=True
        if node['children']:out['children']=list(node['children'])
        if node['kind']==2:
            if node['name'] in by_mesh:out['mesh']=by_mesh[node['name']];instances+=1
            else:unresolved.append(dict(node=node['index'],name=node['name']))
        doc['nodes'].append(out)
    doc['scenes']=[dict(name='Stage',nodes=[scene['stage_root']]),dict(name='Effects',nodes=[scene['effect_root']])]
    if scene['template_count']:doc['scenes'].append(dict(name='Templates',nodes=scene['roots'][:-2]))
    collision_instances=0;missing_hits=[]
    if hit:
        material=len(doc['materials']);doc['materials'].append(dict(name='Collision wireframe',emissiveFactor=[0.1,1.,0.2],
            pbrMetallicRoughness=dict(baseColorFactor=[0.1,1.,0.2,1.],metallicFactor=0,roughnessFactor=1)))
        positions=gltf.array([v[:3] for v in hit['vertices']],'VEC3',bounds=True)
        hit_mesh={}
        for obj in hit['objects']:
            edges=[]
            for poly in hit['polygons'][obj['first_polygon']:obj['first_polygon']+obj['polygon_count']]:
                a=poly['first_vertex'];n=poly['vertex_count']
                for j in range(n):edges.extend((a+j,a+(j+1)%n))
            if not edges:continue
            mi=len(doc['meshes']);doc['meshes'].append(dict(name=obj['name'],primitives=[dict(attributes=dict(POSITION=positions),indices=gltf.array(edges,'SCALAR',5125),mode=1,material=material)],
                extras=dict(hit_object=obj['index'],flags=obj['flags'])))
            hit_mesh.setdefault(obj['name'],mi)
        offset=len(doc['nodes'])
        for node in scene['nodes']:
            out=copy.deepcopy(doc['nodes'][node['index']]);out.pop('mesh',None)
            out['name']='collision:'+out['name']
            if 'children' in out:out['children']=[i+offset for i in out['children']]
            for ref in node['references']:
                if ref['name'] not in hit_mesh:
                    missing_hits.append(dict(node=node['index'],name=ref['name']));continue
                child=len(scene['nodes'])*2+collision_instances
                out.setdefault('children',[]).append(child);collision_instances+=1
            doc['nodes'].append(out)
        for node in scene['nodes']:
            for ref in node['references']:
                if ref['name'] in hit_mesh:doc['nodes'].append(dict(name=ref['name'],mesh=hit_mesh[ref['name']],extras=dict(stg_reference_flags=ref['flags'])))
        doc['scenes'].append(dict(name='Collision',nodes=[scene['stage_root']+offset]))
        doc['scenes'].append(dict(name='Stage + collision',nodes=[scene['stage_root'],scene['stage_root']+offset]))
    report=dict(format='ARIKA_STAGE_PREVIEW',source_stg_sha256=scene['source_sha256'],source_model_sha256=model['source_sha256'],
        source_hit_sha256=hit['source_sha256'] if hit else None,mesh_instances=instances,unresolved_meshes=unresolved,
        uninstanced_model_meshes=sorted(set(by_mesh)-{n['name'] for n in scene['nodes'] if n['kind']==2}),
        collision_instances=collision_instances,unresolved_collision=missing_hits,
        scope='Authored static preview. TRS interpreted as radians in a child/sibling forest. Template roots are separated. Opaque kinds 4/5/6 use identity transforms and do not execute runtime controls, spawning, visibility or destruction. Collision wireframes preserve polygon edges; no triangulation or solver is inferred.')
    doc['extras']=report;return gltf,report


def build_stage_gltf(stg_path,model_path=None,hit_path=None,texture_path=None,scene=None,scene_data=None,
    model_data=None,hit_data=None,texture_data=None):
    """Build a stage glTF entirely in memory; optional byte payloads avoid disk reads."""
    import os,tempfile
    stg_path=Path(stg_path);model_path=Path(model_path) if model_path else stg_path.with_suffix('.mdl')
    hit_path=Path(hit_path) if hit_path else stg_path.with_suffix('.hit')
    texture_path=Path(texture_path) if texture_path else model_path.with_suffix('.pix')
    if scene is None:
        scene=parse_stg(scene_data if scene_data is not None else stg_path.read_bytes())
    model=parse_model(model_data if model_data is not None else model_path.read_bytes())
    hit=parse_hit(hit_data) if hit_data is not None else (parse_hit(hit_path.read_bytes()) if hit_path.exists() else None)
    texture_arg=None
    if texture_data is not None:
        handle,texture_arg=tempfile.mkstemp(suffix='.pix')
        try:
            with os.fdopen(handle,'wb') as handle_file:handle_file.write(texture_data)
        except Exception:
            os.close(handle);raise
    else:
        texture_arg=texture_path if texture_path.exists() else None
    try:
        base=build_gltf(model,texture_path=texture_arg)
    finally:
        if texture_data is not None:
            try:os.unlink(texture_arg)
            except OSError:pass
    return assemble_document(scene,model,base,hit)


def export_stage(stg_path,output,model_path=None,hit_path=None,texture_path=None,scene=None,scene_data=None):
    require(not hit_path or Path(hit_path).is_file(),'explicit HIT file does not exist')
    require(not texture_path or Path(texture_path).is_file(),'explicit texture file does not exist')
    stg_path=Path(stg_path);model_path=Path(model_path) if model_path else stg_path.with_suffix('.mdl')
    hit_path=Path(hit_path) if hit_path else stg_path.with_suffix('.hit')
    texture_path=Path(texture_path) if texture_path else model_path.with_suffix('.pix')
    inputs=[stg_path,model_path]+([hit_path] if hit_path.exists() else [])+([texture_path] if texture_path.exists() else [])
    require(all(Path(output).resolve()!=p.resolve() for p in inputs),'output must differ from inputs')
    gltf,report=build_stage_gltf(stg_path,model_path,hit_path,texture_path,scene,scene_data)
    payload=json.dumps(gltf.to_document(),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    write_output(output,payload,inputs)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('list','stg-json','controls-json','hit-json','hit-obj','scene-gltf'):
        p=sub.add_parser(command);p.add_argument('input');p.add_argument('output')
        if command=='scene-gltf':p.add_argument('--model');p.add_argument('--hit');p.add_argument('--textures')
    args=parser.parse_args()
    try:
        if args.command=='scene-gltf':print(json.dumps(export_stage(args.input,args.output,args.model,args.hit,args.textures)))
        elif args.command=='list':write_output(args.output,json.dumps(inventory(args.input),indent=2).encode(),[])
        else:
            data=Path(args.input).read_bytes();doc=parse_stg(data) if args.command in ('stg-json','controls-json') else parse_hit(data)
            if args.command=='controls-json':
                doc=dict(format='ARIKA_STAGE_CONTROLS',source_sha256=doc['source_sha256'],controls=[dict(node=n['index'],name=n['name'],**n['state_control']) for n in doc['nodes'] if 'state_control'in n],scope='Native subtree lookup structure; resolved authored nodes only, no runtime visibility/destruction simulation.')
            write_output(args.output,hit_obj(doc) if args.command=='hit-obj' else json.dumps(doc,indent=2).encode(),[args.input])
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
