#!/usr/bin/env python3
"""Compare supported transitions with the original MIPS prefix and audit previews."""
import argparse
import json
from pathlib import Path
import struct

from arika_actions import c_elf_reader, common_tables
from arika_cht import parse_cht, load_banks, lookup, resolve
import arika_models as models
from arika_sequence import next_segment,plan_sequence,sample_sequence
from arika_import import write_output
from validate_cht_mapping import check_gltf


def native_transition(reader,records,index):
    # Only the integer branch-selection prefix of 0x1D7120 is executed.
    # Stop before root-state reset, motion lookup, or any external call.
    memory={};registers=[0]*32;obj=0x1000;table=0x2000
    def put(address,body):
        for i,byte in enumerate(body):memory[address+i]=byte
    def read(address,size):return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
    put(obj+0x88,struct.pack('<I',table));put(obj+0x90,struct.pack('<I',index))
    for i,r in enumerate(records):put(table+20*i,struct.pack('<HHfffI',r['motion_id'],r['variant'],r['speed'],r['start_frame'],r['end_frame'],r['flags']))
    registers[4]=registers[17]=obj
    pc=0x1D7140;pending=None
    for _ in range(150):
        if pc in (0x1D71C0,0x1D72D0,0x1D7404):
            value=read(obj+0x90,4)
            return None if value==0xFFFFFFFF else value
        word=struct.unpack('<I',reader.read(pc,4))[0]
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;shift=(word>>6)&31
        immediate=word&0xFFFF;signed=immediate if immediate<0x8000 else immediate-0x10000
        previous=pending;pending=None
        if op==0:
            function=word&63
            if function==0:registers[rd]=registers[rt]<<shift
            elif function in (0x21,0x2D):registers[rd]=registers[rs]+registers[rt]
            elif function==0x24:registers[rd]=registers[rs]&registers[rt]
            else:raise ValueError('unsupported SPECIAL in transition verifier')
        elif op==15:registers[rt]=immediate<<16
        elif op in (9,25):registers[rt]=registers[rs]+signed
        elif op==12:registers[rt]=registers[rs]&immediate
        elif op==13:registers[rt]=registers[rs]|immediate
        elif op in (35,37):registers[rt]=read((registers[rs]+signed)&0xFFFFFFFF,4 if op==35 else 2)
        elif op in (40,43):
            size=1 if op==40 else 4
            put((registers[rs]+signed)&0xFFFFFFFF,(registers[rt]&((1<<(size*8))-1)).to_bytes(size,'little'))
        elif op in (4,5):
            equal=registers[rs]==registers[rt]
            pending=pc+4+signed*4 if equal==(op==4) else pc+8
        elif word in (0x4483A000,0x46006546):pass  # float registers do not select the branch
        else:raise ValueError('unsupported opcode at 0x%X'%pc)
        registers=[r&0xFFFFFFFF for r in registers];registers[0]=0
        pc=previous if previous is not None else pc+4
    raise ValueError('transition verifier step limit')


def audit(elf,root):
    data=Path(elf).read_bytes();tables=common_tables(data);reader=c_elf_reader(data)
    checked=0;unsupported=[]
    for action in tables['actions']:
        for index,record in enumerate(action['records']):
            try:expected,_=next_segment(action['records'],index)
            except ValueError as error:
                unsupported.append(dict(slot=action['slot'],segment=index,reason=str(error)));continue
            actual=native_transition(reader,action['records'],index)
            if actual!=expected:raise ValueError('native transition mismatch')
            checked+=1
    # Exercise jump targets and precedence combinations absent from common defaults.
    synthetic=0
    for index in range(4):
        for flags in [0,0x10000,0x20000,0x30000]+[base|target for base in (0x40000,0x50000,0x60000,0x70000) for target in range(4)]:
            records=[dict(motion_id=i,variant=0,speed=1,start_frame=0,end_frame=-1,flags=0x10000) for i in range(4)]
            records[index]['flags']=flags
            try:expected,_=next_segment(records,index)
            except ValueError:continue
            if native_transition(reader,records,index)!=expected:raise ValueError('synthetic transition mismatch')
            synthetic+=1
    root=Path(root);common=root/'ply/p00/p00x.pmt';package_cache={};characters=[]
    for path in sorted(root.glob('ply/p*/p*act.cht')):
        cht=parse_cht(path.read_bytes());banks=load_banks(['0='+str(path.with_suffix('.pmt')),'1='+str(common)])
        def resolver(record):
            binding=resolve(lookup(cht,record['motion_id'],record['variant']),banks)
            if binding['status']!='resolved':raise ValueError(binding['status'])
            package=binding['package']
            if package not in package_cache:package_cache[package]=models.parse_motions(Path(package).read_bytes())['motions']
            return package_cache[package][binding['package_index']],binding
        passed=0;failed=[]
        for action in tables['actions']:
            try:
                plan,_=plan_sequence(action['records'],resolver)
                times={0,.1,1,3,10}
                for entry in plan['segments']:
                    for time in (entry['start_time'],entry['end_time']):times.update((max(0,time-1e-6),time,time+1e-6))
                samples=sample_sequence(plan,sorted(times))
                if not all(0<=s['motion_time'] for s in samples):raise ValueError('negative motion time')
                passed+=1
            except ValueError as error:failed.append(dict(slot=action['slot'],reason=str(error)))
        characters.append(dict(character=path.parent.name,planned=passed,unresolved=failed))
    return dict(format='ARIKA_SEQUENCE_VALIDATION',elf_sha256=tables['elf_sha256'],
        common_transitions_checked=checked,synthetic_transitions_checked=synthetic,unsupported_transitions=unsupported,
        characters=characters,scope='MIPS prefix check validates branch/index selection only. Timeline sampling is an authored-frame preview, not native tick/blend emulation.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf');p.add_argument('extracted');p.add_argument('output')
    p.add_argument('--gltf',action='append',default=[]);args=p.parse_args()
    result=audit(args.elf,args.extracted);result['gltf_exports']=[check_gltf(path) for path in args.gltf]
    write_output(args.output,json.dumps(result,indent=2).encode(),[args.elf]+args.gltf+list(Path(args.extracted).rglob('*.cht'))+list(Path(args.extracted).rglob('*.pmt')))
    print('Native transitions:',result['common_transitions_checked'],'synthetic:',result['synthetic_transitions_checked'])
    print('Plans:',sum(c['planned'] for c in result['characters']),'characters:',len(result['characters']))


if __name__=='__main__':main()
