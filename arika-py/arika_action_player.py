#!/usr/bin/env python3
"""Bake the supported automatic common-action clock chain into local poses."""
import argparse
import copy
import json
import math
from pathlib import Path
import struct
import sys
from arika_action_clock import c_action_clock,load_action
from arika_actions import sample_hands
from arika_face_player import f32,sample_program
from arika_models import parse_model,require
from arika_pose import c_native_pose,synthetic_motion
from arika_import import write_output


class c_action_player:
    def __init__(self,model,segments,initial_blend=0):
        require(0 in segments,'action requires initial segment zero')
        self.m_segments=segments;self.m_hands=(0,0);self.m_evaluations=[];self.m_evaluation_count=0
        rest={n['name']:{p:list(map(f32,n[p])) for p in ('translation','rotation','scale')} for n in model['nodes']}
        flags={b['name']:b['flags'] for b in segments[0]['package']['bones']}
        masks={n:v&7 for n,v in flags.items() if v&7}
        for segment in segments.values():
            other={b['name']:b['flags']&7 for b in segment['package']['bones'] if b['flags']&7}
            require(other==masks,'action packages require identical named component masks')
        self.m_pose=c_native_pose(rest,flags)
        self.m_action=c_action_clock(segments,initial_blend,on_evaluate=self.evaluate)

    def evaluate(self,index,state):
        motion=self.m_segments[index]['motion']
        # Common startup clears the previous-motion pointer: no entry bridge.
        if state['pose_dispatch']=='animated_channels':self.m_pose.apply_animated(motion,state['sample_time'])
        else:self.m_pose.apply(motion,state['sample_time'],state['blend_weight'],state['blend_remaining']>0)
        hand=sample_hands(motion,[state['sample_time']],initial=self.m_hands)[0]
        self.m_hands=(hand['left'],hand['right'])
        self.m_evaluation_count+=1
        self.m_evaluations.append(dict(segment=index,motion_time=state['sample_time'],blend_weight=state['blend_weight'],
            blend_active=state['blend_remaining']>0,terminal=not state['active'],pose_dispatch=state['pose_dispatch']))

    def step(self,delta):
        self.m_evaluations=[];self.m_action.step(delta)
        return self.snapshot()

    def snapshot(self):
        return dict(self.m_action.snapshot(),pose=copy.deepcopy(self.m_pose.m_pose),hands=list(self.m_hands),
            evaluations=copy.deepcopy(self.m_evaluations),evaluation_count=self.m_evaluation_count)


def sample_action_poses(model,segments,duration,rate,initial_blend=0):
    require(math.isfinite(duration) and 0<duration<=60,'action pose duration must be in (0,60]')
    require(rate in (25,30,50,60,100,120),'unsupported action pose rate')
    player=c_action_player(model,segments,initial_blend);samples=[dict(time=0,**player.snapshot())]
    for tick in range(1,math.ceil(duration*rate)+1):samples.append(dict(time=tick/rate,**player.step(1/rate)))
    return samples,player.m_action.m_events


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('sample','animate'):
        p=sub.add_parser(command);p.add_argument('elf');p.add_argument('cht');p.add_argument('output')
        p.add_argument('--model',required=True);p.add_argument('--slot',type=int,required=True);p.add_argument('--bank',action='append',required=True)
        p.add_argument('--duration',type=float,required=True);p.add_argument('--rate',type=int,default=60)
        p.add_argument('--initial-blend',type=float,default=0)
        if command=='animate':p.add_argument('--textures')
    args=parser.parse_args()
    try:
        plan,segments,inputs=load_action(args.elf,args.cht,args.bank,args.slot)
        model=parse_model(Path(args.model).read_bytes());inputs.append(args.model)
        samples,events=sample_action_poses(model,segments,args.duration,args.rate,args.initial_blend)
        plan=dict(plan,format='ARIKA_COMMON_ACTION_POSES',events=events,sample_rate=args.rate,initial_blend=args.initial_blend,
            model_sha256=model['source_sha256'],
            scope='Automatic common-action subset: scalar clock/carry, supported record startup, named local-pose helpers, and discrete HandAni preview. Initial blend is caller supplied. Root reset/accumulation, IK, gameplay callbacks, contextual binding and character table overrides are not simulated.')
        if args.command=='sample':write_output(args.output,json.dumps(dict(plan,samples=samples),indent=2).encode(),inputs)
        else:
            from arika_face_bake import bake_gltf
            if args.textures:inputs.append(args.textures)
            require(all(Path(args.output).resolve()!=Path(p).resolve() for p in inputs),'output must differ from inputs')
            texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
            playback=sample_program([],samples[-1]['time'],args.rate,blink=False)
            playback['native_pose']=plan;playback['action_sequence']=plan
            print(json.dumps(bake_gltf(model,playback,args.output,texture,synthetic_motion(samples,args.rate),
                name='native_common_action_%d'%args.slot,auto_hands=True)))
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
