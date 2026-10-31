#!/usr/bin/env python3
"""Audit stage extents/name bindings, optional snapshot evidence and glTF integrity."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
from arika_stages import parse_stg,parse_hit
from arika_models import parse_model,require
from arika_import import c_gltf_reader,write_output


def check_scene_gltf(path):
    reader=c_gltf_reader(path);doc=reader.m_document
    values=[reader.accessor(i) for i in range(len(doc['accessors']))]
    for mesh in doc['meshes']:
        for part in mesh['primitives']:
            count=len(values[part['attributes']['POSITION']]);indices=[v[0] for v in values[part['indices']]]
            require(all(type(i) is int and 0<=i<count for i in indices),'invalid stage mesh index')
            width={1:2,4:3}[part.get('mode',4)]
            require(len(indices)%width==0,'stage primitive index count mismatch')
    seen=set();active=set()
    def visit(i):
        require(type(i) is int and 0<=i<len(doc['nodes']),'invalid stage node index')
        require(i not in active,'stage node cycle')
        if i in seen:return
        active.add(i);node=doc['nodes'][i]
        if 'mesh' in node:require(0<=node['mesh']<len(doc['meshes']),'invalid stage node mesh')
        for k in ('translation','rotation','scale'):
            if k in node:require(all(math.isfinite(v) for v in node[k]),'nonfinite stage transform')
        for child in node.get('children',[]):visit(child)
        active.remove(i);seen.add(i)
    for scene in doc['scenes']:
        for i in scene['nodes']:visit(i)
    for i in range(len(doc['nodes'])):visit(i)
    require(not doc['extras']['unresolved_meshes'] and not doc['extras']['unresolved_collision'],'unresolved stage preview references')
    return dict(file=Path(path).name,accessors_checked=len(values),nodes_checked=len(seen),
        scene_names=[s['name'] for s in doc['scenes']],mesh_instances=doc['extras']['mesh_instances'],collision_instances=doc['extras']['collision_instances'])


def audit(root,snapshot=None):
    root=Path(root);rows=[];total=Counter();ram=Path(snapshot).read_bytes()[:32*1024*1024] if snapshot else None;runtime=[]
    for path in sorted(root.rglob('*.stg')):
        data=path.read_bytes();scene=parse_stg(data);hit_data=path.with_suffix('.hit').read_bytes();hit=parse_hit(hit_data)
        model=parse_model(path.with_suffix('.mdl').read_bytes());meshes={m['name'] for m in model['meshes']};hits={o['name'] for o in hit['objects']}
        missing_meshes=[n['name'] for n in scene['nodes'] if n['kind']==2 and n['name'] not in meshes]
        missing_hits=[r['name'] for n in scene['nodes'] for r in n['references'] if r['name'] not in hits]
        require(not missing_meshes and not missing_hits,'unresolved stage names in '+str(path))
        require(not model['nodes'] and not any(m['skinned'] for m in model['meshes']),'unexpected non-rigid stage base')
        counts=dict(nodes=len(scene['nodes']),mesh_references=sum(n['kind']==2 for n in scene['nodes']),
            collision_references=sum(len(n['references']) for n in scene['nodes']),hit_objects=len(hit['objects']),
            polygons=len(hit['polygons']),vertices=len(hit['vertices']))
        rows.append(dict(file=path.relative_to(root).as_posix(),templates=scene['template_count'],node_kinds=dict(Counter(n['kind'] for n in scene['nodes'])),**counts))
        total.update(counts)
        if ram is not None:
            at=ram.find(hit_data)
            if at>=0:runtime.append(dict(file=path.with_suffix('.hit').name,address=hex(at),exact_bytes_matched=len(hit_data)))
            name_end=16+16*len(scene['names']);at=ram.find(data[:name_end])
            if at>=0:
                checked=0
                for n in scene['nodes']:
                    off=at+n['offset'];kind,refs,links,flags=ram[off:off+4]
                    require((kind,refs,links&3,flags)==(n['kind'],len(n['references']),n['links'],n['flags']),'runtime STG tag mismatch')
                    require(struct.unpack_from('<I',ram,off+4)[0]==n['name_index'],'runtime STG name mismatch');checked+=1
                runtime.append(dict(file=path.name,address=hex(at),names_and_tags_checked=checked,
                    scope='Name table and original tag bits; runtime adds tag flags and modifies control payloads. No transform/behavior equivalence is asserted.'))
    require(bool(rows),'no STG assets found')
    return dict(format='ARIKA_STAGE_VALIDATION',stage_scenes=len(rows),totals=dict(total),files=rows,runtime_matches=runtime,
        snapshot_sha256=hashlib.sha256(Path(snapshot).read_bytes()).hexdigest() if snapshot else None,
        scope='Corpus structure, exact mesh/collision names, rigid base-model scope and optional snapshot checks. STG forest/TRS preview semantics are inferred from authored data; runtime controls, visibility, destruction and scripts remain unresolved.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('output');p.add_argument('--snapshot');p.add_argument('--gltf',action='append',default=[]);args=p.parse_args()
    result=audit(args.root,args.snapshot);result['gltf_exports']=[check_scene_gltf(path) for path in args.gltf]
    inputs=list(Path(args.root).rglob('*.stg'))+list(Path(args.root).rglob('*.hit'))+list(Path(args.root).rglob('*.mdl'))+args.gltf+([args.snapshot] if args.snapshot else [])
    write_output(args.output,json.dumps(result,indent=2).encode(),inputs)
    print('Stage scenes:',result['stage_scenes'],'polygons:',result['totals']['polygons'])


if __name__=='__main__':main()
