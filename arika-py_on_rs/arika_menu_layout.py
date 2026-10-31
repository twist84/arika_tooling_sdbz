#!/usr/bin/env python3
"""Extract menu composite geometry and draw an asset-free diagnostic SVG."""
import argparse
import json
from pathlib import Path
import struct

# item, vtable, setup, draw, table, count, GP base offset, component animation array
COMPOSITES = [
    (0,0x4f2250,0x380210,0x380100,0x4aa450,7,-19184,1040),
    (1,0x4f22d0,0x380bd0,0x380ac0,0x4aa620,4,-19128,608),
    (2,0x4f2350,0x381530,0x381380,0x4aa740,9,-19096,1328),
    (3,0x4f2290,0x3807a0,0x380690,0x4aa520,8,-19168,1184),
    (4,0x4f2310,0x380fd0,0x380ec0,0x4aa6a0,5,-19112,752),
    (5,0x4f21d0,0x37fab0,0x37f9a0,0x4aa370,3,-19248,464),
    (6,0x4f2210,0x37fe40,0x37fd30,0x4aa420,2,-19224,320),
]


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def texture_entry(item,part):
    if item in (0,1):return 5
    if item==2:return 6
    if item==3:return 7 if part in (1,2,6) else 6
    if item==4:return 6 if part==1 else 5
    return 7 if item==5 else 8


def pose_part(composite,part,anchors,component_offset=(0,0),part_offset=(0,0),component_depth=0):
    """Unrotated unit-scale sprite quad; dynamic offsets are explicit, not simulated."""
    fields=part['uv_fields']
    if part['uv_interpretation']=='xywh':
        u,v,w,h=fields;uv=[u,v,u+w,v+h]
    else:uv=list(fields)
    width=abs(uv[2]-uv[0]);height=abs(uv[3]-uv[1])
    base=composite['base_position'];offset=part['placement'];sign=composite['component_offset_sign']
    if sign<0:
        x=f32(f32(base[0]-component_offset[0])+f32(offset[0]+part_offset[0]))
        y=f32(f32(base[1]-component_offset[1])+f32(offset[1]+part_offset[1]))
    else:
        x=f32(part_offset[0]+f32(f32(base[0]+component_offset[0])+offset[0]))
        y=f32(part_offset[1]+f32(f32(base[1]+component_offset[1])+offset[1]))
    z=f32(f32(component_depth+15)+offset[2])
    mode=part['anchor_mode']
    if not 0<=mode<len(anchors):raise ValueError('unsupported sprite anchor mode')
    vertices=[[f32(x+f32(width*a)),f32(y+f32(height*b))] for a,b in anchors[mode]['vertices']]
    return dict(position=[x,y,z],uv_endpoints=uv,vertices=vertices,
        bounds=[min(v[0] for v in vertices),min(v[1] for v in vertices),max(v[0] for v in vertices),max(v[1] for v in vertices)])


def recover_layout(elf,gp):
    from arika_menu_layers import recover_layers
    if elf.words(0x3814ec,1)[0]!=0x2a630009:raise ValueError('nine-part item 2 loop mismatch')
    anchors=[]
    for mode,pointer in enumerate(elf.words(0x49a8e0,9)):
        values=struct.unpack('<8f',elf.read(pointer,32))
        anchors.append(dict(mode=mode,address=pointer,vertices=[list(values[i:i+2]) for i in range(0,8,2)]))
    composites=[]
    for item,vtable,setup,draw,table,count,gp_offset,animation_array in COMPOSITES:
        if elf.words(vtable+48,1)[0]!=draw:raise ValueError('composite draw vtable mismatch')
        composite=dict(item=item,vtable=vtable,setup=setup,draw=draw,table_address=table,
            base_address=gp+gp_offset,base_position=list(struct.unpack('<2f',elf.read(gp+gp_offset,8))),
            component_offset_sign=-1 if item==2 else 1,part_animation_array_offset=animation_array,parts=[])
        for index in range(count):
            fields=struct.unpack('<4h3fI',elf.read(table+index*24,24))
            part=dict(index=index,record_address=table+index*24,texture_entry=texture_entry(item,index),
                uv_fields=list(fields[:4]),uv_interpretation='endpoints' if item==0 and index>=5 else 'xywh',
                placement=list(fields[4:7]),anchor_mode=fields[7])
            part['zero_offset_pose']=pose_part(composite,part,anchors)
            composite['parts'].append(part)
        composites.append(composite)
    layers=recover_layers(elf,gp)
    for composite,overlay in zip(composites,layers['item_overlays']):
        part=dict(index=len(composite['parts']),role='overlay',texture_entry=2,
            uv_fields=overlay['uv_xywh'],uv_interpretation='xywh',placement=[0,0,0],anchor_mode=0)
        part['zero_offset_pose']=pose_part(dict(base_position=overlay['base_position'],component_offset_sign=1),part,anchors,component_depth=10)
        composite['item_overlay']=part
    return dict(format='ARIKA_MENU_COMPOSITE_LAYOUT',version=2,anchor_pointer_table=0x49a8e0,
        layers=layers,item_overlay_count=7,
        geometry_helper=0x2fd4a0,anchors=anchors,composites=composites,
        part_count=sum(len(c['parts']) for c in composites),
        limits=['Separate item composites, not a complete menu screen.',
                'Geometry uses zero explicit animation offsets, unit scale and zero rotation.',
                'Background/shared UI, animation curves, clipping and native draw ordering are not simulated.'])


def layout_svg(layout):
    colors=['#5bd8ff','#ffb454','#c6a0ff','#7de3a5','#ff829a','#e6da66','#74c6ba','#ed9bde','#9eb6ff']
    result=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="1960" viewBox="0 0 1280 1960">',
        '<rect width="1280" height="1960" fill="#151922"/>',
        '<g fill="#e4eaf3" font-family="sans-serif"><text x="24" y="30" font-size="21">Menu composite geometry</text>',
        '<text x="24" y="55" font-size="13">%d item + %d shared quads; startup baseline, zero animation offsets. Outlines do not imply visibility. No textures or compositing.</text></g>'%(layout['part_count']+layout.get('item_overlay_count',7)+layout.get('first_plain_count',0),layout.get('shared_plain_count',0))]
    for composite in layout['composites']+layout.get('shared_diagram_groups',[]):
        item=composite['item'];ox=20+(item%2)*630;oy=82+(item//2)*465
        result.append('<g transform="translate(%s %s)">'%(ox,oy))
        result.append('<rect width="610" height="445" rx="8" fill="#202633"/>')
        if composite.get('is_shared'):
            title='Shared layers · %d quads; visibility gates not applied'%len(composite['parts'])
        else:title='Item %d · %d sprite parts + overlay + %d plain'%(item,len(composite['parts']),len(composite.get('plain_parts',[])))
        result.append('<text x="12" y="23" fill="#e4eaf3" font-family="sans-serif" font-size="16">%s</text>'%title)
        # Fit the recovered bounds, rather than guessing a native viewport size.
        diagram_parts=composite['parts'] if composite.get('is_shared') else composite['parts']+[composite['item_overlay']]+composite.get('plain_parts',[])
        bounds=[p['zero_offset_pose']['bounds'] for p in diagram_parts]
        x0=min(b[0] for b in bounds);y0=min(b[1] for b in bounds);x1=max(b[2] for b in bounds);y1=max(b[3] for b in bounds)
        scale=min(560/max(1,x1-x0),350/max(1,y1-y0))
        for part in diagram_parts:
            p=part['zero_offset_pose'];b=p['bounds'];x=25+(b[0]-x0)*scale;y=50+(b[1]-y0)*scale
            color=colors[part['index']%len(colors)]
            result.append('<rect x="%g" y="%g" width="%g" height="%g" fill="%s" fill-opacity="0.05" stroke="%s"/>'%(x,y,(b[2]-b[0])*scale,(b[3]-b[1])*scale,color,color))
            if part.get('role')=='shared':label=part['label'].replace('conditional_overlay','gated overlay')
            elif part.get('role')=='first':label='F:'+part['label'].replace('literal_','L').replace('decoration_','D')
            else:label='overlay' if part.get('role')=='overlay' else str(part['index'])
            text_y=y+13+(part['index']*12 if part.get('role')=='shared' and part['index']<3 else 0)
            result.append('<text x="%g" y="%g" fill="%s" font-family="monospace" font-size="11">%s · tex %d</text>'%(min(x+3,445),text_y,color,label,part['texture_entry']))
        result.append('<text x="12" y="430" fill="#aebbd0" font-family="monospace" font-size="11">Native bounds [%g, %g]–[%g, %g]; diagram auto-fit</text></g>'%(x0,y0,x1,y1))
    result.append('</svg>')
    return '\n'.join(result)+'\n'


def main():
    from arika_menus import analyze_menu
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf');parser.add_argument('svg');parser.add_argument('--json',dest='json_output')
    args=parser.parse_args()
    paths=[Path(args.elf).resolve(),Path(args.svg).resolve()]
    if args.json_output:paths.append(Path(args.json_output).resolve())
    if len(set(paths))!=len(paths):parser.error('input and output paths must differ')
    try:layout=analyze_menu(Path(args.elf).read_bytes())['composite_layout']
    except (ValueError,OSError) as error:parser.error(str(error))
    Path(args.svg).write_text(layout_svg(layout),encoding='utf-8')
    if args.json_output:Path(args.json_output).write_text(json.dumps(layout,indent=2)+'\n')
    print('Wrote 7 item diagrams and shared layer diagram: %d composite parts, 7 overlays, %d first-group and %d shared plain sprites'%(layout['part_count'],layout.get('first_plain_count',0),layout.get('shared_plain_count',0)))


if __name__=='__main__':main()
