#!/usr/bin/env python3
"""Sample the native per-bone blend structure with an isolated segment clock."""
import argparse
import copy
import json
import math
from pathlib import Path
import struct
import sys
import arika_models as models
from arika_models import require
from arika_clock import c_native_clock
from arika_cht import parse_cht,load_banks,lookup,resolve
from arika_face_player import f32,sample_program
from arika_actions import sample_hands
from arika_import import write_output


def lerp_vector(current,target,weight):
    weight=f32(weight)
    return [f32(f32(a)+f32(f32(f32(b)-f32(a))*weight)) for a,b in zip(current,target)]


def blend_quaternion(current,target,weight):
    a=list(map(f32,current));b=list(map(f32,target));weight=f32(weight)
    dot=f32(a[1]*b[1])
    for i in (0,2,3):dot=f32(dot+f32(a[i]*b[i]))
    if dot<0:
        dot=f32(-dot);b=[f32(-v) for v in b]
    old_weight=f32(1-weight);new_weight=weight
    if f32(1-dot)>f32(.001):
        angle=f32(math.acos(max(-1,min(1,dot))))
        denominator=f32(math.sin(angle))
        old_weight=f32(f32(math.sin(f32(angle*old_weight)))/denominator)
        new_weight=f32(f32(math.sin(f32(angle*weight)))/denominator)
    # The native near-parallel path does not normalize its linear result.
    return [f32(f32(new_weight*y)+f32(old_weight*x)) for x,y in zip(a,b)]


def sample_native_track(track,time,path):
    keys=track['times'];values=track['values'];time=f32(time)
    require(keys and len(keys)==len(values),'invalid pose track')
    index=0;factor=0.0
    if time>0:
        for j,key in enumerate(keys):
            if abs(f32(f32(key)-time))<f32(1e-5):index=j;break
            if key>time:
                require(j>0,'track begins after requested positive time')
                index=j-1;factor=f32(f32(time-f32(keys[index]))/f32(f32(key)-f32(keys[index])));break
            index=j
    if factor==0 or index==len(values)-1:return list(map(f32,values[index]))
    return blend_quaternion(values[index],values[index+1],factor) if path=='rotation' else lerp_vector(values[index],values[index+1],factor)


def apply_bone(current,target,rest,mask,weight,blend_active=True,scale_enabled=True):
    require(type(mask) is int and 0<=mask<=255,'invalid bone component flags')
    require(math.isfinite(weight) and 0<=weight<=1,'invalid pose blend coefficient')
    output=copy.deepcopy(current);weight=f32(weight)
    for bit,path in ((1,'translation'),(2,'rotation'),(4,'scale')):
        if not mask&bit or path=='scale' and not scale_enabled:continue
        fallback=[1,1,1] if path=='scale' else rest[path]
        value=target[path] if target is not None and path in target else fallback
        require(len(value)==(4 if path=='rotation' else 3) and all(math.isfinite(v) for v in value),'invalid pose component')
        if blend_active:
            output[path]=blend_quaternion(current[path],value,weight) if path=='rotation' else lerp_vector(current[path],value,weight)
        else:output[path]=list(map(f32,value))
    return output


def apply_bone_pair(current,first,second,rest,mask,fraction,weight,blend_active=True,scale_enabled=True):
    require(math.isfinite(fraction) and 0<=fraction<=1,'invalid source blend fraction')
    if first is None and second is None:
        return apply_bone(current,None,rest,mask,weight,blend_active,scale_enabled)
    # Missing first source reverses the native interpolation operands.
    base=second if first is None else first
    other=second if first is not None and second is not None else None
    mix=f32(1-f32(fraction)) if first is None else f32(fraction)
    mixed={}
    for bit,path in ((1,'translation'),(2,'rotation'),(4,'scale')):
        if not mask&bit or path=='scale' and not scale_enabled:continue
        fallback=[1.,1.,1.] if path=='scale' else rest[path]
        a=base.get(path,fallback);b=other.get(path,fallback) if other is not None else fallback
        mixed[path]=blend_quaternion(a,b,mix) if path=='rotation' else lerp_vector(a,b,mix)
    return apply_bone(current,mixed,rest,mask,weight,blend_active,scale_enabled)


class c_native_pose:
    def __init__(self,rest_pose,bone_flags):
        self.m_rest=copy.deepcopy(rest_pose)
        self.m_pose=copy.deepcopy(rest_pose)
        self.m_flags=dict(bone_flags)

    def apply(self,motion,time,weight,blend_active=True,second_time=None,fraction=None):
        nodes={n['name']:n for n in motion['nodes'] if 'name' in n}
        for name,current in self.m_pose.items():
            mask=self.m_flags.get(name,0)
            if not mask&7:continue
            source=nodes.get(name)
            target={p:sample_native_track(source['tracks'][p],time,p) for bit,p in ((1,'translation'),(2,'rotation'),(4,'scale'))
                if mask&bit and (p!='scale' or motion['channel_counts'][2]>0)} if source else None
            if second_time is None:
                self.m_pose[name]=apply_bone(current,target,self.m_rest[name],mask,weight,blend_active,
                    motion['channel_counts'][2]>0)
            else:
                second={p:sample_native_track(source['tracks'][p],second_time,p) for p in target} if source else None
                self.m_pose[name]=apply_bone_pair(current,target,second,self.m_rest[name],mask,fraction,weight,
                    blend_active,motion['channel_counts'][2]>0)
        return copy.deepcopy(self.m_pose)

    def apply_sources(self,first_motion,first_time,second_motion,second_time,fraction,weight,blend_active=True):
        first_nodes={n['name']:n for n in first_motion['nodes'] if 'name' in n}
        second_nodes={n['name']:n for n in second_motion['nodes'] if 'name' in n}
        scale=second_motion['channel_counts'][2]>0
        require(not scale or first_motion['channel_counts'][2]>0,'mixed scale-channel transition is unsupported')
        for name,current in self.m_pose.items():
            mask=self.m_flags.get(name,0)
            if not mask&7:continue
            def target(nodes,time):
                source=nodes.get(name)
                return {p:sample_native_track(source['tracks'][p],time,p) for bit,p in ((1,'translation'),(2,'rotation'),(4,'scale'))
                    if mask&bit and (p!='scale' or scale)} if source else None
            self.m_pose[name]=apply_bone_pair(current,target(first_nodes,first_time),target(second_nodes,second_time),
                self.m_rest[name],mask,fraction,weight,blend_active,scale)
        return copy.deepcopy(self.m_pose)

    def apply_animated(self,motion,time):
        # 0x1B0C30 walks the animated channel forward map; constants are untouched.
        for node in motion['nodes']:
            name=node.get('name')
            if name not in self.m_pose:continue
            for path,track in node['tracks'].items():
                if path in ('translation','rotation','scale') and track['animated']:
                    self.m_pose[name][path]=sample_native_track(track,time,path)
        return copy.deepcopy(self.m_pose)


def sample_pose(model,package,motion,duration,rate,blend=.17,speed=1,reverse=False,loop=False):
    require(math.isfinite(duration) and 0<duration<=60,'pose duration must be in (0,60] seconds')
    require(rate in (25,30,50,60,100,120),'unsupported pose rate')
    rest={n['name']:{p:list(map(f32,n[p])) for p in ('translation','rotation','scale')} for n in model['nodes']}
    player=c_native_pose(rest,{b['name']:b['flags'] for b in package['bones']})
    clock=c_native_clock(motion['fps'],motion['frame_count'],speed=speed,blend=blend,reverse=reverse,loop=loop,
        scale_channels=motion['channel_counts'][2])
    state=clock.snapshot();left=right=0
    if clock.m_initialization_tick:
        state=clock.m_initialization_tick
        if state['advanced']:
            player.apply(motion,state['sample_time'],state['blend_weight'],state['blend_remaining']>0)
            hand=sample_hands(motion,[state['sample_time']],initial=(left,right))[0]
            left,right=hand['left'],hand['right']
    samples=[dict(time=0,clock=state,pose=copy.deepcopy(player.m_pose),hands=[left,right])]
    for tick in range(1,math.ceil(duration*rate)+1):
        state=clock.step(1/rate)
        if state['advanced']:
            if state['wrap_fraction'] is not None:
                player.apply(motion,state['end_time'],state['blend_weight'],state['blend_remaining']>0,
                    second_time=state['start_time'],fraction=state['wrap_fraction'])
            else:player.apply(motion,state['sample_time'],state['blend_weight'],state['blend_remaining']>0)
            hand=sample_hands(motion,[state['sample_time']],initial=(left,right))[0]
            left,right=hand['left'],hand['right']
        samples.append(dict(time=tick/rate,clock=state,pose=copy.deepcopy(player.m_pose),hands=[left,right]))
    return samples


def synthetic_motion(samples,rate):
    times=[s['time'] for s in samples];nodes=[]
    for name in samples[0]['pose']:
        if name=='HandAni':continue
        nodes.append(dict(name=name,tracks={p:dict(times=times,values=[s['pose'][name][p] for s in samples]) for p in ('translation','rotation','scale')}))
    nodes.append(dict(name='HandAni',tracks=dict(translation=dict(times=times,values=[[s['hands'][0],0,s['hands'][1]] for s in samples]))))
    return dict(name='native_pose_blend',fps=rate,frame_count=len(samples),duration=times[-1]+1/rate,last_frame_time=times[-1],nodes=nodes)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ('sample','animate'):
        q=sub.add_parser(command);q.add_argument('cht');q.add_argument('output');q.add_argument('--model',required=True)
        q.add_argument('--id',type=int,required=True);q.add_argument('--variant',type=int,default=0);q.add_argument('--bank',action='append',required=True)
        q.add_argument('--duration',type=float,required=True);q.add_argument('--rate',type=int,default=60)
        q.add_argument('--blend',type=float,default=.17);q.add_argument('--speed',type=float,default=1);q.add_argument('--reverse',action='store_true')
        q.add_argument('--loop',action='store_true')
        if command=='animate':q.add_argument('--textures')
    args=p.parse_args()
    try:
        banks=load_banks(args.bank);cht=parse_cht(Path(args.cht).read_bytes());binding=resolve(lookup(cht,args.id,args.variant),banks)
        require(binding['status']=='resolved','unresolved pose motion: '+binding['status'])
        package=models.parse_motions(Path(binding['package']).read_bytes());motion=package['motions'][binding['package_index']]
        model=models.parse_model(Path(args.model).read_bytes())
        samples=sample_pose(model,package,motion,args.duration,args.rate,args.blend,args.speed,args.reverse,args.loop)
        metadata=dict(format='ARIKA_NATIVE_POSE',motion_binding=binding,model_sha256=model['source_sha256'],
            cht_sha256=cht['source_sha256'],motion_id=args.id,sample_rate=args.rate,blend=args.blend,speed=args.speed,reverse=args.reverse,loop=args.loop,
            scope='Isolated segment from model rest pose, including two-source loop-gap blending. Host trig/IEEE float32 approximate EE math; full action startup, root motion and contextual binding are not simulated. HandAni retains discrete clamped-time preview sampling.')
        inputs=[args.cht,args.model]+[b['path'] for b in banks.values()]
        if args.command=='sample':write_output(args.output,json.dumps(dict(metadata,samples=samples),indent=2).encode(),inputs)
        else:
            from arika_face_bake import bake_gltf
            texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
            require(all(Path(args.output).resolve()!=Path(path).resolve() for path in inputs),'output must differ from inputs')
            playback=sample_program([],samples[-1]['time'],args.rate,blink=False)
            playback['native_pose']=metadata;playback['motion_binding']=binding
            print(json.dumps(bake_gltf(model,playback,args.output,texture,synthetic_motion(samples,args.rate),name='native_pose_%d_%d'%(args.id,args.variant),auto_hands=True)))
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
