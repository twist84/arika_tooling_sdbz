#!/usr/bin/env python3
"""Trace the scalar native MOT2 clock, without the pose/callback backend."""
import argparse
import json
import math
from pathlib import Path
import struct
import sys
from arika_models import require, parse_motions
from arika_cht import parse_cht,load_banks,lookup,resolve
from arika_face_player import f32
from arika_import import write_output


ACTIVE=0x01000000
PAUSED=0x04000000
DIRTY=0x02000000
WRAPPED=0x08000000
REVERSE=0x00020000
LOOP=0x00010000


class c_native_clock:
    def __init__(self,fps,frame_count,start=0,end=-1,speed=1,blend=0,
                 reverse=False,loop=False,stop_after=-1,scale_channels=0,inherited_blend=None):
        require(all(math.isfinite(x) for x in (fps,start,end,speed,blend,stop_after)), 'nonfinite clock setup')
        require(fps>0 and type(frame_count) is int and 0<frame_count<=65535,'invalid clock motion timing')
        native_fps=f32(fps)
        require(native_fps>0 and math.isfinite(native_fps),'invalid float32 fps')
        self.m_frame_period=f32(1/native_fps)
        require(self.m_frame_period>0 and math.isfinite(self.m_frame_period),'invalid float32 frame period')
        last=f32(frame_count-1)
        start=min(last,max(0,f32(start)))
        end=last if end<0 else min(last,f32(end))
        require(end>=start,'reversed frame range is unsupported')
        self.m_start=f32(start*self.m_frame_period)
        self.m_end=f32(end*self.m_frame_period)
        self.m_speed=max(f32(.01),f32(speed))
        self.m_baseline=f32(self.m_end+self.m_frame_period) if reverse else f32(self.m_start-self.m_frame_period)
        self.m_position=self.m_baseline
        self.m_blend_total=self.m_blend_remaining=max(0,f32(blend))
        if blend<0 and inherited_blend is not None:
            total,remaining=inherited_blend
            require(all(math.isfinite(v) for v in (total,remaining)) and total>=0 and remaining<=total,'invalid inherited blend')
            self.m_blend_total=f32(total);self.m_blend_remaining=f32(remaining)
        self.m_stop_timer=f32(stop_after)
        self.m_scale_channels=scale_channels
        self.m_flags=ACTIVE|DIRTY|(REVERSE if reverse else 0)|(LOOP if loop else 0)|(0x100 if scale_channels else 0)
        require(self.m_start!=self.m_baseline if not reverse else self.m_end!=self.m_baseline,'unrepresentable clock baseline')
        self.m_initialization_tick=None
        if self.m_stop_timer==0 or self.m_end<=self.m_start:
            self.m_initialization_tick=self.step(self.m_frame_period)

    def snapshot(self,carry=0,wrap_fraction=None,advanced=False):
        weight=f32(1-f32(self.m_blend_remaining/self.m_blend_total)) if self.m_blend_remaining>0 else 1.0
        return dict(position=self.m_position,sample_time=min(self.m_end,max(self.m_start,self.m_position)),
            start_time=self.m_start,end_time=self.m_end,baseline=self.m_baseline,speed=self.m_speed,
            stop_timer=self.m_stop_timer,blend_total=self.m_blend_total,blend_remaining=self.m_blend_remaining,
            blend_weight=weight,carry=carry,wrap_fraction=wrap_fraction,active=bool(self.m_flags&ACTIVE),
            flags=self.m_flags,advanced=advanced)

    def step(self,delta):
        require(math.isfinite(delta),'nonfinite clock delta')
        delta=f32(delta)
        if not self.m_flags&ACTIVE:
            return self.snapshot(carry=delta)
        if self.m_flags&PAUSED or delta<=0:
            return self.snapshot()
        scaled=f32(delta*self.m_speed)
        require(math.isfinite(scaled),'clock delta overflow')
        carry=0.0;overshoot=0.0;finished=False;fraction=None
        if self.m_stop_timer>0:
            self.m_stop_timer=f32(self.m_stop_timer-scaled)
            if self.m_stop_timer<=0:
                overshoot=f32(-self.m_stop_timer)
                carry=f32(overshoot/self.m_speed)
                scaled=f32(scaled+self.m_stop_timer)
                finished=True
        if self.m_blend_remaining>0:
            self.m_blend_remaining=f32(self.m_blend_remaining-scaled)
            if self.m_blend_remaining<=0:
                if self.m_scale_channels==0:self.m_flags&=~0x100
                self.m_flags|=DIRTY
        reverse=bool(self.m_flags&REVERSE)
        self.m_position=f32(self.m_position-scaled) if reverse else f32(self.m_position+scaled)
        if self.m_flags&LOOP:
            period=f32(self.m_baseline-self.m_start) if reverse else f32(self.m_end-self.m_baseline)
            require(period>0,'invalid native loop period')
            for _ in range(100000):
                outside=self.m_position<self.m_start if reverse else self.m_position>self.m_end
                if not outside:break
                self.m_flags|=WRAPPED
                updated=f32(self.m_position+period) if reverse else f32(self.m_position-period)
                require(updated!=self.m_position,'native loop subtraction cannot progress')
                self.m_position=updated
            else:raise ValueError('native loop iteration limit')
        else:
            at_end=self.m_position<=self.m_start if reverse else self.m_position>=self.m_end
            if at_end:
                extra=f32(self.m_start-self.m_position) if reverse else f32(self.m_position-self.m_end)
                carry=f32(f32(overshoot+extra)/self.m_speed)
                self.m_position=self.m_start if reverse else self.m_end
                finished=True
        if self.m_flags&WRAPPED:
            if reverse and self.m_position>self.m_end:
                fraction=f32(f32(self.m_position-self.m_end)/self.m_frame_period)
            elif not reverse and self.m_position<self.m_start:
                fraction=f32(1-f32(f32(self.m_start-self.m_position)/self.m_frame_period))
        if finished:self.m_flags&=0xF
        # Pose evaluation clears the one-shot dirty flag before terminal cleanup.
        self.m_flags&=~DIRTY
        return self.snapshot(carry,fraction,True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cht');p.add_argument('output')
    p.add_argument('--id',type=int,required=True);p.add_argument('--variant',type=int,default=0)
    p.add_argument('--bank',action='append',required=True);p.add_argument('--duration',type=float,required=True)
    p.add_argument('--rate',type=int,default=60);p.add_argument('--speed',type=float,default=1)
    p.add_argument('--start-frame',type=float,default=0);p.add_argument('--end-frame',type=float,default=-1)
    p.add_argument('--blend',type=float,default=0);p.add_argument('--stop-after',type=float,default=-1)
    p.add_argument('--reverse',action='store_true');p.add_argument('--loop',action='store_true')
    args=p.parse_args()
    try:
        require(math.isfinite(args.duration) and 0<args.duration<=600,'duration must be in (0,600]')
        require(args.rate in (25,30,50,60,100,120),'unsupported clock rate')
        banks=load_banks(args.bank);cht=parse_cht(Path(args.cht).read_bytes())
        binding=resolve(lookup(cht,args.id,args.variant),banks)
        require(binding['status']=='resolved','unresolved clock motion: '+binding['status'])
        binding.update(motion_id=args.id,cht_sha256=cht['source_sha256'])
        motion=parse_motions(Path(binding['package']).read_bytes())['motions'][binding['package_index']]
        clock=c_native_clock(motion['fps'],motion['frame_count'],args.start_frame,args.end_frame,args.speed,
            args.blend,args.reverse,args.loop,args.stop_after,motion['channel_counts'][2])
        samples=[dict(tick=0,wall_time=0,**clock.snapshot())]
        for tick in range(1,math.ceil(args.duration*args.rate)+1):
            samples.append(dict(tick=tick,wall_time=tick/args.rate,**clock.step(1/args.rate)))
        result=dict(format='ARIKA_NATIVE_SEGMENT_CLOCK',motion_binding=binding,sample_rate=args.rate,
            motion_timing=dict(fps=motion['fps'],frame_count=motion['frame_count'],frame_period=clock.m_frame_period,
                scale_channels=motion['channel_counts'][2]),
            setup=dict(start_frame=args.start_frame,end_frame=args.end_frame,speed=args.speed,blend=args.blend,
                stop_after=args.stop_after,reverse=args.reverse,loop=args.loop),
            samples=samples,initialization_tick=clock.m_initialization_tick,
            scope='Scalar clock only: fresh segment setup before tick 1, including the zero-timer/zero-range setup update. Native pose blending, callbacks, motion lists and action-startup orchestration are not simulated. Blend weight is the scalar countdown coefficient.')
        write_output(args.output,json.dumps(result,indent=2).encode(),[args.cht]+[b['path'] for b in banks.values()])
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
