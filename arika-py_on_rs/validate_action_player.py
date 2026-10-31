#!/usr/bin/env python3
"""Compare automatic constant-pose chains with composed instruction oracles."""
import argparse
import copy
import json
from pathlib import Path
import struct
from arika_actions import c_elf_reader,REFERENCE_SHA256
from arika_action_clock import startup_control
from arika_action_player import c_action_player
from arika_clock import c_native_clock,DIRTY
from arika_face_player import f32
from arika_import import write_output
from validate_native_clock import native_step,native_blend_weight
from validate_native_pose import native_bone,bits,floating
from validate_action_clock import native_startup
from validate_cht_mapping import check_gltf
import hashlib
import math


def native_dispatch(reader,flags,remaining):
    r=[0]*32;f=[0]*32;r[18]=0x1000;f[20]=f[21]=bits(-1.);condition=False;pc=0x1B8948;pending=None
    memory={0x1000:flags,0x101C:bits(remaining)}
    for _ in range(40):
        if pc==0x1B8B94:return 'helper'
        if pc==0x1B8F50:return 'animated_channels'
        word=struct.unpack('<I',reader.read(pc,4))[0];op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31
        imm=word&65535;signed=imm if imm<32768 else imm-65536;old=pending;pending=None
        if word==0:pass
        elif op==0 and word&63==0x24:r[rd]=r[rs]&r[rt]
        elif op==35:r[rt]=memory[r[rs]+signed]
        elif op==15:r[rt]=imm<<16
        elif op==5:pending=pc+4+signed*4 if r[rs]!=r[rt] else pc+8
        elif op==49:f[rt]=memory[r[rs]+signed]
        elif op==17:
            if rs==4:f[rd]=r[rt]
            elif rs==8:pending=pc+4+signed*4 if condition==bool(rt&1) else pc+8
            elif rs==16:
                a=floating(f[rd]);b=floating(f[rt]);fn=word&63
                if fn==0x34:condition=a<b
                elif fn==0x36:condition=a<=b
                else:raise ValueError('unsupported dispatch FPU')
            else:raise ValueError('unsupported dispatch COP1')
        else:raise ValueError('unsupported dispatch opcode at '+hex(pc))
        r[0]=0;pc=old if old is not None else pc+4
    raise ValueError('dispatch interpreter limit')


def fixture(flags,mask,scale,speed):
    rest=dict(translation=[1.,2.,3.],rotation=[0.,0.,0.,1.],scale=[2.,2.,2.])
    model=dict(nodes=[dict(name='bone',**rest)])
    records=[dict(motion_id=i,variant=0,speed=speed,start_frame=0,end_frame=-1,flags=f) for i,f in enumerate((flags,0x10000))]
    targets=[dict(translation=[8.,4.,-2.],rotation=[0.,1.,0.,0.],scale=[3.,1.,2.]),
             dict(translation=[20.,-2.,5.],rotation=[1.,0.,0.,0.],scale=[1.,3.,4.])]
    segments={}
    for i,target in enumerate(targets):
        motion=dict(fps=2,frame_count=3,last_frame_time=1.,duration=1.5,channel_counts=[0,0,int(scale)],
            nodes=[dict(name='bone',tracks={p:dict(animated=False,times=[0.],values=[v]) for p,v in target.items()})])
        segments[i]=dict(record=records[i],motion=motion,package=dict(bones=[dict(name='bone',flags=mask)]),control=startup_control(records,i))
    return model,segments,records,targets,rest


def audit(data):
    if hashlib.sha256(data).hexdigest()!=REFERENCE_SHA256:raise ValueError('reference ELF required')
    reader=c_elf_reader(data);runs=steps=evaluations=0
    for flags in (0,0x200000,0x20000,0x240001):
        for mask in range(8):
            for scale in (False,True):
                for speed in (.5,2.):
                    model,segments,records,targets,rest=fixture(flags,mask,scale,speed)
                    actual=c_action_player(model,segments,initial_blend=2.)
                    clock=c_native_clock(2,3,speed=speed,blend=2.,scale_channels=int(scale));pose=copy.deepcopy(rest)
                    index=0;finished=False;runs+=1
                    for delta in (.125,.25,.7,1.75,3.25,.1):
                        trace=[];remaining=f32(delta)
                        if not finished:
                            for _ in range(100):
                                state=native_step(reader,clock,remaining,include_evaluation_flags=True)
                                if 'evaluation_flags' in state:
                                    mode=native_dispatch(reader,state['evaluation_flags'],state['blend_remaining'])
                                    weight=native_blend_weight(reader,state['blend_remaining'],clock.m_blend_total)
                                    active=bool(state['flags']&0x1000000)
                                    if mode=='helper':pose,_=native_bone(reader,pose,targets[index],rest,mask,weight,scale,blend_active=state['blend_remaining']>0)
                                    trace.append(dict(segment=index,motion_time=min(clock.m_end,max(clock.m_start,state['position'])),
                                        blend_weight=weight,blend_active=state['blend_remaining']>0,terminal=not active,pose_dispatch=mode));evaluations+=1
                                else:active=bool(clock.m_flags&0x1000000)
                                clock.m_position=state['position'];clock.m_flags=state['flags'];clock.m_stop_timer=state['stop_timer'];clock.m_blend_remaining=state['blend_remaining']
                                if active:break
                                call=native_startup(reader,records,index)
                                if call is None:finished=True;break
                                index=call['segment'];args=call['settings'];old=clock
                                clock=c_native_clock(2,3,start=args['start_frame'],end=args['end_frame'],speed=args['speed'],blend=args['blend_request'],
                                    scale_channels=int(scale),inherited_blend=(old.m_blend_total,old.m_blend_remaining))
                                remaining=state['carry']
                            else:raise ValueError('reference chain limit')
                        observed=actual.step(delta)
                        if observed['segment']!=index or observed['finished']!=finished or observed['evaluations']!=trace:
                            raise ValueError('action evaluation-order mismatch '+repr((flags,mask,scale,speed,delta,observed['evaluations'],trace)))
                        for path in pose:
                            if list(map(bits,observed['pose']['bone'][path]))!=list(map(bits,pose[path])):
                                raise ValueError('action constant-pose mismatch '+repr((flags,mask,scale,speed,delta,path)))
                        steps+=1
    ordering=[(0x1B89A8,0x0C06BE70),(0x1B89B0,0x12C0000C),(0x1B89D8,0x0040F809)]
    for address,word in ordering:
        if struct.unpack('<I',reader.read(address,4))[0]!=word:raise ValueError('unexpected completion-tail instruction')
    return dict(format='ARIKA_ACTION_POSE_VALIDATION',elf_sha256=REFERENCE_SHA256,constant_chain_runs=runs,
        input_steps_checked=steps,pose_evaluations_checked=evaluations,
        scope='Composed original scalar timing, pose-dispatch, startup-argument, and constant-bone helper instruction oracles with host float32/trig. Checks synthetic chain ordering/poses under the documented controller, plus tail call sites showing pose return precedes terminal callback. Not a full-program R5900 execution or hardware comparison. Animated track sampling, HandAni, root transforms and gameplay callbacks are outside this oracle.')


def check_trace(path,clock_path=None):
    document=json.loads(Path(path).read_text());samples=document['samples'];previous=-1.;evaluations=0;dispatch={}
    if document['format']!='ARIKA_COMMON_ACTION_POSES' or not samples:raise ValueError('expected nonempty action pose trace')
    for sample in samples:
        time=sample['time']
        if not math.isfinite(time) or time<=previous:raise ValueError('non-increasing pose trace times')
        previous=time
        for pose in sample['pose'].values():
            for component,width in (('translation',3),('rotation',4),('scale',3)):
                if len(pose[component])!=width or not all(math.isfinite(v) for v in pose[component]):raise ValueError('invalid trace pose')
        if len(sample['hands'])!=2 or not all(type(v) is int and 0<=v<=9 for v in sample['hands']):raise ValueError('invalid trace hands')
        evaluations+=len(sample['evaluations'])
        for evaluation in sample['evaluations']:
            key=evaluation['pose_dispatch'];dispatch[key]=dispatch.get(key,0)+1
    if samples[-1]['evaluation_count']!=evaluations:raise ValueError('trace evaluation count mismatch')
    matched=False
    if clock_path:
        clock=json.loads(Path(clock_path).read_text())
        if len(clock['samples'])!=len(samples) or clock['events']!=document['events']:raise ValueError('scalar/pose trace event mismatch')
        for actual,expected in zip(samples,clock['samples']):
            if any(actual[key]!=value for key,value in expected.items()):raise ValueError('scalar/pose clock trace mismatch')
        matched=True
    return dict(file=Path(path).name,samples_checked=len(samples),startup_events=len(document['events']),
        pose_evaluations=evaluations,dispatch_counts=dispatch,scalar_trace_matched=matched)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf');p.add_argument('output');p.add_argument('--gltf',action='append',default=[])
    p.add_argument('--pose-trace');p.add_argument('--clock-trace');args=p.parse_args()
    if args.clock_trace and not args.pose_trace:p.error('--clock-trace requires --pose-trace')
    result=audit(Path(args.elf).read_bytes());result['gltf_exports']=[check_gltf(path) for path in args.gltf]
    result['pose_trace']=check_trace(args.pose_trace,args.clock_trace) if args.pose_trace else None
    write_output(args.output,json.dumps(result,indent=2).encode(),[args.elf]+args.gltf+([args.pose_trace] if args.pose_trace else [])+([args.clock_trace] if args.clock_trace else []))
    print('Action chain steps:',result['input_steps_checked'],'pose evaluations:',result['pose_evaluations_checked'])


if __name__=='__main__':main()
