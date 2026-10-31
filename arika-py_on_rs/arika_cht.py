#!/usr/bin/env python3
"""Read CHT logical-motion mappings without following relocated runtime pointers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from arika_models import require
from arika_dat import motion_archive
from arika_import import write_output


def parse_cht(data):
    require(len(data)>=20 and data[:8]==b'\0\0\1\0CHT ', 'expected reference-version CHT')
    cursor=20

    def take(size):
        nonlocal cursor
        require(size>=0 and cursor+size<=len(data), 'truncated CHT block at 0x%X'%cursor)
        offset=cursor
        cursor+=size
        return offset

    def align():
        take((-cursor)%16)

    count=struct.unpack_from('<I',data,16)[0]
    require(count<=0x10000 and count*32<=len(data)-cursor, 'invalid CHT name count')
    names=[]
    for _ in range(count):
        block=data[take(32):cursor]
        require(b'\0' in block, 'unterminated CHT motion name')
        names.append(block.split(b'\0',1)[0].decode('cp932'))
    flags=struct.unpack_from('<18I',data,take(72))
    for flag in flags:
        align()
        if flag:
            take(32)
    directory=take(4000)
    actions=[]
    while cursor<len(data):
        offset=take(12)
        logical_id,variants,_=struct.unpack_from('<3I',data,offset)
        require(logical_id<1000 and variants<=(len(data)-cursor)//136, 'invalid CHT action/count')
        base=take(variants*136)
        records=[]
        for variant in range(variants):
            at=base+variant*136
            name_index,bank=struct.unpack_from('<HH',data,at+4)
            require(name_index<len(names), 'CHT name index out of range')
            blocks=dict(type_68=0,type_36=0,type_32=0,type_12=0)
            # Native 0x2AC930: 16x68, 8x36, then 8x12 children per variant.
            for field in range(8,72,4):
                if struct.unpack_from('<I',data,at+field)[0]:
                    child=take(68);blocks['type_68']+=1;align()
                    for subfield in range(36,68,4):
                        if struct.unpack_from('<I',data,child+subfield)[0]:
                            take(32);blocks['type_32']+=1
            for field in range(104,136,4):
                if struct.unpack_from('<I',data,at+field)[0]:
                    child=take(36);blocks['type_36']+=1;align()
                    for subfield in range(4,36,4):
                        if struct.unpack_from('<I',data,child+subfield)[0]:
                            take(32);blocks['type_32']+=1
            for field in range(72,104,4):
                if struct.unpack_from('<I',data,at+field)[0]:
                    take(12);blocks['type_12']+=1
            records.append(dict(variant=variant,offset=at,name_index=name_index,
                motion_name=names[name_index],resource_bank=bank,child_blocks=blocks))
        actions.append(dict(motion_id=logical_id,offset=offset,variants=records))
    return dict(format='ARIKA_CHT_MOTIONS',source_sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),name_table=names,runtime_directory_offset=directory,actions=actions,
        scope='Logical motion ID/variant mapping. Collision block extents are walked, not interpreted. Duplicate IDs use the last entry at runtime.')


def lookup(document,motion_id,variant):
    require(type(motion_id) is int and 0<=motion_id<1000, 'motion ID must be 0..999')
    require(type(variant) is int and variant>=0, 'variant must be nonnegative')
    action=next((a for a in reversed(document['actions']) if a['motion_id']==motion_id),None)
    require(action is not None, 'logical motion ID is absent from CHT')
    require(variant<len(action['variants']), 'motion variant is absent from CHT')
    return action['variants'][variant]


def runtime_motion_name(name):
    # 0x1B12F0: copy 15 bytes, terminate byte 15, replace dots with NUL.
    return name.encode('cp932')[:15].split(b'.',1)[0].decode('cp932')


def load_banks(specifications):
    banks={}
    for specification in specifications:
        key,separator,path=specification.partition('=')
        require(separator and key.isdecimal() and path, 'bank must be INDEX=package.pmt')
        index=int(key)
        require(0<=index<=0xFFFF and index not in banks, 'invalid or duplicate bank index')
        data=Path(path).read_bytes();package=motion_archive(data);names={}
        for motion in package['motions']:
            names.setdefault(runtime_motion_name(motion['name']),motion)
        banks[index]=dict(path=str(Path(path)),sha256=hashlib.sha256(data).hexdigest(),names=names)
    return banks


def resolve(record,banks):
    result=dict(record)
    bank=banks.get(record['resource_bank'])
    if bank is None:
        result.update(status='missing_bank')
        return result
    result.update(package=bank['path'],package_sha256=bank['sha256'])
    motion=bank['names'].get(record['motion_name'])
    if motion is None:
        result.update(status='missing_motion')
    else:
        result.update(status='resolved',package_index=motion['index'],package_motion=motion['name'])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    for command in ('json','map'):
        p=subs.add_parser(command);p.add_argument('cht');p.add_argument('output')
        if command=='map':p.add_argument('--bank',action='append',required=True)
    args=parser.parse_args()
    try:
        result=parse_cht(Path(args.cht).read_bytes());inputs=[args.cht]
        if args.command=='map':
            banks=load_banks(args.bank);inputs += [b['path'] for b in banks.values()]
            for action in result['actions']:
                action['variants']=[resolve(v,banks) for v in action['variants']]
        write_output(args.output,json.dumps(result,indent=2).encode(),inputs)
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
