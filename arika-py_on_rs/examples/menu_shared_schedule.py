#!/usr/bin/env python3
"""Diagnostic shared scheduling: native owner, explicit no-op banner/small updates.

Run from any directory: python menu_shared_schedule.py output.json
The initial shared phase, seed and exit request are authored choices.
"""
import json
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from arika_menu_shared import initialize_shared,request_exit,step_shared
from arika_menu_owner import initialize_owner,start_owner,step_owner
from arika_menu_rng import c_native_rng
from arika_menu_banner import initialize_banner,start_banner,exit_banner,step_banner,draw_banner
from arika_menu_small import initialize_small,start_small,step_small,draw_small


def trace_schedule(report,banner_motion=False,small_motion=False):
    shared=initialize_shared();shared['phase']=1
    owner=initialize_owner(report['shared_companions'],report['tile_companion_owner'])
    banner=initialize_banner(report['shared_banner']) if banner_motion else None
    small=[initialize_small() for _ in range(7)] if small_motion else None
    rng=c_native_rng(1);frames=[];draws=[]
    for tick in range(140):
        if tick==120:request_exit(shared)
        owner_event=None
        def draw(role):
            value=rng.next();draws.append(dict(tick=tick,role=role,value=value));return value
        def child(role,index):
            nonlocal owner_event
            if role=='update_owner':owner_event=step_owner(owner,report['shared_companions']['templates'],draw)
            elif role=='start_owner':start_owner(owner)
            elif small is not None and role in ('update_small','start_small'):
                component=report['shared_small_animation']['components'][index]
                if role=='update_small':step_small(small[index],component,report['shared_small_animation'])
                else:start_small(small[index],component,report['shared_small_animation'])
                shared['small_phases'][index]=small[index]['phase']
            elif banner is not None:
                if role=='update_banner':step_banner(banner,report['shared_banner'])
                elif role=='start_banner':start_banner(banner)
                elif role=='exit_banner':exit_banner(banner)
            # Disabled child animation callbacks deliberately perform no work.
        calls=step_shared(shared,report['shared_scheduler'],child)
        frames.append(dict(tick=tick,shared=json.loads(json.dumps(shared)),calls=calls,
            owner_phase=owner['owner_phase'],owner_age=owner['owner_age'],tile_phase=owner['phase'],
            event_timer=owner['timer'],active_slots=sum(s['active'] for s in owner['slots']),owner_event=owner_event))
        if banner is not None:frames[-1]['banner']=dict(**json.loads(json.dumps(banner)),geometry=draw_banner(banner,report['shared_banner']))
        if small is not None:frames[-1]['small_components']=[dict(**json.loads(json.dumps(s)),geometry=draw_small(s,c)) for s,c in zip(small,report['shared_small_animation']['components'])]
    result=dict(format='ARIKA_MENU_SHARED_SCHEDULE_TRACE',version=1,elf_sha256=report['elf_sha256'],
        frames=frames,random_draws=draws,rng_state=dict(initial=1,final=rng.get_state()),
        limits=['Shared phase 1 at sample zero, native RNG seed 1 and exit request at sample 120 are authored.',
                'Banner/small animation updates and start effects are explicit no-ops; scheduler small phase writes are retained.',
                'Inner owner updates are recovered. No textures, pixel output, outer activation timing or native tick frequency is inferred.'])
    if banner is not None:
        result['version']=2
        result['limits'][1]='Recovered banner animation is enabled. Small animation updates/start callbacks remain no-ops; scheduler phase writes are retained.'
    if small is not None:
        result['version']=3
        result['limits'][1]='Recovered small-component motion is enabled; banner motion is %s. No child exit requests beyond the recovered shared calls are invented.'%('enabled' if banner is not None else 'disabled')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');parser.add_argument('--banner',action='store_true')
    parser.add_argument('--small',action='store_true')
    args=parser.parse_args();output=Path(args.output).resolve()
    if output in (Path(__file__).resolve(),ROOT/'research/main_menu_map.json'):raise SystemExit('output must differ from inputs')
    report=json.loads((ROOT/'research/main_menu_map.json').read_text())
    output.write_text(json.dumps(trace_schedule(report,args.banner,args.small),indent=2,allow_nan=False)+'\n')
