#!/usr/bin/env python3
"""Compare scalar clock steps against the original R5900 timing prefix."""
import argparse
import hashlib
import itertools
import json
import random
from pathlib import Path
import struct
from arika_actions import c_elf_reader,REFERENCE_SHA256
from arika_clock import c_native_clock,ACTIVE,DIRTY,PAUSED
from arika_face_player import f32
from arika_import import write_output


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def floating(value):return struct.unpack('<f',struct.pack('<I',value))[0]


def native_blend_weight(reader,remaining,total):
    if remaining<=0:return 1.0
    f=[0]*32;f[0]=bits(1);f[1]=bits(total);f[2]=bits(remaining)
    for pc in (0x1B8C34,0x1B8C3C):
        word=struct.unpack('<I',reader.read(pc,4))[0]
        if word>>26!=17 or (word>>21)&31!=16:raise ValueError('unexpected blend coefficient opcode')
        ft=(word>>16)&31;fs=(word>>11)&31;fd=(word>>6)&31;fn=word&63
        if fn==3:value=floating(f[fs])/floating(f[ft])
        elif fn==1:value=floating(f[fs])-floating(f[ft])
        else:raise ValueError('unexpected blend coefficient operation')
        f[fd]=bits(f32(value))
    return floating(f[0])


def native_step(reader,clock,delta,include_evaluation_flags=False):
    memory={};r=[0]*32;f=[0]*32;condition=False;obj=0x1000
    def put(address,value,size=4):
        for i,byte in enumerate((value&((1<<(8*size))-1)).to_bytes(size,'little')):memory[address+i]=byte
    def get(address,size=4):return int.from_bytes(bytes(memory.get(address+i,0) for i in range(size)),'little')
    put(obj,clock.m_flags)
    for offset,value in [(4,clock.m_position),(8,clock.m_start),(12,clock.m_end),(16,clock.m_baseline),
        (20,clock.m_stop_timer),(24,clock.m_blend_total),(28,clock.m_blend_remaining),(32,clock.m_speed)]:put(obj+offset,bits(value))
    put(obj+40,0x2000);put(0x2000,0x3000);put(0x3000+60,bits(clock.m_frame_period));put(0x3000+52,0x4000)
    put(0x4000+52,clock.m_scale_channels,2)
    r[4]=r[18]=obj;r[2]=ACTIVE  # lui v0,0x100 from the skipped save prologue
    f[12]=bits(f32(delta));pc=0x1B84E0;pending=None
    for _ in range(200000):
        if pc in (0x1B89EC,0x1B89F4):
            carry=f32(delta) if pc==0x1B89EC else 0.0
            return dict(position=clock.m_position,stop_timer=clock.m_stop_timer,blend_remaining=clock.m_blend_remaining,
                flags=clock.m_flags,carry=carry,wrap_fraction=None)
        if pc==0x1B8948:
            flags=get(obj)&~DIRTY
            if r[22]:flags&=0xF
            result=dict(position=floating(get(obj+4)),stop_timer=floating(get(obj+20)),blend_remaining=floating(get(obj+28)),
                flags=flags,carry=floating(f[22]),wrap_fraction=floating(f[21]) if floating(f[21])>=0 else None)
            if include_evaluation_flags:result['evaluation_flags']=get(obj)
            return result
        word=struct.unpack('<I',reader.read(pc,4))[0]
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;shift=(word>>6)&31
        imm=word&65535;signed=imm if imm<32768 else imm-65536;previous=pending;pending=None;skip=False
        if op==0:
            fn=word&63
            if fn==0:r[rd]=r[rt]<<shift
            elif fn in (0x21,0x2D):r[rd]=r[rs]+r[rt]
            elif fn==0x24:r[rd]=r[rs]&r[rt]
            elif fn==0x25:r[rd]=r[rs]|r[rt]
            else:raise ValueError('unsupported integer timing instruction at '+hex(pc))
        elif op==15:r[rt]=imm<<16
        elif op in (9,25):r[rt]=r[rs]+signed
        elif op==12:r[rt]=r[rs]&imm
        elif op==13:r[rt]=r[rs]|imm
        elif op in (35,37):r[rt]=get((r[rs]+signed)&0xFFFFFFFF,4 if op==35 else 2)
        elif op in (40,41,43):put((r[rs]+signed)&0xFFFFFFFF,r[rt],{40:1,41:2,43:4}[op])
        elif op in (4,5,20,21):
            taken=(r[rs]==r[rt])==(op in (4,20))
            if op in (20,21) and not taken:skip=True
            else:pending=pc+4+4*signed if taken else pc+8
        elif op==49:f[rt]=get((r[rs]+signed)&0xFFFFFFFF)
        elif op==57:put((r[rs]+signed)&0xFFFFFFFF,f[rt])
        elif op==17:
            if rs==4:f[rd]=r[rt]
            elif rs==0:r[rt]=f[rd]
            elif rs==8:
                taken=condition==bool(rt&1)
                if rt&2 and not taken:skip=True
                else:pending=pc+4+4*signed if taken else pc+8
            elif rs==16:
                ft=rt;fs=rd;fd=shift;fn=word&63;a=floating(f[fs]);b=floating(f[ft])
                if fn==0:f[fd]=bits(f32(a+b))
                elif fn==1:f[fd]=bits(f32(a-b))
                elif fn==2:f[fd]=bits(f32(a*b))
                elif fn==3:f[fd]=bits(f32(a/b))
                elif fn==6:f[fd]=f[fs]
                elif fn==7:f[fd]=f[fs]^0x80000000
                elif fn==0x34:condition=a<b
                elif fn==0x36:condition=a<=b
                elif fn==0x32:condition=a==b
                else:raise ValueError('unsupported FPU timing instruction at '+hex(pc))
            else:raise ValueError('unsupported COP1 timing instruction at '+hex(pc))
        else:raise ValueError('unsupported timing opcode at '+hex(pc))
        r=[v&0xFFFFFFFF for v in r];r[0]=0
        pc=previous if previous is not None else pc+(8 if skip else 4)
    raise ValueError('native timing prefix step limit')


def compare(reader,clock,delta):
    expected=native_step(reader,clock,delta);actual=clock.step(delta)
    for key,value in expected.items():
        if isinstance(value,float):
            if bits(actual[key])!=bits(value):raise ValueError('clock mismatch '+key+': '+repr((actual[key],value)))
        elif actual[key]!=value:raise ValueError('clock mismatch '+key+': '+repr((actual[key],value)))
    if bits(actual['blend_weight'])!=bits(native_blend_weight(reader,expected['blend_remaining'],clock.m_blend_total)):
        raise ValueError('blend coefficient mismatch')


def audit(data):
    if hashlib.sha256(data).hexdigest()!=REFERENCE_SHA256:raise ValueError('reference ELF required')
    reader=c_elf_reader(data);checked=0;setups=0
    for fps,speed,reverse,loop,blend,stop_after,scale in itertools.product(
        (25,60),(0,.5,1,2),(False,True),(False,True),(0,.17),(-1,.08),(0,1)):
        clock=c_native_clock(fps,8,1,6,speed,blend,reverse,loop,stop_after,scale)
        setups+=1
        for delta in (0,-.01,1/120,1/60,.04,.2,.7):
            compare(reader,clock,delta);checked+=1
    # Repeated active updates exercise float32 accumulation and wrap flags.
    for reverse,loop in itertools.product((False,True),repeat=2):
        clock=c_native_clock(60,17,0,-1,1,.17,reverse,loop)
        for _ in range(160):compare(reader,clock,1/60);checked+=1
    for active,paused in itertools.product((False,True),repeat=2):
        clock=c_native_clock(60,20)
        if not active:clock.m_flags&=~ACTIVE
        if paused:clock.m_flags|=PAUSED
        for delta in (0,-.1,.1):compare(reader,clock,delta);checked+=1
    rng=random.Random(0x54161)
    for _ in range(200):
        clock=c_native_clock(rng.choice((23.976,29.97,59.94,120)),rng.randrange(5,200),
            rng.choice((0,.25,1.5)),rng.choice((-1,3.75)),rng.choice((.01,.333,1.5,3)),
            rng.choice((0,.07,.17)),rng.choice((False,True)),rng.choice((False,True)),
            rng.choice((-1,.07,.3)),rng.randrange(2))
        setups+=1
        for _ in range(10):compare(reader,clock,rng.choice((1/120,1/60,.03,.11)));checked+=1
    return dict(format='ARIKA_NATIVE_CLOCK_VALIDATION',elf_sha256=REFERENCE_SHA256,
        parameter_setups=setups,steps_checked=checked,
        fields=['position','stop_timer','blend_remaining','flags','carry','wrap_fraction','blend_weight'],
        scope='Bitwise scalar comparison with an IEEE-float32 interpreter executing the original timing prefix through 0x1B8948, early exits, and coefficient arithmetic at 0x1B8C34/3C. This is not a PS2 hardware capture or full R5900 FPU emulator. Pose sampling, motion-list callbacks and complete action orchestration are excluded. Final flags model subsequent dirty/terminal cleanup. Setup translation is inspected separately, not executed by this prefix oracle.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf');p.add_argument('output');args=p.parse_args()
    result=audit(Path(args.elf).read_bytes());write_output(args.output,json.dumps(result,indent=2).encode(),[args.elf]);print('Checked native clock steps:',result['steps_checked'])


if __name__=='__main__':main()
