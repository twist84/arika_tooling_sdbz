#!/usr/bin/env python3
"""Trace the isolated native shared-menu tile scroll and its two sprite copies."""
import argparse
import json
import math
from pathlib import Path
import struct
from arika_menu_layout import f32
from arika_menu_plain import plain_sprite
from arika_menu_strips import step_phase


def recover_tile_kernel(elf,gp):
    if elf.words(0x37603c,1)[0]!=0x3c0242aa:raise ValueError('tile depth initializer mismatch')
    return dict(draw_address=0x376290,draw_words=elf.words(0x376290,(0x376358-0x376290)//4),
        clock_address=0x3761b0,clock_words=elf.words(0x3761b0,(0x376280-0x3761b0)//4),
        global_pointer=gp,base_address=gp-19792,base_position=list(struct.unpack('<2f',elf.read(gp-19792,8))),
        period=2048,texture_entry=2,uv_xywh=[0,384,512,128],initial_depth=85,
        draw_companion_calls=[0x3763b0,0x376600],
        limits='This exporter isolates tile phase arithmetic. Companion timer and inner owner lifecycle are separate modules; full outer menu scheduling is not reproduced.')


def tile_draw(phase,base,offset=(0,0),uv=(0,384,512,128),depth=85):
    if len(base)!=2 or len(offset)!=2 or len(uv)!=4:raise ValueError('invalid tile dimensions')
    if uv[2]<=0 or uv[3]<=0:raise ValueError('positive source dimensions required')
    phase=f32(phase);base=[f32(v) for v in base];offset=[f32(v) for v in offset];depth=f32(depth)
    if not all(math.isfinite(v) for v in [phase,depth]+base+offset):raise ValueError('finite tile inputs required')
    endpoints=plain_sprite(uv,[0,0])['uv_endpoints']
    width=endpoints[2]-endpoints[0]
    position=f32(f32(base[0]+offset[0])+f32(f32(-f32(width/2048))*phase))
    y=f32(base[1]+offset[1]);quads=[]
    for piece in range(2):
        geometry=plain_sprite(uv,[position,y])
        quads.append(dict(piece=piece,depth=depth,**geometry))
        position=f32(position+width)
    return dict(quads=quads,final_sprite_position=[position,y])




def main():
    from arika_menus import analyze_menu
    from arika_menu_strip_preview import animated_svg
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf');parser.add_argument('output');parser.add_argument('--steps',type=int,default=2050)
    parser.add_argument('--phase',type=float,default=0);parser.add_argument('--offset',type=float,nargs=2,default=[0,0])
    parser.add_argument('--svg');parser.add_argument('--stride',type=int,default=15);parser.add_argument('--ticks-per-second',type=float,default=60)
    args=parser.parse_args()
    if not 1<=args.steps<=100000:parser.error('steps must be 1..100000')
    paths=[Path(p).resolve() for p in [args.elf,args.output]+([args.svg] if args.svg else [])]
    if len(set(paths))!=len(paths):parser.error('all input/output paths must differ')
    try:
        report=analyze_menu(Path(args.elf).read_bytes());kernel=report['tile_scroll_kernel'];phase=f32(args.phase);frames=[]
        for tick in range(args.steps):
            draw=tile_draw(phase,kernel['base_position'],args.offset,kernel['uv_xywh'],kernel['initial_depth'])
            frames.append(dict(tick=tick,phase=phase,**draw));phase=step_phase(phase,kernel['period'])
        result=dict(format='ARIKA_MENU_TILE_TRACE',version=1,preview_kind='tile',elf_sha256=report['elf_sha256'],
            offset=args.offset,kernel=kernel,frames=frames,
            limits=['Isolated draw-then-phase-step schedule; no native callback ordering or wall-clock rate is inferred.',
                    'Companion effects, owner animation/state, texture sampling, clipping and final compositing are not simulated.',
                    'Host float32 arithmetic does not establish PS2 hardware FPU/accumulator bit accuracy.'])
        svg=animated_svg(result,args.stride,args.ticks_per_second) if args.svg else None
        encoded=json.dumps(result,indent=2,allow_nan=False)+'\n'
    except (ValueError,OSError,OverflowError,KeyError,TypeError) as error:parser.error(str(error))
    Path(args.output).write_text(encoded)
    if args.svg:Path(args.svg).write_text(svg,encoding='utf-8')
    print('Wrote %d tile samples and %d quads'%(len(frames),len(frames)*2))


if __name__=='__main__':main()
