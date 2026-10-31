#!/usr/bin/env python3
"""Check native constant/missing-node blend paths using an instruction interpreter."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import struct
from arika_actions import c_elf_reader,REFERENCE_SHA256
from arika_face_player import f32
from arika_pose import apply_bone,apply_bone_pair
from arika_import import write_output
from validate_cht_mapping import check_gltf


def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floating(v):return struct.unpack('<f',struct.pack('<I',v))[0]


def native_bone(reader,current,target,rest,mask,weight,scale_enabled,pair=None,blend_active=True):
    memory={};r=[0]*32;f=[0]*32;acc=0.0;condition=False
    helper=0x1000;node=0x2000;ref=0x3000;runtime=0x4000;raw=0x5000;pool=0x9000
    def put(address,value,size=4):
        for i,b in enumerate((value&((1<<(8*size))-1)).to_bytes(size,'little')):memory[address+i]=b
    def get(address,size=4):
        return int.from_bytes(bytes(memory[address+i] if address+i in memory else reader.read(address+i,1)[0] for i in range(size)),'little')
    def vector(address,values):
        for i,v in enumerate(values):put(address+i*4,bits(f32(v)))
    put(helper+4,0x6000);put(helper+8,bits(weight))
    vector(node+0x30,current['translation']+[1]);vector(node+0x40,current['rotation']);vector(node+0x60,current['scale']+[1])
    vector(0x6000,rest['translation']+[1]);vector(0x6010,rest['rotation'])
    put(ref,runtime);put(ref+8,0x7000);put(0x7000,0 if target else 0xFFFF,2)
    put(runtime+52,raw);put(raw+20,0x8000);put(raw+24,pool)
    for offset,value in ((0,0),(2,0),(4,1),(6,2)):put(0x8000+offset,value,2)
    if target:
        vector(pool,target['translation']+[1]);vector(pool+16,target['rotation']);vector(pool+32,target['scale']+[1])
    r[7]=ref;r[8]=0xA000;r[9]=mask
    if scale_enabled:
        r[21]=helper;r[20]=node;r[19]=0xA000;pc=0x1B5CB0;stops=(0x1B6354,0x1B6358)
    else:
        r[17]=helper;r[6]=node;pc=0x1B2E58;stops=(0x1B3338,0x1B333C)
    if pair is None and not blend_active:
        r[4]=helper;r[5]=0;r[6]=0 if scale_enabled else node
        if scale_enabled:
            r[20]=node;r[19]=0xA000;pc=0x1B7578;stops=(0x1B78E8,0x1B78EC)
        else:pc=0x1B3F8C;stops=(0x1B41B0,0x1B41B4)
    if pair is not None:
        second,fraction=pair
        ref2=0xB000;runtime2=0xC000;raw2=0xD000;pool2=0xE000;desc2=0xF000
        put(ref2,runtime2);put(ref2+8,0xB100);put(0xB100,0 if second else 0xFFFF,2)
        put(runtime2+52,raw2);put(raw2+20,desc2);put(raw2+24,pool2)
        for offset,value in ((0,0),(2,0),(4,1),(6,2)):put(desc2+offset,value,2)
        if second:
            vector(pool2,second['translation']+[1]);vector(pool2+16,second['rotation']);vector(pool2+32,second['scale']+[1])
        r[6]=0;r[7]=ref;r[8]=0xA000;r[9]=ref2;r[10]=0xA100;r[11]=mask;f[12]=bits(f32(fraction));r[29]=0x11000
        if scale_enabled:
            r[21]=helper;r[20]=node;r[19]=0xA000;r[18]=0xA100;r[17]=mask
            pc=0x1B44B4 if blend_active else 0x1B6400
            stops=(0x1B5C04,0x1B5C08) if blend_active else (0x1B7500,0x1B7504)
        else:
            r[19]=helper;r[18]=node;r[17]=0xA100
            pc=0x1B1B48 if blend_active else 0x1B33B8
            stops=(0x1B2C40,0x1B2C44) if blend_active else (0x1B3F3C,0x1B3F40)
    pending=None;calls=0
    for _ in range(2000):
        if pc in stops:
            return {p:[floating(get(node+offset+i*4)) for i in range(n)] for p,offset,n in [('translation',0x30,3),('rotation',0x40,4),('scale',0x60,3)]},calls
        if pc in (0x185E08,0x185C78,0x19D150):
            if pc==0x19D150:
                body=[get(r[5]+i,1) for i in range(16)]
                for i,b in enumerate(body):put(r[4]+i,b,1)
            else:
                argument=floating(f[12]);value=math.acos(argument) if pc==0x185E08 else math.sin(argument)
                f[0]=bits(f32(value));calls+=1
            pc=r[31];continue
        word=struct.unpack('<I',reader.read(pc,4))[0]
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;sh=(word>>6)&31
        imm=word&65535;signed=imm if imm<32768 else imm-65536;old=pending;pending=None;skip=False
        if op==0:
            fn=word&63
            if fn==0:r[rd]=r[rt]<<sh
            elif fn in (0x21,0x2D):r[rd]=r[rs]+r[rt]
            elif fn==0x24:r[rd]=r[rs]&r[rt]
            elif fn==0x25:r[rd]=r[rs]|r[rt]
            else:raise ValueError('unsupported pose SPECIAL at '+hex(pc))
        elif op==15:r[rt]=imm<<16
        elif op in (9,25):r[rt]=r[rs]+signed
        elif op==12:r[rt]=r[rs]&imm
        elif op==13:r[rt]=r[rs]|imm
        elif op in (33,35,37):
            v=get((r[rs]+signed)&0xFFFFFFFF,4 if op==35 else 2)
            r[rt]=v-65536 if op==33 and v&0x8000 else v
        elif op==43:put((r[rs]+signed)&0xFFFFFFFF,r[rt])
        elif op==31: # EE SQ: constant paths spill integer pointers to the stack.
            address=(r[rs]+signed)&0xFFFFFFFF
            put(address,r[rt],16)
        elif op==30:r[rt]=get((r[rs]+signed)&0xFFFFFFFF,4) # LQ pointer reload; upper lanes are unused.
        elif op==55 and old in stops:pass # Epilogue restore in a taken branch delay slot.
        elif op in (2,3):
            if op==3:r[31]=pc+8
            pending=((pc+4)&0xF0000000)|((word&0x3FFFFFF)<<2)
        elif op==1:
            if rt!=0:raise ValueError('unsupported pose regimm')
            pending=pc+4+signed*4 if r[rs]&0x80000000 else pc+8
        elif op in (4,5,20,21):
            taken=(r[rs]==r[rt])==(op in (4,20))
            if op in (20,21) and not taken:skip=True
            else:pending=pc+4+signed*4 if taken else pc+8
        elif op==49:f[rt]=get((r[rs]+signed)&0xFFFFFFFF)
        elif op==57:put((r[rs]+signed)&0xFFFFFFFF,f[rt])
        elif op==17:
            if rs==4:f[rd]=r[rt]
            elif rs==8:
                taken=condition==bool(rt&1)
                if rt&2 and not taken:skip=True
                else:pending=pc+4+signed*4 if taken else pc+8
            elif rs==16:
                a=floating(f[rd]);b=floating(f[rt]);fd=sh;fn=word&63
                if fn==0:f[fd]=bits(f32(a+b))
                elif fn==1:f[fd]=bits(f32(a-b))
                elif fn==2:f[fd]=bits(f32(a*b))
                elif fn==3:f[fd]=bits(f32(a/b))
                elif fn==6:f[fd]=f[rd]
                elif fn==7:f[fd]=f[rd]^0x80000000
                elif fn==0x18:acc=f32(a+b)
                elif fn==0x1A:acc=f32(a*b)
                elif fn==0x1E:acc=f32(acc+f32(a*b))
                elif fn==0x1C:f[fd]=bits(f32(acc+f32(a*b)))
                elif fn==0x32:condition=a==b
                elif fn==0x34:condition=a<b
                elif fn==0x36:condition=a<=b
                else:raise ValueError('unsupported pose FPU at '+hex(pc))
            else:raise ValueError('unsupported pose COP1 at '+hex(pc))
        else:raise ValueError('unsupported pose opcode at '+hex(pc))
        r=[v&0xFFFFFFFF for v in r];r[0]=0;pc=old if old is not None else pc+(8 if skip else 4)
    raise ValueError('pose interpreter step limit')


def audit(data):
    if hashlib.sha256(data).hexdigest()!=REFERENCE_SHA256:raise ValueError('reference ELF required')
    reader=c_elf_reader(data);rng=random.Random(0x54161);checked=0;paired=0;trig=0
    def quaternion():
        q=[rng.uniform(-1,1) for _ in range(4)];length=math.sqrt(sum(v*v for v in q));return [f32(v/length) for v in q]
    for case in range(20):
        current=dict(translation=[f32(rng.uniform(-100,100)) for _ in range(3)],rotation=quaternion(),scale=[f32(rng.uniform(.2,3)) for _ in range(3)])
        rest=dict(translation=[1.,2.,3.],rotation=[0.,0.,0.,1.],scale=[2.,2.,2.])
        target=dict(translation=[f32(rng.uniform(-100,100)) for _ in range(3)],rotation=quaternion(),scale=[f32(rng.uniform(.2,3)) for _ in range(3)])
        if case==0:target['rotation']=list(current['rotation'])
        if case==1:target['rotation']=[-v for v in current['rotation']]
        if case==2:
            q=[current['rotation'][0]+.0001]+current['rotation'][1:];n=math.sqrt(sum(v*v for v in q));target['rotation']=[f32(v/n) for v in q]
        for mask in range(8):
            for present in (False,True):
                for scale in (False,True):
                    for weight in (0,.1,.5,.9,1):
                        expected,calls=native_bone(reader,current,target if present else None,rest,mask,f32(weight),scale)
                        actual=apply_bone(current,target if present else None,rest,mask,weight,True,scale)
                        for path in expected:
                            if list(map(bits,expected[path]))!=list(map(bits,actual[path])):
                                raise ValueError('native pose mismatch '+repr((case,mask,present,scale,weight,path,actual[path],expected[path])))
                        checked+=1;trig+=calls
        second=dict(translation=[f32(rng.uniform(-100,100)) for _ in range(3)],rotation=quaternion(),scale=[f32(rng.uniform(.2,3)) for _ in range(3)])
        if case==0:second=copy.deepcopy(target)
        if case==1:second['rotation']=[-v for v in target['rotation']]
        if case==2:
            q=[target['rotation'][0]+.0001]+target['rotation'][1:];n=math.sqrt(sum(v*v for v in q));second['rotation']=[f32(v/n) for v in q]
        for mask in range(8):
            for first_present,second_present in ((False,False),(False,True),(True,False),(True,True)):
                first=target if first_present else None;other=second if second_present else None
                for scale in (False,True):
                    for active,weights in ((False,(1,)),(True,(0,.5,1))):
                        for weight in weights:
                            for fraction in (0,.1,.5,.9,1):
                                expected,calls=native_bone(reader,current,first,rest,mask,f32(weight),scale,(other,fraction),active)
                                actual=apply_bone_pair(current,first,other,rest,mask,fraction,weight,active,scale)
                                for path in expected:
                                    if list(map(bits,expected[path]))!=list(map(bits,actual[path])):
                                        raise ValueError('native paired pose mismatch '+repr((case,mask,first_present,second_present,scale,active,weight,fraction,path,actual[path],expected[path])))
                                paired+=1;trig+=calls
    return dict(format='ARIKA_NATIVE_POSE_VALIDATION',elf_sha256=REFERENCE_SHA256,bone_cases_checked=checked,host_trig_calls=trig,
        paired_bone_cases_checked=paired,
        scope='Original one-source paths 0x1B2E20/0x1B5C60 and two-source paths 0x1B1B00/0x1B3370/0x1B4450/0x1B63A0, constant tracks and missing nodes, interpreted with IEEE float32 accumulator arithmetic. Native sin/acos/memcpy calls are substituted with host functions. This is not hardware or native-libm bit equivalence; animated-track sampling and full action orchestration are separate.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf');p.add_argument('output');p.add_argument('--gltf',action='append',default=[]);args=p.parse_args()
    result=audit(Path(args.elf).read_bytes());result['gltf_exports']=[check_gltf(path) for path in args.gltf]
    write_output(args.output,json.dumps(result,indent=2).encode(),[args.elf]+args.gltf)
    print('Native bone cases:',result['bone_cases_checked'])
    print('Native paired bone cases:',result['paired_bone_cases_checked'])


if __name__=='__main__':main()
