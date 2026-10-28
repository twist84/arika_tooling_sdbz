#!/usr/bin/env python3
"""Trace shared-menu companion slots with explicit RNG state or recorded random inputs."""
import argparse
import json
from pathlib import Path
import random
import struct
from arika_menu_layout import f32
from arika_menu_plain import plain_sprite
from arika_menu_strips import step_phase
from arika_menu_rng import c_native_rng,MASK64

RANDOM_SCALE=f32(1/32767)


def recover_companions(elf,gp):
    templates=[]
    for index in range(3):
        fields=struct.unpack('<4h5f',elf.read(0x4a9ea0+index*28,28))
        templates.append(dict(index=index,address=0x4a9ea0+index*28,uv_xywh=list(fields[:4]),
            depth=fields[4],y_base=fields[5],y_span=fields[6],speed_base=fields[7],speed_span=fields[8]))
    return dict(version=1,slot_count=10,slot_stride=112,texture_entry=2,spawn_x=576,retire_x=-240,
        templates=templates,spawn_address=0x376790,spawn_words=elf.words(0x376790,(0x3768d0-0x376790)//4),
        update_address=0x3768d0,update_words=elf.words(0x3768d0,32),draw_address=0x376950,draw_words=elf.words(0x376950,16),
        global_pointer=gp,reset_position_addresses=[gp-10720,gp-10716],reset_position_initial=list(struct.unpack('<2f',elf.read(gp-10720,8))),
        limits='Reset positions use startup defaults; captured runtime writes and the global RNG state/call ordering are not inferred.')


def random_fraction(value):
    if not isinstance(value,int) or not 0<=value<=0x7fffffff:raise ValueError('random input must be a nonnegative 31-bit integer')
    return f32((value&32767)*RANDOM_SCALE)


def empty_slot(reset_position=None):
    position=[None,None] if reset_position is None else [f32(v) for v in reset_position]
    return dict(active=False,x=position[0],y=position[1],speed=0,depth=0,uv_xywh=[0,0,0,0],template=None)


def spawn_slot(template,random_y,random_speed):
    y=f32(template['y_base']+f32(template['y_span']*random_fraction(random_y)))
    speed=f32(template['speed_base']+f32(template['speed_span']*random_fraction(random_speed)))
    depth=f32(template['depth']+f32(f32(.1)*speed))
    return dict(active=True,x=576.0,y=y,speed=speed,depth=depth,uv_xywh=list(template['uv_xywh']),template=template['index'])


def update_slot(slot,reset_position=None):
    result=dict(slot)
    if not result['active']:return result
    result['x']=f32(result['x']-result['speed'])
    return empty_slot(reset_position) if result['x']<-240 else result


def attempt_spawn(slots,templates,draw_random):
    for index,slot in enumerate(slots):
        if not slot['active']:
            choice=draw_random('template');random_fraction(choice)
            variant=(choice>>5)%3
            slots[index]=spawn_slot(templates[variant],draw_random('height'),draw_random('speed'))
            return index
    return None


def step_state(state,templates,draw_random):
    state['slots']=[update_slot(slot,state.get('reset_position')) for slot in state['slots']]
    return advance_event(state,templates,draw_random)


def advance_event(state,templates,draw_random):
    state['timer']=f32(state['timer']-1);spawned=None;attempted=False
    if state['timer']<=0:
        attempted=True;spawned=attempt_spawn(state['slots'],templates,draw_random)
        state['timer']=f32(90+f32(120*random_fraction(draw_random('timer'))))
    state['phase']=step_phase(state['phase'],2048)
    return dict(attempted=attempted,spawned=spawned)


def main():
    from arika_menus import analyze_menu
    from arika_menu_strip_preview import animated_svg
    from arika_menu_owner import initialize_owner,start_owner,step_owner
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('elf');parser.add_argument('output')
    parser.add_argument('--steps',type=int,default=1800);parser.add_argument('--seed',type=lambda v:int(v,0),default=1)
    parser.add_argument('--rng',choices=['native','python'],default='native',help='native algorithm by default; python retains the older diagnostic stream')
    parser.add_argument('--schedule',choices=['active','owner'],default='active',help='active retains isolated passes; owner initializes and starts the recovered inner lifecycle')
    parser.add_argument('--random-values');parser.add_argument('--svg');parser.add_argument('--stride',type=int,default=15)
    parser.add_argument('--ticks-per-second',type=float,default=60)
    args=parser.parse_args()
    if not 1<=args.steps<=100000:parser.error('steps must be 1..100000')
    paths=[Path(p).resolve() for p in [args.elf,args.output]+([args.random_values] if args.random_values else [])+([args.svg] if args.svg else [])]
    if len(set(paths))!=len(paths):parser.error('all input/output paths must differ')
    try:
        report=analyze_menu(Path(args.elf).read_bytes());kernel=report['shared_companions']
        supplied=json.loads(Path(args.random_values).read_text()) if args.random_values else None
        if supplied is not None and not isinstance(supplied,list):raise ValueError('random-values file must contain an integer array')
        if supplied is None and args.rng=='native' and not 0<=args.seed<=MASK64:raise ValueError('native seed must be an unsigned 64-bit integer')
        native=c_native_rng(args.seed) if supplied is None and args.rng=='native' else None
        generator=random.Random(args.seed);draws=[]
        def draw_random(role):
            if supplied is not None:
                if len(draws)>=len(supplied):raise ValueError('explicit random inputs exhausted')
                value=supplied[len(draws)]
            else:value=native.next() if native is not None else generator.randrange(0x80000000)
            random_fraction(value);draws.append(dict(role=role,value=value));return value
        state=dict(slots=[empty_slot(kernel['reset_position_initial']) for _ in range(10)],timer=0.0,phase=0.0,
            reset_position=kernel['reset_position_initial']);frames=[]
        if args.schedule=='owner':
            state=initialize_owner(kernel,report['tile_companion_owner']);start_owner(state)
        for tick in range(args.steps):
            event=(step_owner if args.schedule=='owner' else step_state)(state,kernel['templates'],draw_random);quads=[]
            for index,slot in enumerate(state['slots']):
                if slot['active']:
                    quads.append(dict(piece=index,template=slot['template'],depth=slot['depth'],
                        **plain_sprite(slot['uv_xywh'],[slot['x'],slot['y']])))
            frames.append(dict(tick=tick,phase=state['phase'],timer=state['timer'],event=event,quads=quads))
            if args.schedule=='owner':frames[-1].update(owner_phase=state['owner_phase'],owner_age=state['owner_age'])
        result=dict(format='ARIKA_MENU_COMPANION_TRACE',version=3,preview_kind='companions',elf_sha256=report['elf_sha256'],startup_model=report['startup']['model'],
            random_source='authored integer array' if supplied is not None else 'native LCG algorithm; authored seed %d'%args.seed if native is not None else 'diagnostic Python RNG; seed %d (not game RNG)'%args.seed,
            rng_state=dict(initial=args.seed,final=native.get_state()) if native is not None else None,
            random_draws=draws,frames=frames,final_state=state,
            limits=['Isolated active update pass: move/retire slots, process event/spawn, then advance tile phase and draw.',
                    'Startup/exit phases, captured global RNG state/call ordering, textures, alpha and final compositing are not reproduced.',
                    'Positions/templates use the verified startup subset, not captured runtime state. Host float32 is not PS2 hardware bit accuracy.'])
        if args.schedule=='owner':
            result.update(version=4,schedule='verified inner owner; explicitly started before sample zero')
            result['limits'][0]='Inner owner update followed by companion geometry export; entry/active/exit dispatch is recovered.'
            result['limits'][1]='Outer menu activation/exit scheduling, global RNG synchronization, textures, alpha and final compositing are not reproduced.'
        svg=animated_svg(result,args.stride,args.ticks_per_second) if args.svg else None
        encoded=json.dumps(result,indent=2,allow_nan=False)+'\n'
    except (ValueError,OSError,OverflowError,KeyError,TypeError) as error:parser.error(str(error))
    Path(args.output).write_text(encoded)
    if args.svg:Path(args.svg).write_text(svg,encoding='utf-8')
    print('Wrote %d companion samples, %d sprite quads and %d explicit random draws'%(len(frames),sum(len(f['quads']) for f in frames),len(draws)))


if __name__=='__main__':main()
