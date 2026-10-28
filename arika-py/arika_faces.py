#!/usr/bin/env python3
"""Edit Super Dragon Ball Z facial ANI timelines and export facial playback."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import arika_models as models
import arika_import as importer

require = models.require
# Tables in SLES_541.61 at EE 0x47C1D0 and 0x47C1F0.
EXPRESSION_STATES = [1,3,2,4,5,0,0,0]
BEHAVIOR_AMPLITUDES = [.7,.1,.3,.5,1,0,0,0]
PAIRS = ['AB','AC','AD','BC','BD','CD']


def parse_face(data):
    require(len(data)>=16, 'truncated ANI header')
    count = models.u32(data,0)
    require(0<count<1024 and 16+count*8<=len(data), 'invalid ANI group count')
    groups = []
    pointers = set()
    table_ranges = []
    for i in range(count):
        n, at = struct.unpack_from('<II',data,16+i*8)
        require(at>=16+count*8 and at+n*4<=len(data), 'invalid ANI pointer table')
        starts = list(struct.unpack_from('<'+'I'*n,data,at))
        pointers.update(starts)
        table_ranges.append((at,at+n*4))
        groups.append(dict(index=i,table_offset=at,program_offsets=starts))
    require(pointers, 'ANI has no programs')
    starts = sorted(pointers)
    require(starts[0]>=max(end for _,end in table_ranges), 'ANI programs overlap pointer tables')
    programs = []
    for i, at in enumerate(starts):
        end = starts[i+1] if i+1<len(starts) else len(data)
        require(at<end<=len(data) and (end-at)%8==0, 'invalid ANI record span')
        records = []
        for offset in range(at,end,8):
            time, expression, behavior, flags = struct.unpack_from('<fBBH',data,offset)
            require(math.isfinite(time) and time>=0, 'invalid ANI timestamp')
            require(expression<8 and behavior<8, 'ANI control outside runtime tables')
            require(flags in (0,0x1000), 'unobserved ANI flags; refusing to guess their layout')
            require(not records or not records[-1]['flags']&0x1000, 'records after ANI terminator')
            records.append(dict(offset=offset,time=time,expression=expression,behavior=behavior,flags=flags))
        require(records[-1]['flags']==0x1000, 'ANI program has no END marker')
        programs.append(dict(offset=at,records=records))
    return dict(format='ARIKA_FACE_ANI',source_sha256=hashlib.sha256(data).hexdigest(),
        groups=groups,programs=programs,
        expression_to_pair_state=EXPRESSION_STATES,behavior_amplitudes=BEHAVIOR_AMPLITUDES,
        behavior_notes={'5':'timed expression pulse with standard rise/fall phases',
            '6':'randomized repeated expression pulses; exact preview needs runtime random/tick state'})


def face_catalog(directory):
    """Index per-character ANI groups; the first three are native player face slots."""
    root = Path(directory)
    files = sorted(root.glob('p*/p*.ani'))
    require(bool(files), 'no p*/p*.ani character files found')
    characters = []
    for path in files:
        source = parse_face(path.read_bytes())
        programs = {program['offset']: program for program in source['programs']}
        groups = []
        for group in source['groups']:
            entries = []
            for index, offset in enumerate(group['program_offsets']):
                program = programs[offset]
                records = program['records']
                entries.append(dict(index=index, offset=offset,
                    duration=max((r['time'] for r in records), default=0.0),
                    records=len(records), events=[dict(time=r['time'], expression=r['expression'],
                        behavior=r['behavior']) for r in records if not r['flags'] & 0x1000]))
            groups.append(dict(index=group['index'], native_player_slot=group['index'] if group['index'] < 3 else None,
                               program_count=len(entries), programs=entries))
        characters.append(dict(character=path.parent.name, file=path.as_posix(),
                               source_sha256=source['source_sha256'], groups=groups))
    return dict(format='ARIKA_FACE_CATALOG', native_slot_evidence={
        'player_asset_loader': '0x1E8B98 resolves indexed ANI pointers into player asset slots +0x5C/+0x60/+0x64',
        'player_binding': '0x1EB150 copies those pointers to player+0x7E4/+0x7F0/+0x7FC',
        'slot_0': dict(player_face_handle='player+0x7E4', voice_handle='player+0x7E0',
                       voice_event_action_slot=55,
                       voice_event_motion_id=55, face_start_handler='0x1ECBC0'),
        'slot_1': dict(player_face_handle='player+0x7F0', voice_handle='player+0x7EC',
                       voice_event_action_slots=[232,233],
                       voice_event_motion_ids=[232, 233], face_start_handler='0x1EC2C8'),
        'slot_2': dict(player_face_handle='player+0x7FC', voice_handle='player+0x7F8',
                       voice_event_action_slot=235,
                       voice_event_motion_id=235, face_start_handler='0x1EC6B0'),
        'selection': 'per-character asset loader indexes each ANI group and stores the program pointer on the player',
        'legacy_motion_id_fields': 'voice_event_motion_id(s) are retained for compatibility; native handlers select action-table slots whose records resolve through CHT',
        'voice_readiness': dict(wrapper='0x001F5810',query='0x002FBE30',channel=15,
            audio_channel_table='0x005D2D00',channel_stride=40,state_offset=36,ready_states=[0,1],
            note='incoming context argument is discarded; this gate queries channel 15'),
        'timing': 'face program starts after channel 15 reports ready; elapsed wait varies at runtime',
        'scope': 'native slots 0..2 only; additional ANI groups are retained with an unknown purpose'
    }, characters=characters)


def resolve_timeline(source, document):
    require(document.get('format')=='ARIKA_FACE_EVENTS', 'expected ARIKA_FACE_EVENTS schedule')
    if 'source_sha256' in document:
        require(document['source_sha256']==source['source_sha256'], 'event schedule belongs to another ANI source')
    require(isinstance(document.get('events'),list) and document['events'], 'schedule needs at least one event')
    programs={p['offset']:p for p in source['programs']}
    result=[]
    for event in document['events']:
        group=event['group'];program=event['program'];time=event['time']
        require(type(group) is int and 0<=group<len(source['groups']), 'event group index out of range')
        offsets=source['groups'][group]['program_offsets']
        require(type(program) is int and 0<=program<len(offsets), 'event program index out of range')
        require(type(time) in (int,float) and math.isfinite(time) and time>=0, 'invalid event time')
        result.append(dict(time=time,group=group,program=program,records=programs[offsets[program]]['records']))
    return result


def face_from_json(original, edited):
    source = parse_face(original)
    importer.check_source(original,edited)
    require(edited.get('format')=='ARIKA_FACE_ANI', 'expected facial ANI JSON')
    require(edited['groups']==source['groups'] and len(edited['programs'])==len(source['programs']), 'ANI group/program layout cannot change')
    output = bytearray(original)
    for before,after in zip(source['programs'],edited['programs']):
        require(before['offset']==after['offset'] and len(before['records'])==len(after['records']), 'ANI program extent cannot change')
        for br,ar in zip(before['records'],after['records']):
            require(br['offset']==ar['offset'] and ar['flags']==br['flags'], 'ANI record addresses/terminators cannot change')
            require(isinstance(ar['expression'],int) and 0<=ar['expression']<8 and isinstance(ar['behavior'],int) and 0<=ar['behavior']<8, 'invalid expression/behavior index')
            importer.patch_floats(output,br['offset'],[ar['time']])
            struct.pack_into('<BB',output,br['offset']+4,ar['expression'],ar['behavior'])
    parse_face(output)
    return bytes(output)


def expression_pose(model, pair, blend, super_hair=False, left_hand='A',right_hand='A'):
    require(0<=blend<=1 and math.isfinite(blend), 'blend must be between zero and one')
    result = copy.deepcopy(model)
    by_name = {m['name']:m for m in result['meshes']}
    face_name = 'ShapeHead'+pair
    require(face_name in by_name, 'model has no '+face_name)
    face = by_name[face_name]
    require(face['morph'], 'selected face does not contain endpoint geometry')
    face['default_morph_weight'] = blend
    # Runtime 0x1D5B44..0x1D5BA0 switches texture endpoint using int(blend + .5).
    texture_pair = pair if blend<.5 else ('SDA' if pair=='SAD' else pair[::-1])
    control = by_name.get('HeadTex'+texture_pair)
    if control:
        require(len(control['primitives'])==1, 'unexpected face texture-control geometry')
        material = control['primitives'][0]['material']
        for primitive in face['primitives']:
            primitive['material'] = material
    patterns = ['MeshBody',face_name,'MeshHairS' if super_hair else 'MeshHair',
        'MeshLHand'+left_hand,'MeshRHand'+right_hand]
    patterns = [p for p in patterns if p in by_name]
    return result,patterns


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('json');p.add_argument('input');p.add_argument('output')
    p=subs.add_parser('catalog');p.add_argument('directory');p.add_argument('output')
    p=subs.add_parser('import-json');p.add_argument('original');p.add_argument('edited');p.add_argument('output')
    p=subs.add_parser('pose');p.add_argument('model');p.add_argument('output')
    p.add_argument('--pair',choices=PAIRS+['SAD'],default='AB');p.add_argument('--blend',type=float,default=0)
    p.add_argument('--super-hair',action='store_true');p.add_argument('--left-hand',default='A');p.add_argument('--right-hand',default='A')
    p.add_argument('--textures')
    for command in ('sample','animate','timeline-sample','timeline-animate'):
        p=subs.add_parser(command)
        p.add_argument('ani')
        if command.startswith('timeline-'):
            p.add_argument('events')
        else:
            p.add_argument('--group',type=int,default=0);p.add_argument('--program',type=int,default=0)
            p.add_argument('--face-start',type=float,default=0,help='start ANI at this export time; snapped to the next sample tick')
        p.add_argument('output')
        p.add_argument('--duration',type=float);p.add_argument('--rate',type=int,default=60)
        p.add_argument('--seed',type=lambda s:int(s,0),default=1)
        p.add_argument('--no-blink',action='store_true');p.add_argument('--super-form',action='store_true')
        if command.endswith('animate'):
            p.add_argument('--model',required=True);p.add_argument('--textures')
            p.add_argument('--motion')
            selection=p.add_mutually_exclusive_group()
            selection.add_argument('--motion-index',type=int)
            selection.add_argument('--motion-id',type=int,help='resolve body motion through --cht and --bank')
            p.add_argument('--cht');p.add_argument('--variant',type=int,default=0)
            p.add_argument('--bank',action='append')
            p.add_argument('--loop-motion',action='store_true')
            p.add_argument('--auto-hands',action='store_true',help='animate hand variants from the motion HandAni track')
            p.add_argument('--left-hand',default='A');p.add_argument('--right-hand',default='A')
    args=parser.parse_args()
    try:
        if args.command=='json':
            data=Path(args.input).read_bytes();result=parse_face(data)
            importer.write_output(args.output,json.dumps(result,indent=2).encode(),[args.input])
        elif args.command=='catalog':
            result=face_catalog(args.directory)
            importer.write_output(args.output,json.dumps(result,indent=2).encode(),
                [str(path) for path in sorted(Path(args.directory).glob('p*/p*.ani'))])
        elif args.command=='import-json':
            data=Path(args.original).read_bytes();edited=json.loads(Path(args.edited).read_text(encoding='utf-8'))
            result=face_from_json(data,edited)
            importer.write_output(args.output,result,[args.original,args.edited])
        elif args.command in ('sample','animate','timeline-sample','timeline-animate'):
            from arika_face_player import sample_program, sample_timeline
            from arika_face_bake import bake_gltf
            require(0<=args.seed<=0xFFFFFFFFFFFFFFFF, 'seed must fit uint64')
            source=parse_face(Path(args.ani).read_bytes())
            inputs=[args.ani]
            if args.command.startswith('timeline-'):
                events=resolve_timeline(source,json.loads(Path(args.events).read_text(encoding='utf-8')))
                duration=args.duration if args.duration is not None else max(e['time']+max(r['time'] for r in e['records']) for e in events)+.5
                playback=sample_timeline(events,duration,args.rate,args.seed,not args.no_blink,args.super_form)
                inputs.append(args.events)
                clip_name='facial_event_timeline'
            else:
                require(0<=args.group<len(source['groups']), 'group index out of range')
                group=source['groups'][args.group]
                require(0<=args.program<len(group['program_offsets']), 'program index out of range')
                offset=group['program_offsets'][args.program]
                program=next(p for p in source['programs'] if p['offset']==offset)
                duration=args.duration if args.duration is not None else args.face_start+max(r['time'] for r in program['records'])+.5
                playback=sample_program(program['records'],duration,args.rate,args.seed,not args.no_blink,args.super_form,args.face_start)
                playback.update(group=args.group,program=args.program)
                clip_name='face_g%d_p%d'%(args.group,args.program)
            playback.update(source_sha256=source['source_sha256'])
            if args.command in ('sample','timeline-sample'):
                importer.write_output(args.output,json.dumps(playback,indent=2).encode(),inputs)
            else:
                if args.motion_id is not None:
                    from arika_cht import parse_cht, lookup, load_banks, resolve
                    require(args.cht and args.bank,'--motion-id requires --cht and --bank')
                    require(not args.motion,'--motion cannot be combined with --motion-id')
                    banks=load_banks(args.bank)
                    binding=resolve(lookup(parse_cht(Path(args.cht).read_bytes()),args.motion_id,args.variant),banks)
                    require(binding['status']=='resolved','motion could not be resolved: '+binding['status'])
                    binding.update(motion_id=args.motion_id,cht_sha256=hashlib.sha256(Path(args.cht).read_bytes()).hexdigest())
                    args.motion=binding['package'];args.motion_index=binding['package_index']
                    playback['motion_binding']=binding
                    inputs += [args.cht]+[b['path'] for b in banks.values()]
                else:
                    require(not args.cht and not args.bank and args.variant==0,'--cht, --bank and --variant require --motion-id')
                    args.motion_index=0 if args.motion_index is None else args.motion_index
                require(not args.loop_motion or args.motion, '--loop-motion requires --motion')
                require(not args.auto_hands or args.motion, '--auto-hands requires --motion')
                require(not args.auto_hands or (args.left_hand=='A' and args.right_hand=='A'), '--auto-hands cannot be combined with explicit nondefault hand variants')
                inputs += [args.model] + ([args.motion] if args.motion else []) + ([args.textures] if args.textures else [])
                require(all(Path(args.output).resolve()!=Path(i).resolve() for i in inputs), 'output must differ from inputs')
                model=models.parse_model(Path(args.model).read_bytes())
                motion=None
                if args.motion:
                    motions=models.parse_motions(Path(args.motion).read_bytes())['motions']
                    require(0<=args.motion_index<len(motions), 'motion index out of range')
                    motion=motions[args.motion_index]
                textures=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
                result=bake_gltf(model,playback,args.output,textures,motion,args.loop_motion,args.left_hand,args.right_hand,
                    clip_name,auto_hands=args.auto_hands)
                print(json.dumps(result))
        else:
            require(Path(args.model).resolve()!=Path(args.output).resolve(), 'output must differ from model input')
            model=models.parse_model(Path(args.model).read_bytes())
            pose,patterns=expression_pose(model,args.pair,args.blend,args.super_hair,args.left_hand,args.right_hand)
            textures=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
            models.export_gltf(pose,args.output,patterns=patterns,texture_path=textures)
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,IndexError,TypeError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
