#!/usr/bin/env python3
"""Inspect the first menu-component group, scrolling strips and particle templates."""
import argparse
import json
from pathlib import Path
import struct
from arika_menu_layers import setup_calls


def scaled_records(elf,address,count):
    records=[]
    for index in range(count):
        uvx,uvy,width,height,x,y,sx,sy=struct.unpack('<4h4f',elf.read(address+index*24,24))
        records.append(dict(index=index,address=address+index*24,uv_xywh=[uvx,uvy,width,height],
            placement=[x,y],scale=[sx,sy]))
    return records


def position_source(elf,address):
    try:values=list(struct.unpack('<2f',elf.read(address,8)))
    except ValueError:values=None
    source=getattr(elf,'source_kind',lambda address,size:'file_backed')(address,8) if values is not None else 'runtime_memory_unresolved'
    return dict(address=address,value=values,source=source)


def recover_first_animation(elf, gp, groups):
    """Read common first-layer curves and every subclass's entry direction.

    0x373C50 -> 0x373D60 -> 0x373E60 cover entry and exit.
    0x373EF0 is the common phase-3 emphasis callback.
    0x373A10 dispatches subclass +0x24 once phase 2 is active.
    """
    def curve(values, times, count):
        return dict(values_address=values, times_address=times,
                    values=list(struct.unpack('<' + 'f' * count,
                                               elf.read(values, count * 4))),
                    times=list(struct.unpack('<' + 'f' * count,
                                              elf.read(times, count * 4))))

    components=[]
    for group in groups:
        vt=group['vtable']
        init=elf.words(vt+8,1)[0]
        active=elf.words(vt+0x24,1)[0]
        registers={0:0}
        direction={}
        for word in elf.words(init,16):
            opcode=word>>26
            rs=(word>>21)&31
            rt=(word>>16)&31
            immediate=(word&65535)-(65536 if word&32768 else 0)
            if opcode==9 and rs in registers:
                registers[rt]=registers[rs]+immediate
            elif opcode==0x28 and rs==4 and immediate in (24,25):
                if rt not in registers:
                    raise ValueError('first direction uses unknown MIPS register')
                direction[immediate]=registers[rt]
            if len(direction)==2:
                break
        if set(direction)!={24,25}:
            raise ValueError('missing first-component signed direction bytes')
        components.append(dict(
            item=group['item'], init_callback=init,
            phase_two_callback=active,
            direction=[direction[24],direction[25]]))
    expected=[0x374410,0x374750,0x37a5e0,0x37a860,
              0x374960,0x37b610,0x37bcc0]
    if [c['phase_two_callback'] for c in components]!=expected:
        raise ValueError('first-component phase-two vtable mismatch')
    wave=curve(0x4a9e20,0x4a9e10,4)
    return dict(
        entry=curve(gp-0x4de8,gp-0x4df0,2),
        bounce=curve(0x4a9dd0,0x4a9d90,13),
        exit=curve(gp-0x4dc8,gp-0x4dd0,2),
        emphasis=dict(wave=wave,
                      envelope=curve(gp-0x4dd8,gp-0x4de0,2),
                      period=struct.unpack('<f',elf.read(0x4a9e1c,4))[0]+1.0),
        reset_position=list(struct.unpack('<2f',
                                         elf.read(gp-0x29e0,8))),
        components=components,
        entry_address=0x373d60,
        exit_address=0x373e60,
        phase_two_dispatch=0x373ac8)


def recover_first(elf,gp):
    # item, vtable, setup, draw, position source relative to GP
    specs=[(0,0x4f17b0,0x374530,0x374430,-5952),
           (1,0x4f1800,0x374800,0x374760,-19888),
           (2,0x4f1d30,0x37a700,0x37a600,-19600),
           (3,0x4f1d80,0x37aa90,0x37a910,-19576),
           (4,0x4f1840,0x374b60,0x374980,-19880),
           (5,0x4f1e10,0x37b740,0x37b620,-19528),
           (6,0x4f1ef0,0x37bde0,0x37bce0,-19480)]
    table_specs={3:(0x4a9fd0,6),4:(0x4a9e30,2),5:(0x4aa0d0,4)}
    strips={0:(-19896,144),2:(-19584,128),4:(-19864,416),6:(-19464,128)}
    groups=[]
    for item,vtable,setup,draw,base in specs:
        if elf.words(vtable+48,1)[0]!=draw:raise ValueError('first-group vtable mismatch')
        evidence=setup_calls(elf,setup,stop_before_branch=True,gp=gp)
        if len(evidence['resources'])!=1:raise ValueError('unexpected first-group resource lookups')
        texture=evidence['resources'][0]['entry']
        sprites=[dict(index=i,component_offset=32+i*96,texture_entry=texture,uv_xywh=r['xywh'],
            call_instruction=r['instruction']) for i,r in enumerate(evidence['rectangles'])]
        group=dict(item=item,vtable=vtable,setup=setup,draw=draw,texture_entry=texture,
            base_position=position_source(elf,gp+base),literal_sprites=sprites,evidence=evidence,decorations=[])
        if item in table_specs:
            address,count=table_specs[item]
            group['decoration_table']=dict(address=address,count=count,stride=24,format='s16 uv_xywh[4]; f32 placement[2]; f32 scale[2]')
            group['decorations']=scaled_records(elf,address,count)
            for decoration in group['decorations']:
                decoration['component_offset']=(128 if item==5 else 224)+decoration['index']*96
                decoration['texture_entry']=texture
        if item in strips:
            offset,component_offset=strips[item]
            effects=evidence['strip_effects']
            if item==4:
                # This is the straight-line suffix after the decoration loop's branch.
                # The loop is not executed by constant propagation.
                suffix=evidence['stopped_before_branch']+8
                group['suffix_evidence']=setup_calls(elf,suffix,gp=gp)
                effects=group['suffix_evidence']['strip_effects']
            if len(effects)!=1:raise ValueError('expected one scrolling-strip setup')
            group['scroll_strip']=dict(component_offset=component_offset,descriptor_address=gp+offset,
                uv_xywh=list(struct.unpack('<4h',elf.read(gp+offset,8))),
                parameters=effects[0],setup_helper=0x373ff0,update_helper=0x3740d0,draw_helper=0x374110,
                rotated=bool(effects[0]['orientation']),anchor_mode=3 if effects[0]['orientation'] else 1)
            base=group['base_position']['value'];delta=position_source(elf,gp+{0:-5944,2:-19592,4:-5936,6:-19472}[item])
            if base is not None and delta['value'] is not None:
                group['scroll_strip']['startup_origin']=[struct.unpack('<f',struct.pack('<f',base[i]+delta['value'][i]))[0] for i in range(2)]
        groups.append(group)
    # Item 3 stretches a one-pixel source by a fixed Y scale; its Y offsets are runtime-driven.
    groups[3]['first_sprite_y_scale']=dict(address=gp-19568,value=struct.unpack('<f',elf.read(gp-19568,4))[0])
    groups[3]['runtime_fields']=[dict(role='first_sprite_y_offset',address=gp-5912,initial_value=struct.unpack('<f',elf.read(gp-5912,4))[0]),
        dict(role='second_sprite_y_offset',address=gp-5908,initial_value=struct.unpack('<f',elf.read(gp-5908,4))[0])]
    templates=[]
    for index in range(4):
        fields=struct.unpack('<4h2f',elf.read(0x4aa060+index*16,16))
        templates.append(dict(index=index,address=0x4aa060+index*16,uv_xywh=list(fields[:4]),
            speed_base=fields[4],speed_random_span=fields[5]))
    particles=dict(item=3,texture_entry=11,allocate=0x37ac10,initialize=0x37adb0,draw=0x37aee0,
        sprite_initialize=0x37b0a0,slot_stride=176,slot_count=6,initial_active_slots=5,
        template_table=0x4aa060,templates=templates,seed_position_table=0x4aa0a0,
        seed_positions=[list(struct.unpack('<2f',elf.read(0x4aa0a0+i*8,8))) for i in range(5)],
        runtime_pointer_address=gp-5900,runtime_clip_boundary_address=gp-5904,
        template_selection=dict(shift=5,mask=3),
        limits='RNG state/call ordering, respawning and native runtime playback are not simulated.')
    return dict(version=2,groups=groups,animation=recover_first_animation(elf,gp,groups),
        literal_sprite_count=sum(len(g['literal_sprites']) for g in groups),
        decoration_count=sum(len(g['decorations']) for g in groups),strip_count=sum('scroll_strip' in g for g in groups),
        particles=particles,
        limits=['The first group uses plain sprites; no additional quads are added to the component SVG.',
                'Partial setup scans stop before conditional branches; fixed tables and the item 4 suffix are decoded separately.',
                'Position values use the verified startup subset, not captured runtime writes; native owner playback is not implemented.'])


def main():
    from arika_menus import analyze_menu
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('elf');parser.add_argument('output')
    args=parser.parse_args()
    if Path(args.elf).resolve()==Path(args.output).resolve():parser.error('output must differ from ELF input')
    try:report=analyze_menu(Path(args.elf).read_bytes())['first_components']
    except (OSError,ValueError) as error:parser.error(str(error))
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print('Wrote seven first-component groups: 9 literal sprites, 12 decorations, 4 strips and particle templates')


if __name__=='__main__':main()
