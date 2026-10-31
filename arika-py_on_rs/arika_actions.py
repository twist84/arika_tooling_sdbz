#!/usr/bin/env python3
"""Inspect common action tables in SLES_541.61 and sample hand-selection tracks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import arika_models as models
from arika_import import write_output
from arika_face_player import f32


REFERENCE_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'


class c_elf_reader:
    def __init__(self, data):
        models.require(len(data) >= 52 and data[:7] == b'\x7fELF\x01\x01\x01', 'expected little-endian ELF32')
        self.m_data = data
        self.m_segments = []
        phoff = struct.unpack_from('<I', data, 28)[0]
        size, count = struct.unpack_from('<HH', data, 42)
        models.require(size >= 32 and phoff + count * size <= len(data), 'invalid ELF program headers')
        for i in range(count):
            kind, offset, address, _, length = struct.unpack_from('<5I', data, phoff + i * size)
            if kind == 1:
                models.require(offset + length <= len(data), 'truncated ELF segment')
                self.m_segments.append((address, offset, length))

    def read(self, address, length):
        for base, offset, size in self.m_segments:
            if base <= address and address + length <= base + size:
                return self.m_data[offset + address - base:offset + address - base + length]
        raise ValueError('address outside ELF file-backed segments: 0x%08X' % address)


def parse_table(reader, address, count):
    models.require(0 < count <= 1000, 'invalid action record count')
    data = reader.read(address, count * 20)
    result = []
    import math
    for i in range(count):
        motion, variant, speed, start, end, flags = struct.unpack_from('<HHfffI', data, i * 20)
        models.require(all(math.isfinite(v) for v in (speed, start, end)), 'nonfinite action record')
        result.append(dict(index=i, address=address+i*20, motion_id=motion, variant=variant,
                           speed=speed, start_frame=start, end_frame=end, flags=flags,
                           flags_hex='0x%08X' % flags))
    return result


def common_tables(data):
    digest = hashlib.sha256(data).hexdigest()
    models.require(digest == REFERENCE_SHA256, 'common table addresses require the supplied SLES_541.61 reference ELF')
    reader = c_elf_reader(data)
    pointers = struct.unpack('<1000I', reader.read(0x49E5C0, 4000))
    addresses = sorted(set(pointers) - {0}) + [0x49E5C0]
    tables = {}
    for address, end in zip(addresses, addresses[1:]):
        count, padding = divmod(end-address, 20)
        models.require(count > 0 and padding < 16 and not any(reader.read(address+count*20, padding)),
                       'unexpected common action table boundary')
        tables[address] = parse_table(reader, address, count)
    return dict(format='ARIKA_COMMON_ACTIONS', elf_sha256=digest, pointer_table=0x49E5C0,
                scope='Common defaults before character-specific native overrides; not a gameplay script.',
                actions=[dict(slot=i, address=p, records=tables[p]) for i,p in enumerate(pointers) if p])


def resolve_action(action, cht, banks):
    from arika_cht import lookup, resolve
    segments=[]
    for record in action['records']:
        try:
            binding=resolve(lookup(cht,record['motion_id'],record['variant']),banks)
        except ValueError as error:
            binding=dict(status='missing_cht_entry',reason=str(error))
        segments.append(dict(record,binding=binding))
    return dict(format='ARIKA_ACTION_MOTION_RESOLUTION',slot=action['slot'],address=action['address'],
        cht_sha256=cht['source_sha256'],segments=segments,
        scope='Common action table and this CHT only; native table overrides and contextual CHT fallback are not applied. Each segment is resolved independently; sequence flags are preserved, not executed.')


def resolve_hands(model):
    """Runtime 0x1D55B4: A..J, carrying forward the last existing mesh."""
    by_name = {mesh['name']:mesh for mesh in model['meshes']}
    result = {}
    for side in ('L', 'R'):
        prefix = 'Mesh'+side+'Hand'
        last = by_name.get(prefix)
        choices = []
        for letter in 'ABCDEFGHIJ':
            last = by_name.get(prefix+letter, last)
            choices.append(last)
        result[side] = choices
    return result


def sample_hands(motion, times, loop=False, initial=(0,0)):
    """HandAni translation X/Z -> left/right; negative integers retain selection."""
    node = next((n for n in motion['nodes'] if n.get('name') == 'HandAni'), None)
    track = node['tracks']['translation'] if node else None
    left, right = initial
    output = []
    for time in times:
        sample_time = time
        time = time % motion['duration'] if loop else min(time, motion['last_frame_time'])
        if track:
            # 0x1D7C38 passes t1=1: 0x1B7E90 zeros the interpolation factor.
            # The native search also snaps to a key within float32 1e-5 seconds.
            keys = track['times']; values = track['values']
            i = 0
            if f32(time) > 0:
                for j,key in enumerate(keys):
                    if abs(f32(key-f32(time))) < f32(1e-5):
                        i = j; break
                    if key > f32(time): break
                    i = j
            value = list(values[i])
        else:
            value = [0,0,0]
        requested = (int(value[0]), int(value[2]))
        for index in requested:
            models.require(index < 10, 'HandAni index exceeds the runtime hand table')
        if requested[0] >= 0: left = requested[0]
        if requested[1] >= 0: right = requested[1]
        output.append(dict(time=sample_time, motion_time=time, left=left, right=right,
                           requested_left=requested[0], requested_right=requested[1]))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('tables'); p.add_argument('elf'); p.add_argument('output')
    p = subs.add_parser('table'); p.add_argument('elf'); p.add_argument('output')
    p.add_argument('--address',type=lambda s:int(s,0),required=True)
    p.add_argument('--count',type=int,required=True)
    p = subs.add_parser('hands'); p.add_argument('motion'); p.add_argument('output')
    p.add_argument('--motion-index', type=int, default=0)
    p.add_argument('--rate', type=int, default=60)
    p = subs.add_parser('motion'); p.add_argument('motion'); p.add_argument('output')
    p.add_argument('--model',required=True); p.add_argument('--textures')
    p.add_argument('--motion-index',type=int,default=0)
    p.add_argument('--duration',type=float); p.add_argument('--rate',type=int,default=60)
    p.add_argument('--loop-motion',action='store_true'); p.add_argument('--no-blink',action='store_true')
    p.add_argument('--seed',type=lambda s:int(s,0),default=1); p.add_argument('--super-form',action='store_true')
    p = subs.add_parser('resolve',help='resolve common action segments through a character CHT')
    p.add_argument('elf');p.add_argument('cht');p.add_argument('output')
    p.add_argument('--slot',type=int,required=True);p.add_argument('--bank',action='append',required=True)
    p = subs.add_parser('motion-id',help='export a CHT logical motion and variant without a package index')
    p.add_argument('cht');p.add_argument('output');p.add_argument('--id',type=int,required=True)
    p.add_argument('--variant',type=int,default=0);p.add_argument('--bank',action='append',required=True)
    p.add_argument('--model',required=True);p.add_argument('--textures')
    p.add_argument('--duration',type=float);p.add_argument('--rate',type=int,default=60)
    p.add_argument('--loop-motion',action='store_true');p.add_argument('--no-blink',action='store_true')
    p.add_argument('--seed',type=lambda s:int(s,0),default=1);p.add_argument('--super-form',action='store_true')
    args = parser.parse_args()
    try:
        if args.command in ('resolve','motion-id'):
            from arika_cht import parse_cht, load_banks, lookup, resolve
            cht=parse_cht(Path(args.cht).read_bytes());banks=load_banks(args.bank)
            inputs=[args.cht]+[bank['path'] for bank in banks.values()]
            if args.command=='resolve':
                tables=common_tables(Path(args.elf).read_bytes())
                action=next((a for a in tables['actions'] if a['slot']==args.slot),None)
                models.require(action is not None,'common action slot is empty or out of range')
                result=resolve_action(action,cht,banks);result['elf_sha256']=tables['elf_sha256']
                inputs.append(args.elf)
            else:
                from arika_face_player import sample_program
                from arika_face_bake import bake_gltf
                binding=resolve(lookup(cht,args.id,args.variant),banks)
                models.require(binding['status']=='resolved','motion could not be resolved: '+binding['status'])
                binding.update(motion_id=args.id,cht_sha256=cht['source_sha256'])
                inputs += [args.model]+([args.textures] if args.textures else [])
                models.require(all(Path(args.output).resolve()!=Path(p).resolve() for p in inputs),'output must differ from inputs')
                motion=models.parse_motions(Path(binding['package']).read_bytes())['motions'][binding['package_index']]
                model=models.parse_model(Path(args.model).read_bytes())
                duration=args.duration if args.duration is not None else motion['duration']
                playback=sample_program([],duration,args.rate,args.seed,not args.no_blink,args.super_form)
                playback['motion_binding']=binding
                texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
                result=bake_gltf(model,playback,args.output,texture,motion,args.loop_motion,
                    name='motion_%d_variant_%d'%(args.id,args.variant),auto_hands=True)
                print(json.dumps(result));return 0
        elif args.command == 'table':
            data=Path(args.elf).read_bytes()
            models.require(hashlib.sha256(data).hexdigest()==REFERENCE_SHA256,'reference ELF required')
            result=dict(format='ARIKA_ACTION_TABLE',elf_sha256=REFERENCE_SHA256,
                        records=parse_table(c_elf_reader(data),args.address,args.count))
            inputs=[args.elf]
        elif args.command == 'tables':
            result = common_tables(Path(args.elf).read_bytes()); inputs = [args.elf]
        else:
            motions = models.parse_motions(Path(args.motion).read_bytes())['motions']
            models.require(0 <= args.motion_index < len(motions), 'motion index out of range')
            motion = motions[args.motion_index]
            if args.command == 'motion':
                from arika_face_player import sample_program
                from arika_face_bake import bake_gltf
                inputs=[args.motion,args.model]+([args.textures] if args.textures else [])
                models.require(all(Path(args.output).resolve()!=Path(p).resolve() for p in inputs),'output must differ from inputs')
                models.require(0<=args.seed<=0xFFFFFFFFFFFFFFFF,'seed must fit uint64')
                model=models.parse_model(Path(args.model).read_bytes())
                duration=args.duration if args.duration is not None else motion['duration']
                playback=sample_program([],duration,args.rate,args.seed,not args.no_blink,args.super_form)
                texture=args.textures or (Path(args.model).with_suffix('.pix') if Path(args.model).with_suffix('.pix').exists() else None)
                result=bake_gltf(model,playback,args.output,texture,motion,args.loop_motion,
                                 name=motion['name']+'_hands',auto_hands=True)
                print(json.dumps(result)); return 0
            models.require(1 <= args.rate <= 120, 'rate must be 1..120')
            import math
            times = [i/args.rate for i in range(math.ceil(motion['last_frame_time']*args.rate)+1)]
            result = dict(format='ARIKA_HAND_PLAYBACK', motion=motion['name'], sample_rate=args.rate,
                          source_sha256=motion['source_sha256'], samples=sample_hands(motion,times))
            inputs = [args.motion]
        write_output(args.output, json.dumps(result,indent=2).encode(), inputs)
        print('Wrote '+args.output)
    except (OSError,ValueError,KeyError,IndexError,TypeError,struct.error) as error:
        print('error: '+str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
