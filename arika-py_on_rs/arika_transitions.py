#!/usr/bin/env python3
"""Explicit motion-switch previews using recovered native clock/blend kernels."""
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
from arika_pose import c_native_pose,synthetic_motion
from arika_face_player import f32,sample_program
from arika_actions import sample_hands
from arika_cht import parse_cht,load_banks,lookup,resolve
from arika_import import write_output


def normalize_schedule(document):
    require(isinstance(document,dict) and set(document)=={'segments'},'schedule must contain only segments')
    rows=document['segments'];require(isinstance(rows,list) and 0<len(rows)<=1000,'expected 1..1000 segments')
    allowed={'at','motion_id','variant','blend','speed','start_frame','end_frame','reverse','loop'}
    result=[];previous=-1
    for row in rows:
        require(isinstance(row,dict) and not set(row)-allowed,'unknown segment field')
        require('at' in row and 'motion_id' in row,'segment requires at and motion_id')
        defaults=dict(variant=0,blend=.17,speed=1.,start_frame=0.,end_frame=-1.,reverse=False,loop=False)
        defaults.update(row);row=defaults
        for key in ('at','blend','speed','start_frame','end_frame'):
            require(type(row[key]) in (int,float) and math.isfinite(row[key]),'invalid segment '+key)
        require(row['at']>=0 and row['at']>previous,'segment times must strictly increase')
        require(type(row['motion_id']) is int and 0<=row['motion_id']<1000,'invalid motion_id')
        require(type(row['variant']) is int and row['variant']>=0,'invalid variant')
        require(row['blend']>=0,'negative blend duration')
        require(type(row['reverse']) is bool and type(row['loop']) is bool,'reverse/loop must be booleans')
        previous=row['at'];result.append(row)
    require(result[0]['at']==0,'first segment must start at zero')
    return result


class c_transition_player:
    def __init__(self,model,segments):
        require(bool(segments),'empty transition list')
        self.m_segments=segments;self.m_index=-1;self.m_clock=None;self.m_previous=None
        self.m_hands=(0,0);self.m_bridge=None;self.m_events=[]
        rest={n['name']:{p:list(map(f32,n[p])) for p in ('translation','rotation','scale')} for n in model['nodes']}
        flags={b['name']:b['flags'] for b in segments[0]['package']['bones']}
        self.m_player=c_native_pose(rest,flags)
        # Contextual skeleton rebinding is outside this standalone player.
        masks={n:v&7 for n,v in flags.items() if v&7}
        for segment in segments:
            other={b['name']:b['flags']&7 for b in segment['package']['bones'] if b['flags']&7}
            require(other==masks,'transition packages require identical named component masks')

    def switch(self,index):
        old=self.m_segments[self.m_index] if self.m_index>=0 else None
        if old is not None:
            self.m_previous=(old['motion'],self.m_clock.snapshot()['sample_time'],self.m_index)
        self.m_index=index;segment=self.m_segments[index];motion=segment['motion'];row=segment['setup']
        self.m_clock=c_native_clock(motion['fps'],motion['frame_count'],start=row['start_frame'],end=row['end_frame'],
            speed=row['speed'],blend=row['blend'],reverse=row['reverse'],loop=row['loop'],scale_channels=motion['channel_counts'][2])
        self.m_state=self.m_clock.snapshot()
        self.m_bridge=None
        self.m_events.append(dict(at=row['at'],segment=index,outgoing_segment=None if old is None else index-1,
            outgoing_time=None if self.m_previous is None else self.m_previous[1],binding=segment.get('binding')))
        if self.m_clock.m_initialization_tick:
            self.apply(self.m_clock.m_initialization_tick)

    def apply(self,state):
        self.m_state=state
        if not state['advanced']:return
        segment=self.m_segments[self.m_index];motion=segment['motion'];row=segment['setup']
        self.m_bridge=None
        if state['wrap_fraction'] is not None:
            self.m_player.apply(motion,state['end_time'],state['blend_weight'],state['blend_remaining']>0,
                second_time=state['start_time'],fraction=state['wrap_fraction'])
        else:
            position=state['position'];fraction=None
            if self.m_previous is not None:
                if row['reverse'] and position>state['end_time']:
                    fraction=f32(1-f32(f32(position-state['end_time'])/self.m_clock.m_frame_period))
                elif not row['reverse'] and position<state['start_time']:
                    fraction=f32(1-f32(f32(state['start_time']-position)/self.m_clock.m_frame_period))
            if fraction is None:
                self.m_player.apply(motion,state['sample_time'],state['blend_weight'],state['blend_remaining']>0)
            else:
                outgoing,time,index=self.m_previous
                self.m_player.apply_sources(outgoing,time,motion,state['sample_time'],fraction,
                    state['blend_weight'],state['blend_remaining']>0)
                self.m_bridge=dict(outgoing_segment=index,outgoing_time=time,incoming_time=state['sample_time'],fraction=fraction)
        hands=sample_hands(motion,[state['sample_time']],initial=self.m_hands)[0]
        self.m_hands=(hands['left'],hands['right'])

    def step(self,delta):
        state=self.m_clock.step(delta);self.apply(state)

    def snapshot(self,time):
        return dict(time=time,segment=self.m_index,clock=copy.deepcopy(self.m_state),bridge=copy.deepcopy(self.m_bridge),
            pose=copy.deepcopy(self.m_player.m_pose),hands=list(self.m_hands))


def sample_transitions(model,segments,duration,rate):
    require(math.isfinite(duration) and 0<duration<=60,'transition duration must be in (0,60]')
    require(rate in (25,30,50,60,100,120),'unsupported transition rate')
    require(segments[-1]['setup']['at']<=duration,'segment begins after requested duration')
    player=c_transition_player(model,segments);player.switch(0);time=0.;next_index=1
    samples=[player.snapshot(0)]
    for tick in range(1,math.ceil(duration*rate)+1):
        end=tick/rate
        while next_index<len(segments) and segments[next_index]['setup']['at']<=end:
            at=segments[next_index]['setup']['at']
            if at>time:player.step(at-time)
            player.switch(next_index);next_index+=1;time=at
        if end>time:player.step(end-time)
        time=end;samples.append(player.snapshot(time))
    return samples,player.m_events


def load_segments(rows,cht,banks):
    cache={};segments=[]
    for row in rows:
        binding=resolve(lookup(cht,row['motion_id'],row['variant']),banks)
        require(binding['status']=='resolved','unresolved transition motion: '+binding['status'])
        path=binding['package']
        if path not in cache:cache[path]=models.parse_motions(Path(path).read_bytes())
        package=cache[path]
        segments.append(dict(setup=row,package=package,motion=package['motions'][binding['package_index']],binding=binding))
    return segments


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('sample','animate'):
        p=sub.add_parser(command);p.add_argument('cht');p.add_argument('schedule');p.add_argument('output')
        p.add_argument('--model',required=True);p.add_argument('--bank',action='append',required=True)
        p.add_argument('--duration',type=float,required=True);p.add_argument('--rate',type=int,default=60)
        if command=='animate':p.add_argument('--textures')
    args=parser.parse_args()
    try:
        rows=normalize_schedule(json.loads(Path(args.schedule).read_text(encoding='utf-8')))
        cht=parse_cht(Path(args.cht).read_bytes());banks=load_banks(args.bank)
        segments=load_segments(rows,cht,banks);model=models.parse_model(Path(args.model).read_bytes())
        samples,events=sample_transitions(model,segments,args.duration,args.rate)
        metadata=dict(format='ARIKA_EXPLICIT_TRANSITIONS',schedule=rows,events=events,sample_rate=args.rate,
            model_sha256=model['source_sha256'],cht_sha256=cht['source_sha256'],
            scope='User-authored switch times with native clock/blend kernels. Outgoing clamped motion time is frozen; live pose is retained. This is not recovered automatic action startup/callback timing, contextual binding, root motion or IK. HandAni uses incoming discrete samples.')
        inputs=[args.cht,args.schedule,args.model]+[b['path'] for b in banks.values()]
        if args.command=='sample':write_output(args.output,json.dumps(dict(metadata,samples=samples),indent=2).encode(),inputs)
        else:
            from arika_face_bake import bake_gltf
            require(all(Path(args.output).resolve()!=Path(p).resolve() for p in inputs),'output must differ from inputs')
            texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
            playback=sample_program([],samples[-1]['time'],args.rate,blink=False);playback['native_pose']=metadata
            print(json.dumps(bake_gltf(model,playback,args.output,texture,synthetic_motion(samples,args.rate),name='explicit_transitions',auto_hands=True)))
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
