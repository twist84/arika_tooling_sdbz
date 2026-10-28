#!/usr/bin/env python3
"""Build a self-contained textured menu lab from the supplied FPIX and ELF report."""
import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import struct
import zlib
from arika_dat import container,tim2_rgba


def rgba_png(width,height,rgba):
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
    rows=b''.join(b'\0'+rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


def texture_assets(data):
    metadata=container(data);assets=[]
    for entry in metadata['chunks']:
        body=data[entry['offset']:entry['offset']+entry['size']]
        if entry['magic']!='XPIX' or body[32:36]!=b'TIM2':raise ValueError('expected XPIX/TIM2 texture entries')
        w,h,rgba=tim2_rgba(body[32:])
        assets.append(dict(index=entry['index'],width=w,height=h,sha256=hashlib.sha256(body).hexdigest(),
            png='data:image/png;base64,'+base64.b64encode(rgba_png(w,h,rgba)).decode('ascii')))
    return assets


def build_payload(report,pix,trace):
    assets=texture_assets(pix)
    if len(assets)!=report['resource']['entry_count']:raise ValueError('texture count differs from researched resource')
    if trace['elf_sha256']!=report['elf_sha256']:raise ValueError('trace/report ELF mismatch')
    items=[]
    for composite in report['composite_layout']['composites']:
        first=[dict(texture_entry=p['texture_entry'],geometry=dict(p['zero_offset_pose'],depth=47)) for p in composite['plain_parts']]
        middle=[dict(texture_entry=p['texture_entry'],geometry=dict(p['zero_offset_pose'],depth=p['zero_offset_pose']['position'][2]+45)) for p in composite['parts']]
        p=composite['item_overlay'];overlay=[dict(texture_entry=p['texture_entry'],geometry=dict(p['zero_offset_pose'],depth=70))]
        arrows=[dict(texture_entry=0,geometry=p['geometry']) for p in report['arrow_baselines']['items'][composite['item']]['variants'][0]]
        items.append(dict(first=first,middle=middle,overlay=overlay,arrows=arrows))
    shared=report['plain_sprite_geometry']['shared']
    frames=[]
    from arika_menu_tiles import tile_draw
    from arika_menu_labels import trace_labels
    from arika_menu_characters import trace_characters
    from arika_menu_strips import clipped_strip
    from arika_menu_strip_preview import command_quad
    labels=trace_labels(report,len(trace['frames']))['frames']
    characters=trace_characters(report,len(trace['frames']))['frames']
    idle_characters=trace_characters(report,len(trace['frames']),idle=True)['frames']
    shake_characters=trace_characters(report,len(trace['frames']),emphasis_tick=80)['frames']
    shake_idle_characters=trace_characters(report,len(trace['frames']),idle=True,emphasis_tick=80)['frames']
    shake_labels=trace_labels(report,len(trace['frames']),emphasis_tick=80)['frames']
    for frame in trace['frames']:
        if 'banner' not in frame or 'small_components' not in frame:raise ValueError('trace requires --banner --small')
        tiles=tile_draw(frame['tile_phase'],report['tile_scroll_kernel']['base_position'])['quads']
        strips=[]
        for group in report['first_components']['groups']:
            strip=group.get('scroll_strip');parts=[]
            if strip is not None:
                params=strip['parameters'];draw=clipped_strip(strip['uv_xywh'],params['orientation'],params['start'],params['end'],params['period'],frame['tick']%params['period'],strip['startup_origin'],depth=45)
                parts=[dict(texture_entry=group['texture_entry'],geometry=command_quad(c,report['composite_layout']['anchors'],report['strip_rotation_kernels'])) for c in draw['commands']]
            strips.append(parts)
        frames.append(dict(tick=frame['tick'],idle_characters=idle_characters[len(frames)]['characters'],characters=characters[len(frames)]['characters'],strips=strips,labels=[s['geometry'] for s in labels[len(frames)]['labels']],alpha=frame['shared']['overlay_alpha'],hidden=frame['shared']['overlay_hidden'],
            banner=frame['banner']['geometry'],small=[s['geometry'] for s in frame['small_components'] if s['geometry'] is not None],tiles=tiles))
        index=len(frames)-1
        frames[-1].update(emphasis_characters=shake_characters[index]['characters'] if index>=80 else None,
            emphasis_idle_characters=shake_idle_characters[index]['characters'] if index>=80 else None,
            emphasis_labels=[s['geometry'] for s in shake_labels[index]['labels']] if index>=80 else None)
    return dict(textures=assets,items=items,frames=frames,
        background=next(p for p in shared if p['label']=='background')['geometry'],
        tint=next(p for p in shared if p['label']=='conditional_overlay')['geometry'],
        provenance=dict(elf_sha256=report['elf_sha256'],pix_sha256=hashlib.sha256(pix).hexdigest(),
            texture_mapping='FPIX chunk order matched to resource-entry indices; visually checked atlas content.',
            limits='Diagnostic layer composition. Labels and character groups use recovered entry/exit; individual part idle offsets are zero. Activation, seed and exit are authored. Canvas blending/filtering are not PS2 GPU emulation.'))


def html_document(payload):
    template=Path(__file__).with_name('arika_menu_textured.html').read_text()
    return template.replace('/*PAYLOAD*/',json.dumps(payload,separators=(',',':')).replace('<','\\u003c'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pix');parser.add_argument('report');parser.add_argument('trace');parser.add_argument('output')
    args=parser.parse_args();paths=[Path(v).resolve() for v in (args.pix,args.report,args.trace,args.output)]
    if len(set(paths))!=4:parser.error('input/output paths must differ')
    if paths[3] in (Path(__file__).resolve(),Path(__file__).with_name('arika_menu_textured.html').resolve()):parser.error('output must differ from generator/template')
    try:payload=build_payload(json.loads(paths[1].read_text()),paths[0].read_bytes(),json.loads(paths[2].read_text()));document=html_document(payload)
    except (ValueError,KeyError,OSError) as error:parser.error(str(error))
    paths[3].write_text(document);print('Wrote textured menu viewer with %d embedded atlases'%len(payload['textures']))


# if __name__=='__main__':main()
