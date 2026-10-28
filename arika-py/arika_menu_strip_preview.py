#!/usr/bin/env python3
"""Convert researched strip traces to rotated quads and animated diagnostic SVG."""
import argparse
import json
import math
from pathlib import Path
import struct
from arika_menu_layout import f32
from arika_menu_plain import s16

HALF_PI=f32(math.pi/2)


def recover_rotation_kernels(elf):
    def vector_words(start,end):
        return [dict(address=a,word=elf.words(a,1)[0]) for a in range(start,end,4)
                if elf.words(a,1)[0]>>26==18 and (elf.words(a,1)[0]>>21)&31>=16]
    return dict(builder=0x1074e0,polynomial_address=0x439520,
        polynomial=list(struct.unpack('<4f',elf.read(0x439520,16))),
        trig_words=vector_words(0x1075dc,0x107634),matrix_words=vector_words(0x107658,0x10769c),
        limits='Only strip command rotations 0 and float32 pi/2 are supported. Host float32 VU approximation, not hardware emulation.')


def strip_basis(rotation,coefficients):
    rotation=f32(rotation)
    if rotation not in (0,HALF_PI):raise ValueError('only recovered strip rotations 0 and float32 pi/2 are supported')
    angle=f32(-rotation);negative=angle<0
    t=f32(angle+HALF_PI) if negative else f32(HALF_PI-angle)
    c=[f32(v*t) for v in coefficients]
    t2=f32(t*t);t4=f32(t2*t2);t6=f32(t2*t4);t8=f32(t4*t4)
    accumulator=t
    for power,coefficient in [(t2,c[3]),(t4,c[2]),(t6,c[1])]:accumulator=f32(accumulator+f32(power*coefficient))
    b=f32(accumulator+f32(t8*c[0]))
    a=f32(math.sqrt(max(0,f32(1-f32(b*b)))))
    if negative:a=f32(-a)
    return dict(x_axis=[b,a],y_axis=[f32(0-a),b])


def command_quad(command,anchors,kernel):
    uv=[s16(v) for v in command['uv_xywh']]
    if len(uv)!=4 or len(command['position'])!=2:raise ValueError('invalid strip command dimensions')
    if command['piece'] not in (0,1):raise ValueError('unsupported strip piece')
    endpoints=[uv[0],uv[1],s16(uv[0]+uv[2]),s16(uv[1]+uv[3])]
    width=abs(endpoints[2]-endpoints[0]);height=abs(endpoints[3]-endpoints[1])
    mode=command['anchor_mode']
    if not isinstance(mode,int) or not 0<=mode<len(anchors):raise ValueError('unsupported anchor mode')
    basis=strip_basis(command['rotation'],kernel['polynomial'])
    px,py=[f32(v) for v in command['position']];vertices=[]
    if not all(math.isfinite(v) for v in [px,py,command['depth']]):raise ValueError('non-finite strip command')
    for a,b in anchors[mode]['vertices']:
        x=f32(width*a);y=f32(height*b)
        rx=f32(f32(x*basis['x_axis'][0])+f32(y*basis['y_axis'][0]))
        ry=f32(f32(x*basis['x_axis'][1])+f32(y*basis['y_axis'][1]))
        vertices.append([f32(px+rx),f32(py+ry)])
    return dict(piece=command['piece'],vertices=vertices,uv_endpoints=endpoints,
        depth=command['depth'],basis=basis,
        bounds=[min(v[0] for v in vertices),min(v[1] for v in vertices),max(v[0] for v in vertices),max(v[1] for v in vertices)])


def quad_trace(trace,report):
    if trace.get('format')!='ARIKA_MENU_STRIP_TRACE' or trace.get('version')!=1:raise ValueError('unsupported strip trace')
    if trace.get('elf_sha256')!=report['elf_sha256']:raise ValueError('trace ELF hash does not match the supported ELF')
    if not trace.get('frames'):raise ValueError('trace has no samples')
    frames=[];previous=-1
    for frame in trace['frames']:
        tick=frame['tick']
        if not isinstance(tick,int) or tick<=previous:raise ValueError('trace ticks must be strictly increasing nonnegative integers')
        if not isinstance(frame['phase'],(int,float)) or not math.isfinite(frame['phase']):raise ValueError('non-finite trace phase')
        previous=tick
        frames.append(dict(tick=tick,phase=frame['phase'],quads=[command_quad(c,report['composite_layout']['anchors'],report['strip_rotation_kernels']) for c in frame['commands']]))
    return dict(format='ARIKA_MENU_STRIP_QUADS',version=1,elf_sha256=report['elf_sha256'],item=trace['item'],
        origin=trace['origin'],origin_source=trace['origin_source'],frames=frames,
        limits=['Only recovered 0/pi/2 strip rotations; host float32 approximation, not PS2 VU hardware accuracy.',
                'Geometry only: texture sampling, alpha, clipping, scene depth ordering and menu state are not rendered.'])


def animated_svg(trace,stride=15,ticks_per_second=60):
    if stride<1 or not math.isfinite(ticks_per_second) or ticks_per_second<=0:raise ValueError('positive sampling stride and diagnostic display rate required')
    all_frames=trace['frames'];frames=all_frames[::stride]
    if frames[-1]['tick']!=all_frames[-1]['tick']:frames.append(all_frames[-1])
    start=all_frames[0]['tick'];span=all_frames[-1]['tick']-start+1
    times=[(f['tick']-start)/span for f in frames]+[1]
    frames=frames+[frames[-1]]
    keys=';'.join('%0.9g'%t for t in times);duration=span/ticks_per_second
    kind=trace.get('preview_kind')
    title='Shared small components · recovered motion, geometry only' if kind=='small' else 'Shared banner · recovered motion, geometry only' if kind=='banner' else 'Shared companions · isolated geometry' if kind=='companions' else 'Shared tiled element · isolated geometry' if kind=='tile' else 'Item %d · isolated strip geometry'%trace['item']
    result=['<svg xmlns="http://www.w3.org/2000/svg" width="1088" height="1040" viewBox="-16 -56 544 520">',
        '<rect x="-16" y="-56" width="544" height="520" fill="#151922"/>',
        '<text x="0" y="-35" fill="#e4eaf3" font-family="sans-serif" font-size="13">%s</text>'%title,
        '<text x="0" y="-16" fill="#b8c5d9" font-family="sans-serif" font-size="8">Display: %g ticks/s (authored); sample stride %d. No textures or native frame timing.</text>'%(ticks_per_second,stride),
        '<rect x="0" y="0" width="512" height="448" fill="#202633" stroke="#56657c"/>']
    for y in range(32,448,32):result.append('<path d="M0 %dH512" stroke="#2b3444" stroke-width="0.5"/>'%y)
    for x in range(32,512,32):result.append('<path d="M%d 0V448" stroke="#2b3444" stroke-width="0.5"/>'%x)
    colors=['#5bd8ff','#ffb454','#c6a0ff','#7de3a5','#ff829a','#e6da66','#74c6ba','#ed9bde','#9eb6ff','#e4eaf3']
    pieces=list(enumerate(colors[:7])) if kind=='small' else list(enumerate(colors)) if kind=='companions' else list(enumerate(colors[:1 if kind=='banner' else 2]))
    for piece,color in pieces:
        points=[];visibility=[]
        for frame in frames:
            matches=[q for q in frame['quads'] if q['piece']==piece]
            if len(matches)>1:raise ValueError('duplicate strip piece')
            if matches:
                vertices=matches[0]['vertices'];points.append(' '.join('%g,%g'%tuple(vertices[i]) for i in [0,1,3,2]));visibility.append('visible')
            else:points.append('0,0 0,0 0,0 0,0');visibility.append('hidden')
        result.append('<polygon points="%s" visibility="%s" fill="%s" fill-opacity="0.2" stroke="%s" stroke-width="1">'%(points[0],visibility[0],color,color))
        for attribute,values in [('points',points),('visibility',visibility)]:
            result.append('<animate attributeName="%s" values="%s" keyTimes="%s" dur="%gs" calcMode="discrete" repeatCount="indefinite"/>'%(attribute,';'.join(values),keys,duration))
        result.append('</polygon>')
    legend='Colors identify the seven components.' if kind=='small' else 'Cyan: shared banner.' if kind=='banner' else 'Colors identify the ten slots.' if kind=='companions' else 'Cyan: piece 0. Orange: piece 1.'
    result.append('<text x="0" y="459" fill="#b8c5d9" font-family="sans-serif" font-size="8">%s Open SVG in a browser to animate; static viewers show the first sample.</text></svg>'%legend)
    return '\n'.join(result)+'\n'


def main():
    from arika_menus import analyze_menu
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf');parser.add_argument('trace');parser.add_argument('svg')
    parser.add_argument('--json',dest='json_output');parser.add_argument('--stride',type=int,default=15)
    parser.add_argument('--ticks-per-second',type=float,default=60)
    args=parser.parse_args();paths=[Path(p).resolve() for p in [args.elf,args.trace,args.svg]+([args.json_output] if args.json_output else [])]
    if len(set(paths))!=len(paths):parser.error('all input/output paths must differ')
    try:
        report=analyze_menu(Path(args.elf).read_bytes());trace=quad_trace(json.loads(Path(args.trace).read_text()),report)
        svg=animated_svg(trace,args.stride,args.ticks_per_second)
    except (ValueError,OSError,OverflowError,KeyError,TypeError) as error:parser.error(str(error))
    Path(args.svg).write_text(svg,encoding='utf-8')
    if args.json_output:Path(args.json_output).write_text(json.dumps(trace,indent=2,allow_nan=False)+'\n')
    print('Wrote rotated strip geometry and animated diagnostic SVG')


if __name__=='__main__':main()
