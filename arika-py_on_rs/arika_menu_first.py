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
    return dict(version=1,groups=groups,literal_sprite_count=sum(len(g['literal_sprites']) for g in groups),
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
