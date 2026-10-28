#!/usr/bin/env python3
"""Trace automatic common-action startup and scalar clock carry."""
import argparse
import copy
import json
import math
from pathlib import Path
import struct
import sys
from arika_actions import common_tables
from arika_clock import c_native_clock,DIRTY
from arika_cht import parse_cht,load_banks,lookup,resolve
from arika_face_player import f32
from arika_models import parse_motions,require
from arika_import import write_output


def startup_control(records,index):
    require(type(index) is int and 0<=index<len(records),'segment index out of range')
    flags=records[index]['flags'];allowed=0x270000|(0xFF if flags&0x40000 else 0)
    require(flags&~allowed==0,'unsupported action flags 0x%08X'%flags)
    if flags&0x20000:return dict(segment=index,transition='replay',blend_request=-1.)
    if flags&0x10000:return dict(segment=None,transition='stop',blend_request=-1.)
    target=flags&0xFF if flags&0x40000 else index+1
    require(0<=target<len(records),'action leaves table')
    return dict(segment=target,transition='jump' if flags&0x40000 else 'advance',
        blend_request=f32(.17) if flags&0x200000 else -1.)


def startup_settings(record,blend_request):
    return dict(speed=f32(record['speed']),start_frame=f32(record['start_frame']),end_frame=f32(record['end_frame']),
        blend_request=f32(blend_request),stop_after=-1.,flags=0)


def load_action(elf,cht_path,bank_specs,slot):
    tables=common_tables(Path(elf).read_bytes())
    action=next((a for a in tables['actions'] if a['slot']==slot),None)
    require(action is not None,'common action slot is empty or out of range')
    cht=parse_cht(Path(cht_path).read_bytes());banks=load_banks(bank_specs);cache={};segments={};index=0
    while index not in segments:
        control=startup_control(action['records'],index);record=action['records'][index]
        binding=resolve(lookup(cht,record['motion_id'],record['variant']),banks)
        require(binding['status']=='resolved','unresolved action motion: '+binding['status'])
        path=binding['package']
        if path not in cache:cache[path]=parse_motions(Path(path).read_bytes())
        segments[index]=dict(record=record,package=cache[path],motion=cache[path]['motions'][binding['package_index']],binding=binding,control=control)
        if control['segment'] is None:break
        index=control['segment']
    plan=dict(format='ARIKA_COMMON_ACTION_STARTUP',action_slot=slot,elf_sha256=tables['elf_sha256'],
        cht_sha256=cht['source_sha256'],segments=[dict(segment=i,record=s['record'],binding=s['binding'],control=s['control']) for i,s in segments.items()],
        scope='Common defaults with resolved CHT names; supported automatic transition and scalar startup/carry only. Initial blend is caller input. No gameplay callbacks, overrides, root transforms, contextual binding, or pose evaluation.')
    return plan,segments,[elf,cht_path]+[b['path'] for b in banks.values()]


class c_action_clock:
    def __init__(self,segments,initial_blend=0,on_evaluate=None):
        require(math.isfinite(initial_blend) and initial_blend>=0,'invalid initial blend')
        self.m_segments=segments;self.m_index=0;self.m_clock=None;self.m_events=[];self.m_finished=False
        self.m_carry=0.;self.m_state=None
        self.m_on_evaluate=on_evaluate
        self.start(0,initial_blend,'initial',0.)

    def start(self,index,blend_request,reason,carry):
        old=self.m_clock;segment=self.m_segments[index];motion=segment['motion'];record=segment['record']
        self.m_index=index
        self.m_clock=c_native_clock(motion['fps'],motion['frame_count'],start=record['start_frame'],end=record['end_frame'],
            speed=record['speed'],blend=blend_request,scale_channels=motion['channel_counts'][2],
            inherited_blend=None if old is None else (old.m_blend_total,old.m_blend_remaining))
        require(self.m_clock.m_initialization_tick is None,'zero-range common-action setup is not yet supported')
        self.m_state=self.m_clock.snapshot()
        self.m_events.append(dict(segment=index,reason=reason,carry_in=carry,settings=startup_settings(record,blend_request),
            clock_setup=copy.deepcopy(self.m_state),clears_previous_bridge=True))

    def step(self,delta):
        require(math.isfinite(delta) and delta>=0,'invalid action delta')
        delta=f32(delta)
        if self.m_finished:self.m_carry=delta;return self.snapshot()
        for _ in range(4096):
            dirty=bool(self.m_clock.m_flags&DIRTY);old_blend=self.m_clock.m_blend_remaining
            self.m_state=self.m_clock.step(delta)
            # Native pose dispatch precedes terminal cleanup/completion callback.
            if self.m_state['advanced'] and self.m_on_evaluate is not None:
                helper=dirty or self.m_state['blend_remaining']>0 or (old_blend>0 and self.m_state['blend_remaining']<=0)
                self.m_on_evaluate(self.m_index,dict(self.m_state,pose_dispatch='helper' if helper else 'animated_channels'))
            if self.m_state['active']:
                self.m_carry=self.m_state['carry'];return self.snapshot()
            control=self.m_segments[self.m_index]['control'];carry=self.m_state['carry']
            if control['segment'] is None:
                self.m_finished=True;self.m_carry=carry;return self.snapshot()
            self.start(control['segment'],control['blend_request'],control['transition'],carry)
            # 0x1D73A8 passes the old clock's wall-time carry to the new clock.
            delta=carry
        raise ValueError('action startup iteration limit (zero-duration cycle or excessive transitions)')

    def snapshot(self):
        return dict(segment=self.m_index,finished=self.m_finished,carry=self.m_carry,clock=copy.deepcopy(self.m_state),
            event_count=len(self.m_events))


def sample_action(segments,duration,rate,initial_blend=0):
    require(math.isfinite(duration) and 0<duration<=60,'action duration must be in (0,60]')
    require(rate in (25,30,50,60,100,120),'unsupported action sample rate')
    player=c_action_clock(segments,initial_blend);samples=[dict(time=0,**player.snapshot())]
    for tick in range(1,math.ceil(duration*rate)+1):samples.append(dict(time=tick/rate,**player.step(1/rate)))
    return samples,player.m_events


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('plan','sample'):
        p=sub.add_parser(command);p.add_argument('elf');p.add_argument('cht');p.add_argument('output')
        p.add_argument('--slot',type=int,required=True);p.add_argument('--bank',action='append',required=True)
        if command=='sample':
            p.add_argument('--duration',type=float,required=True);p.add_argument('--rate',type=int,default=60)
            p.add_argument('--initial-blend',type=float,default=0)
    args=parser.parse_args()
    try:
        plan,segments,inputs=load_action(args.elf,args.cht,args.bank,args.slot)
        if args.command=='sample':
            samples,events=sample_action(segments,args.duration,args.rate,args.initial_blend)
            plan.update(samples=samples,events=events,sample_rate=args.rate,initial_blend=args.initial_blend)
        write_output(args.output,json.dumps(plan,indent=2).encode(),inputs);print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
