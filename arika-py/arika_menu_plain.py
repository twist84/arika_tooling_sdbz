#!/usr/bin/env python3
"""Recover axis-aligned plain-sprite menu geometry without runtime-position guesses."""
import argparse
import json
from pathlib import Path
from arika_menu_layout import f32


def s16(value):
    return ((int(value)+32768)&65535)-32768


def plain_sprite(uv_fields,position,scale=(1,1),uv_interpretation='xywh'):
    if len(uv_fields)!=4 or len(position)!=2 or len(scale)!=2:raise ValueError('invalid sprite dimensions')
    uv=[s16(v) for v in uv_fields]
    if uv_interpretation=='xywh':uv=[uv[0],uv[1],s16(uv[0]+uv[2]),s16(uv[1]+uv[3])]
    elif uv_interpretation!='endpoints':raise ValueError('unknown UV interpretation')
    x,y=[f32(v) for v in position];sx,sy=[f32(v) for v in scale]
    width=abs(uv[2]-uv[0]);height=abs(uv[3]-uv[1])
    right=f32(x+f32(sx*width));bottom=f32(y+f32(sy*height))
    return dict(position=[x,y],scale=[sx,sy],uv_endpoints=uv,
        vertices=[[x,y],[right,y],[x,bottom],[right,bottom]],
        bounds=[min(x,right),min(y,bottom),max(x,right),max(y,bottom)])


def recover_plain(elf,gp,first,layers):
    first_groups=[];unresolved=[]
    for group in first['groups']:
        item=group['item'];base=group['base_position']['value'];parts=[]
        for literal in group['literal_sprites']:
            label='literal_%d'%literal['index']
            if base is None:
                unresolved.append(dict(group='first',item=item,part=label,
                    reason='runtime base position' if base is None else 'runtime Y offset'))
                continue
            position=list(base)
            scale=[1,1]
            if item==3:
                position[1]=f32(position[1]+group['runtime_fields'][literal['index']]['initial_value'])
                if literal['index']==0:scale[1]=group['first_sprite_y_scale']['value']
            if item==4 and literal['index']==1:
                import struct
                offsets=struct.unpack('<2f',elf.read(gp-19872,8))
                position=[f32(base[i]+offsets[i]) for i in range(2)]
            parts.append(dict(label=label,texture_entry=literal['texture_entry'],
                component_offset=literal['component_offset'],geometry=plain_sprite(literal['uv_xywh'],position,scale)))
        for decoration in group['decorations']:
            if base is None:
                unresolved.append(dict(group='first',item=item,part='decoration_%d'%decoration['index'],reason='runtime base position'))
                continue
            position=[f32(base[i]+decoration['placement'][i]) for i in range(2)]
            parts.append(dict(label='decoration_%d'%decoration['index'],texture_entry=decoration['texture_entry'],
                component_offset=decoration['component_offset'],geometry=plain_sprite(decoration['uv_xywh'],position,decoration['scale'])))
        first_groups.append(dict(item=item,parts=parts))
    shared=[]
    setups=layers['shared_setups']
    for label,texture,rect,position,scale,condition in [
        ('background',1,setups[0]['evidence']['rectangles'][0]['xywh'],[0,0],[1,1],'shared draw'),
        ('conditional_overlay',8,setups[0]['evidence']['rectangles'][1]['xywh'],[0,0],[512,448],'shared byte +224 == 0; alpha is state-driven')]:
        shared.append(dict(label=label,texture_entry=texture,draw_condition=condition,geometry=plain_sprite(rect,position,scale)))
    import struct
    banner=list(struct.unpack('<2f',elf.read(gp-19704,8)))
    shared.append(dict(label='banner',texture_entry=2,geometry=plain_sprite(setups[1]['evidence']['rectangles'][0]['xywh'],banner)))
    for component in layers['shared_small_components']:
        base=component['base_position']
        if base is None:
            unresolved.append(dict(group='shared',part='small_%d'%component['index'],reason='runtime base position'))
        else:shared.append(dict(label='small_%d'%component['index'],texture_entry=3,
            draw_condition='component state != 0',geometry=plain_sprite(component['evidence']['rectangles'][0]['xywh'],base)))
    return dict(version=1,draw_helper=0x2fddb0,endpoint_kernel=dict(address=0x2fe138,words=elf.words(0x2fe138,30)),
        first_groups=first_groups,first_quad_count=sum(len(g['parts']) for g in first_groups),
        shared=shared,shared_quad_count=len(shared),unresolved=unresolved,
        separate_passes=[dict(group='shared',part='tiled_element',tool='arika_menu_tiles.py',reason='phase-dependent isolated pass; omitted from static diagram')],
        limits=['Zero explicit component animation offsets; no frame visibility is inferred.',
                'UVs remain pixel endpoints. Texture normalization, sampling, clipping, depth and final compositing are not simulated.',
                'Host float32 arithmetic is not a PS2 hardware bit-accuracy claim.',
                'Conditional overlay geometry does not imply that its alpha or draw gate permits visibility.'])


def main():
    from arika_menus import analyze_menu
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('elf');parser.add_argument('output')
    args=parser.parse_args()
    if Path(args.elf).resolve()==Path(args.output).resolve():parser.error('output must differ from ELF input')
    try:report=analyze_menu(Path(args.elf).read_bytes())['plain_sprite_geometry']
    except (ValueError,OSError) as error:parser.error(str(error))
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print('Wrote %d first-group and %d shared plain-sprite quads'%(report['first_quad_count'],report['shared_quad_count']))


if __name__=='__main__':main()
