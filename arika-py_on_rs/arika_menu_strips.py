#!/usr/bin/env python3
"""Trace isolated native menu strip clocks and clipped sprite draw commands."""
import argparse
import json
import math
from pathlib import Path
from arika_menu_layout import f32
from arika_menu_plain import s16


def step_phase(phase,period):
    phase=f32(phase);period=f32(period)
    if not math.isfinite(phase) or not math.isfinite(period) or period<=0:raise ValueError('finite phase and positive finite period required')
    result=f32(phase+1)
    return f32(result-period) if result>=period else result


def clipped_strip(uv,orientation,start,end,period,phase,origin,motion_offset=0,depth=0):
    uv=[s16(v) for v in uv]
    if len(uv)!=4 or uv[2]<1 or uv[3]<1:raise ValueError('strip requires positive signed-16-bit source dimensions')
    start,end,period,phase,motion_offset,depth=[f32(v) for v in (start,end,period,phase,motion_offset,depth)]
    x,y=[f32(v) for v in origin]
    if not all(math.isfinite(v) for v in [start,end,period,phase,motion_offset,depth,x,y]) or period<=0 or start>end:
        raise ValueError('invalid strip parameters')
    size=uv[3] if orientation else uv[2]
    rate=f32(f32(size-1)/period)
    position=f32(x+f32(phase*f32(-rate)))
    clip_start=f32(start+motion_offset);clip_end=f32(end+motion_offset)
    commands=[]
    for piece in range(2):
        source=uv[1] if orientation else uv[0]
        extent=s16(size-1)
        if position<clip_start:
            amount=s16(math.trunc(f32(clip_start-position)))
            source=s16(source+amount);extent=s16(extent-amount)
            position=f32(position+amount)
        edge=f32(position+extent)
        if edge>clip_end:extent=s16(extent-math.trunc(f32(edge-clip_end)))
        if extent>0:
            rect=list(uv)
            rect[1 if orientation else 0]=source
            rect[3 if orientation else 2]=s16(extent+1)
            commands.append(dict(piece=piece,uv_xywh=rect,position=[position,y],depth=depth,
                rotation=f32(math.pi/2) if orientation else 0,anchor_mode=3 if orientation else 1))
        position=f32(position+extent);depth=f32(depth+1)
    return dict(commands=commands,final_position=position,final_depth=depth)


def recover_strip_kernels(elf):
    return dict(clock_address=0x3740d0,clock_words=elf.words(0x3740d0,16),
        draw_address=0x374110,draw_words=elf.words(0x374110,(0x374380-0x374110)//4))


def main():
    from arika_menus import analyze_menu
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf');parser.add_argument('output');parser.add_argument('--item',type=int,choices=[0,2,4,6],required=True)
    parser.add_argument('--steps',type=int,default=120);parser.add_argument('--phase',type=float,default=0)
    parser.add_argument('--origin',type=float,nargs=2);parser.add_argument('--motion-offset',type=float,default=0)
    parser.add_argument('--depth',type=float,default=0)
    args=parser.parse_args()
    if not 1<=args.steps<=100000:parser.error('steps must be 1..100000')
    if Path(args.elf).resolve()==Path(args.output).resolve():parser.error('output must differ from ELF input')
    try:
        data=Path(args.elf).read_bytes();report=analyze_menu(data)
        group=report['first_components']['groups'][args.item];strip=group['scroll_strip'];params=strip['parameters']
        origin=args.origin;origin_source='authored'
        if origin is None:
            origin=strip.get('startup_origin')
            if origin is None:parser.error('this item requires explicit --origin X Y')
            origin_source='verified startup baseline; zero component animation offsets'
        phase=f32(args.phase);frames=[]
        for tick in range(args.steps):
            draw=clipped_strip(strip['uv_xywh'],params['orientation'],params['start'],params['end'],params['period'],phase,origin,args.motion_offset,args.depth)
            frames.append(dict(tick=tick,phase=phase,**draw));phase=step_phase(phase,params['period'])
    except (ValueError,OSError,OverflowError) as error:parser.error(str(error))
    result=dict(format='ARIKA_MENU_STRIP_TRACE',version=1,elf_sha256=report['elf_sha256'],item=args.item,
        origin=origin,origin_source=origin_source,motion_offset=args.motion_offset,depth=args.depth,strip=strip,frames=frames,
        limits=['Isolated draw-then-clock-step schedule; game callback ordering and wall-clock tick rate are not inferred.',
                'Clipped sprite commands only: no texture sampling, rotated quad rendering or final compositing.',
                'Host float32 arithmetic does not establish PS2 hardware FPU/accumulator bit accuracy.'])
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Wrote %d strip samples and %d clipped sprite commands'%(len(frames),sum(len(f['commands']) for f in frames)))


if __name__=='__main__':main()
