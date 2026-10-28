#!/usr/bin/env python3
"""Audit extracted CHT mappings and optional raw EE RAM / glTF evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from arika_cht import parse_cht, load_banks, resolve
from arika_import import c_gltf_reader, write_output


def audit(root,snapshot=None):
    root=Path(root);common=root/'ply/p00/p00x.pmt'
    ram=Path(snapshot).read_bytes()[:32*1024*1024] if snapshot else None
    if ram is not None and len(ram)<32*1024*1024:
        raise ValueError('expected a raw snapshot beginning with 32 MiB EE RAM')
    files=[];missing=[];runtime=[]
    for path in sorted(root.rglob('*.cht')):
        data=path.read_bytes();document=parse_cht(data)
        banks=load_banks(['0='+str(path.with_suffix('.pmt')),'1='+str(common)])
        counts=dict(resolved=0,missing_bank=0,missing_motion=0)
        for action in document['actions']:
            for record in action['variants']:
                binding=resolve(record,banks);counts[binding['status']]+=1
                if binding['status']!='resolved':
                    missing.append(dict(file=path.relative_to(root).as_posix(),motion_id=action['motion_id'],
                        variant=record['variant'],motion_name=record['motion_name'],resource_bank=record['resource_bank'],status=binding['status']))
        files.append(dict(file=path.relative_to(root).as_posix(),source_sha256=document['source_sha256'],
            bytes_consumed=document['byte_size'],actions=len(document['actions']),**counts))
        if ram is not None:
            base=ram.find(data[:20+32*len(document['name_table'])])
            if base>=0:
                checked=0
                for action in document['actions']:
                    for record in action['variants']:
                        pointer,packed=struct.unpack_from('<II',ram,base+record['offset'])
                        expected=base+20+32*record['name_index']
                        if pointer!=expected or packed!=(record['name_index']|(record['resource_bank']<<16)):
                            raise ValueError('runtime relocation mismatch in '+str(path))
                        checked+=1
                runtime.append(dict(file=path.relative_to(root).as_posix(),ee_address=hex(base),relocated_records_checked=checked))
    if not files:raise ValueError('no CHT files found')
    return dict(format='ARIKA_CHT_MAPPING_VALIDATION',files=files,total_files=len(files),
        total_actions=sum(f['actions'] for f in files),resolved=sum(f['resolved'] for f in files),
        unresolved=missing,runtime_relocations=runtime,
        snapshot_sha256=hashlib.sha256(Path(snapshot).read_bytes()).hexdigest() if snapshot else None,
        scope='Explicit bank 0 companion / bank 1 p00x packages. Contextual fallback is not applied. Runtime checks compare relocated name pointers and packed bank/name indices.')


def check_gltf(path):
    reader=c_gltf_reader(path);document=reader.m_document
    values=[reader.accessor(i) for i in range(len(document['accessors']))]
    for clip in document.get('animations',[]):
        for channel in clip['channels']:
            sampler=clip['samplers'][channel['sampler']]
            times=values[sampler['input']];output=values[sampler['output']]
            if not all(a[0]<b[0] for a,b in zip(times,times[1:])):
                raise ValueError('non-increasing animation time')
            width=1
            if channel['target']['path']=='weights':
                node=document['nodes'][channel['target']['node']]
                width=len(document['meshes'][node['mesh']]['primitives'][0]['targets'])
            if len(output)!=len(times)*width:raise ValueError('animation output count mismatch')
    return dict(file=Path(path).name,accessors_checked=len(values),
        animation_channels=sum(len(c['channels']) for c in document.get('animations',[])),
        motion_binding=document['animations'][0]['extras'].get('source_motion_binding'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extracted');parser.add_argument('output');parser.add_argument('--snapshot')
    parser.add_argument('--gltf',action='append',default=[])
    args=parser.parse_args();result=audit(args.extracted,args.snapshot)
    inputs=list(Path(args.extracted).rglob('*.cht'))+list(Path(args.extracted).rglob('*.pmt'))+args.gltf
    if args.snapshot:inputs.append(args.snapshot)
    result['gltf_exports']=[check_gltf(path) for path in args.gltf]
    write_output(args.output,json.dumps(result,indent=2).encode(),inputs)
    print('CHT files:',result['total_files'],'resolved:',result['resolved'],'unresolved:',len(result['unresolved']))


if __name__=='__main__':main()
