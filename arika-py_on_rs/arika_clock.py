#!/usr/bin/env python3
"""Trace the scalar native MOT2 clock, without the pose/callback backend."""
import argparse
import ctypes
import json
import math
from pathlib import Path
import struct
import sys
from arika_models import require, parse_motions
from arika_cht import parse_cht,load_banks,lookup,resolve
from arika_face_player import f32
from arika_import import write_output
import arika_backend as backend
from arika_backend import BackendError


ACTIVE=0x01000000
PAUSED=0x04000000
DIRTY=0x02000000
WRAPPED=0x08000000
REVERSE=0x00020000
LOOP=0x00010000


def _clock_params(fps, frame_count, start, end, speed, blend, reverse, loop,
                  stop_after, scale_channels, inherited_blend):
    return dict(
        fps=fps, frame_count=frame_count, start_frame=start, end_frame=end,
        speed=speed, blend=blend, reverse=reverse, loop=loop,
        stop_after=stop_after, scale_channels=scale_channels,
        inherited_blend=list(inherited_blend) if inherited_blend is not None else None,
    )


class c_native_clock:
    def __init__(self,fps,frame_count,start=0,end=-1,speed=1,blend=0,
                 reverse=False,loop=False,stop_after=-1,scale_channels=0,inherited_blend=None):
        require(all(math.isfinite(x) for x in (fps,start,end,speed,blend,stop_after)), 'nonfinite clock setup')
        require(fps>0 and type(frame_count) is int and 0<frame_count<=65535,'invalid clock motion timing')
        native_fps=f32(fps)
        require(native_fps>0 and math.isfinite(native_fps),'invalid float32 fps')
        frame_period=f32(1/native_fps)
        require(frame_period>0 and math.isfinite(frame_period),'invalid float32 frame period')
        last=f32(frame_count-1)
        start=min(last,max(0,f32(start)))
        end=last if end<0 else min(last,f32(end))
        require(end>=start,'reversed frame range is unsupported')
        m_start=f32(start*frame_period)
        m_end=f32(end*frame_period)
        m_speed=max(f32(.01),f32(speed))
        m_baseline=f32(m_end+frame_period) if reverse else f32(m_start-frame_period)
        blend_total=blend_remaining=max(0,f32(blend))
        if blend<0 and inherited_blend is not None:
            total,remaining=inherited_blend
            require(all(math.isfinite(v) for v in (total,remaining)) and total>=0 and remaining<=total,'invalid inherited blend')
            blend_total=f32(total);blend_remaining=f32(remaining)
        m_stop_timer=f32(stop_after)
        m_flags=ACTIVE|DIRTY|(REVERSE if reverse else 0)|(LOOP if loop else 0)|(0x100 if scale_channels else 0)
        require(m_start!=m_baseline if not reverse else m_end!=m_baseline,'unrepresentable clock baseline')

        buf = backend._lib.arika_clock_init(json.dumps(_clock_params(
            fps, frame_count, start, end, speed, blend, reverse, loop,
            stop_after, scale_channels, inherited_blend,
        )).encode('utf-8'))
        if not buf.ptr:
            raise BackendError(f"clock_init: {backend._last_error()}")
        try:
            self._state = json.loads(ctypes.string_at(buf.ptr, buf.len).decode('utf-8'))
        finally:
            backend._lib.arika_free_buffer(buf)

        self.m_frame_period=frame_period
        self.m_start=m_start
        self.m_end=m_end
        self.m_speed=m_speed
        self.m_baseline=m_baseline
        self.m_position=m_baseline
        self.m_blend_total=blend_total
        self.m_blend_remaining=blend_remaining
        self.m_stop_timer=m_stop_timer
        self.m_scale_channels=scale_channels
        self.m_flags=m_flags

        self.m_initialization_tick=None
        if self.m_stop_timer==0 or self.m_end<=self.m_start:
            self.m_initialization_tick=self.step(self.m_frame_period)

    @property
    def m_flags(self):
        return self._state['flags']

    @m_flags.setter
    def m_flags(self, value):
        self._state['flags'] = value

    @property
    def m_position(self):
        return self._state['position']

    @m_position.setter
    def m_position(self, value):
        self._state['position'] = value

    @property
    def m_blend_remaining(self):
        return self._state['blend_remaining']

    @m_blend_remaining.setter
    def m_blend_remaining(self, value):
        self._state['blend_remaining'] = value

    @property
    def m_stop_timer(self):
        return self._state['stop_timer']

    @m_stop_timer.setter
    def m_stop_timer(self, value):
        self._state['stop_timer'] = value

    def snapshot(self,carry=0,wrap_fraction=None,advanced=False):
        has_wrap = 1 if wrap_fraction is not None else 0
        wrap = wrap_fraction if wrap_fraction is not None else 0
        buf = backend._lib.arika_clock_snapshot(
            json.dumps(self._state).encode('utf-8'),
            carry, has_wrap, wrap, 1 if advanced else 0,
        )
        if not buf.ptr:
            raise BackendError(f"clock_snapshot: {backend._last_error()}")
        try:
            return json.loads(ctypes.string_at(buf.ptr, buf.len).decode('utf-8'))
        finally:
            backend._lib.arika_free_buffer(buf)

    def step(self,delta):
        require(math.isfinite(delta),'nonfinite clock delta')
        buf = backend._lib.arika_clock_step(
            json.dumps(self._state).encode('utf-8'),
            f32(delta),
        )
        if not buf.ptr:
            raise BackendError(f"clock_step: {backend._last_error()}")
        try:
            result = json.loads(ctypes.string_at(buf.ptr, buf.len).decode('utf-8'))
        finally:
            backend._lib.arika_free_buffer(buf)
        self._state = result['state']
        return result['snapshot']


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
