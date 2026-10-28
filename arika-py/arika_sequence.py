#!/usr/bin/env python3
"""Plan common action transitions and export authored-frame sequence previews."""
import argparse
import bisect
import json
import math
from pathlib import Path
import sys
import struct

import arika_models as models
from arika_models import require
from arika_actions import common_tables, sample_hands
from arika_cht import parse_cht, load_banks, lookup, resolve
from arika_import import sample_track, write_output


def next_segment(records,index):
    require(0<=index<len(records),'segment index out of range')
    flags=records[index]['flags']
    allowed=0x70000 | (0xFF if flags&0x40000 else 0)
    require(flags&~allowed==0,'unsupported sequence flags 0x%08X at segment %d'%(flags,index))
    # 0x1D7120: replay mask precedes stop; stop precedes jump.
    if flags&0x20000:
        return index,'replay'
    if flags&0x10000:
        return None,'stop'
    target=flags&0xFF if flags&0x40000 else index+1
    require(0<=target<len(records),'sequence leaves the table at segment %d'%index)
    return target,'jump' if flags&0x40000 else 'advance'


def plan_sequence(records,motion_resolver):
    require(bool(records),'empty sequence')
    seen={};entries=[];motions={};index=0;clock=0.0
    while index not in seen:
        target,transition=next_segment(records,index)
        motion,binding=motion_resolver(records[index])
        require(math.isfinite(motion['fps']) and motion['fps']>0 and motion['frame_count']>0,'invalid motion timing')
        record=records[index];last=motion['frame_count']-1
        require(all(math.isfinite(record[k]) for k in ('speed','start_frame','end_frame')),'nonfinite sequence timing')
        start=min(last,max(0,record['start_frame']))
        end=last if record['end_frame']<0 else min(last,record['end_frame'])
        require(end>=start,'reversed/empty frame range is unsupported')
        speed=max(.01,record['speed'])
        # Offline preview convention: each authored frame, including the last,
        # occupies one frame interval. This is not the native tick/blend clock.
        span=(end-start+1)/(motion['fps']*speed)
        require(math.isfinite(span) and span>0 and clock+span>clock,'unrepresentable sequence duration')
        seen[index]=len(entries);motions[index]=motion
        entries.append(dict(segment=index,start_time=clock,end_time=clock+span,
            start_frame=start,end_frame=end,effective_speed=speed,fps=motion['fps'],
            transition=transition,next_segment=target,record=dict(record),binding=binding))
        clock+=span
        if target is None:
            return dict(format='ARIKA_ACTION_SEQUENCE',segments=entries,total_path_duration=clock,
                cycle_start=None,cycle_duration=None,timing_model='Authored-frame preview: inclusive frame windows, positive speed floor 0.01; native tick carry/blending are not simulated.'),motions
        index=target
    cycle=seen[index];cycle_start=entries[cycle]['start_time']
    return dict(format='ARIKA_ACTION_SEQUENCE',segments=entries,total_path_duration=clock,
        cycle_start=cycle_start,cycle_duration=clock-cycle_start,
        timing_model='Authored-frame preview: inclusive frame windows, positive speed floor 0.01; native tick carry/blending are not simulated.'),motions


def sample_sequence(plan,times):
    entries=plan['segments'];starts=[e['start_time'] for e in entries]
    result=[];previous=-1
    for time in times:
        require(math.isfinite(time) and time>=previous and time>=0,'sample times must be ordered, finite and nonnegative')
        previous=time;clock=time;iteration=0
        finished=plan['cycle_start'] is None and time>=plan['total_path_duration']
        if plan['cycle_start'] is not None and time>=plan['cycle_start']:
            elapsed=time-plan['cycle_start'];span=plan['cycle_duration']
            iteration=math.floor(elapsed/span)
            clock=plan['cycle_start']+(elapsed%span)
        position=len(entries)-1 if finished else max(0,min(len(entries)-1,bisect.bisect_right(starts,clock)-1))
        entry=entries[position]
        frame=entry['end_frame'] if finished else min(entry['end_frame'],entry['start_frame']+(clock-entry['start_time'])*entry['fps']*entry['effective_speed'])
        result.append(dict(time=time,segment=entry['segment'],motion_time=frame/entry['fps'],
            cycle_iteration=iteration,finished=finished))
    return result


def synthesize_motion(model,plan,motions,samples):
    times=[s['time'] for s in samples]
    tracks={n['name']:{p:[] for p in ('translation','rotation','scale')} for n in model['nodes']}
    sources={index:{n['name']:n for n in motion['nodes'] if 'name' in n} for index,motion in motions.items()}
    hands=[];left=right=0
    for sample in samples:
        index=sample['segment'];time=sample['motion_time'];source=sources[index]
        for node in model['nodes']:
            for path in ('translation','rotation','scale'):
                track=source.get(node['name'],{}).get('tracks',{}).get(path)
                value=sample_track(track['times'],track['values'],time,path,'LINEAR') if track else node[path]
                tracks[node['name']][path].append(list(value))
        state=sample_hands(motions[index],[time],initial=(left,right))[0]
        left,right=state['left'],state['right'];hands.append([left,0,right])
    nodes=[dict(name=n['name'],tracks={p:dict(times=times,values=values) for p,values in tracks[n['name']].items()}) for n in model['nodes'] if n['name']!='HandAni']
    nodes.append(dict(name='HandAni',tracks=dict(translation=dict(times=times,values=hands))))
    rate=1/(times[1]-times[0]) if len(times)>1 else 60
    return dict(name='action_sequence',fps=rate,frame_count=len(times),duration=times[-1]+1/rate,
        last_frame_time=times[-1],nodes=nodes)


def load_plan(elf,cht_path,bank_specs,slot):
    tables=common_tables(Path(elf).read_bytes())
    action=next((a for a in tables['actions'] if a['slot']==slot),None)
    require(action is not None,'common action slot is empty or out of range')
    cht=parse_cht(Path(cht_path).read_bytes());banks=load_banks(bank_specs);cache={}

    def motion_resolver(record):
        binding=resolve(lookup(cht,record['motion_id'],record['variant']),banks)
        require(binding['status']=='resolved','segment motion could not be resolved: '+binding['status'])
        path=binding['package']
        if path not in cache:cache[path]=models.parse_motions(Path(path).read_bytes())['motions']
        return cache[path][binding['package_index']],binding

    plan,motions=plan_sequence(action['records'],motion_resolver)
    plan.update(action_slot=slot,table_address=action['address'],elf_sha256=tables['elf_sha256'],cht_sha256=cht['source_sha256'],
        scope='Reachable common defaults only. Native overrides, event-driven transitions, blending, root-motion accumulation and contextual CHT fallback are not simulated.')
    return plan,motions,[elf,cht_path]+[b['path'] for b in banks.values()]


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for command in ('plan','sample','animate'):
        p=subs.add_parser(command);p.add_argument('elf');p.add_argument('cht');p.add_argument('output')
        p.add_argument('--slot',type=int,required=True);p.add_argument('--bank',action='append',required=True)
        if command!='plan':p.add_argument('--duration',type=float,required=True);p.add_argument('--rate',type=int,default=60)
        if command=='animate':
            p.add_argument('--model',required=True);p.add_argument('--textures');p.add_argument('--ani');p.add_argument('--events')
            p.add_argument('--seed',type=lambda s:int(s,0),default=1);p.add_argument('--no-blink',action='store_true');p.add_argument('--super-form',action='store_true')
    args=parser.parse_args()
    try:
        plan,motions,inputs=load_plan(args.elf,args.cht,args.bank,args.slot)
        if args.command=='plan':
            write_output(args.output,json.dumps(plan,indent=2).encode(),inputs)
        else:
            from arika_face_player import sample_program,sample_timeline
            playback=sample_program([],args.duration,args.rate)
            if args.command=='animate':
                require(bool(args.ani)==bool(args.events),'--ani and --events must be supplied together')
                if args.ani:
                    from arika_faces import parse_face,resolve_timeline
                    events=resolve_timeline(parse_face(Path(args.ani).read_bytes()),json.loads(Path(args.events).read_text(encoding='utf-8')))
                    playback=sample_timeline(events,args.duration,args.rate,args.seed,not args.no_blink,args.super_form)
                    inputs += [args.ani,args.events]
                else:playback=sample_program([],args.duration,args.rate,args.seed,not args.no_blink,args.super_form)
            samples=sample_sequence(plan,[s['time'] for s in playback['samples']])
            if args.command=='sample':
                write_output(args.output,json.dumps(dict(plan=plan,samples=samples),indent=2).encode(),inputs)
            else:
                from arika_face_bake import bake_gltf
                inputs += [args.model]+([args.textures] if args.textures else [])
                require(all(Path(args.output).resolve()!=Path(p).resolve() for p in inputs),'output must differ from inputs')
                model=models.parse_model(Path(args.model).read_bytes())
                motion=synthesize_motion(model,plan,motions,samples);playback['action_sequence']=plan
                texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
                print(json.dumps(bake_gltf(model,playback,args.output,texture,motion,name='action_%d'%args.slot,auto_hands=True)))
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,TypeError,IndexError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
