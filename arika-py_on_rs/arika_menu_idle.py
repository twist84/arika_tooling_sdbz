"""Per-part idle for all seven items, with explicit host trigonometry for circular motion."""
import struct
import math
from arika_menu_banner import sample_curve
from arika_menu_layout import f32


def recover_idle(elf,gp):
    result=[]
    for item,start,end,values,times,count,offset,weights in [
        (0,0x37ffe0,0x380100,0x4aa4f8,0x4aa508,gp-19176,1040,[[0,2],[0,3],[0,3],[0,3],[0,1],[0,2],[0,2]]),
        (1,0x3809a0,0x380ac0,0x4aa680,0x4aa690,gp-19120,608,[[0,2],[0,1],[0,3],[0,3]]),
        (2,0x381210,0x381380,0x4aa818,0x4aa828,gp-19088,1328,[[f32(-.3),.75],[0,.5],[0,.75],[0,.5],[.25,.5],[0,.5],[f32(-.2),.5],[0,.5],[0,.5]]),
        (4,0x380d50,0x380ec0,0x4aa718,0x4aa728,gp-19104,752,[[0,2],[0,1.5],[0,1],[-.5,2],[.5,2]])]:
        if elf.read(count,1)!=b'\x03':raise ValueError('unexpected idle curve sample count')
        jump_address={0:0x4cc920,2:0x4cc9a0}.get(item)
        result.append(dict(item=item,address=start,words=elf.words(start,(end-start)//4),count_address=count,part_offset=offset,weights=weights,
            jump_table_address=jump_address,jump_table=elf.words(jump_address,len(weights)) if jump_address is not None else [],
            curve=dict(values_address=values,times_address=times,values=list(struct.unpack('<3f',elf.read(values,12))),times=list(struct.unpack('<3f',elf.read(times,12))))))
    def curve(values,times,n):return dict(values_address=values,times_address=times,values=list(struct.unpack('<'+'f'*n,elf.read(values,n*4))),times=list(struct.unpack('<'+'f'*n,elf.read(times,n*4))))
    if elf.read(gp-19240,1)!=b'\x03' or elf.read(gp-19236,1)!=b'\x06':raise ValueError('unexpected CUSTOMIZE idle sample counts')
    result.append(dict(item=5,kind='coupled',address=0x37f7f0,words=elf.words(0x37f7f0,(0x37f9a0-0x37f7f0)//4),
        count_address=gp-19240,secondary_count_address=gp-19236,part_offset=464,secondary_age_offset=488,
        curve=curve(0x4aa3b8,0x4aa3c8,3),secondary_curve=curve(0x4aa3e0,0x4aa400,6),
        secondary_y_factor=struct.unpack('<f',elf.read(gp-19232,4))[0]))
    if elf.read(gp-19192,1)!=b'\x02':raise ValueError('unexpected OPTIONS angle sample count')
    result.append(dict(item=6,kind='circular',address=0x37fc00,words=elf.words(0x37fc00,(0x37fd30-0x37fc00)//4),
        count_address=gp-19192,part_offset=320,part_count=2,radius_address=gp-19216,radius=struct.unpack('<f',elf.read(gp-19216,4))[0],
        curve=curve(gp-19208,gp-19200,2),cosine_address=0x1859d8,sine_address=0x185c78,
        trig_model='Host math.cos/math.sin rounded to float32; native libm last-bit equivalence is not established.'))
    if elf.read(gp-19136,1)!=b'\x02' or elf.read(gp-19132,1)!=b'\x05':raise ValueError('unexpected DRAGON SUMMONING idle sample counts')
    result.append(dict(item=3,kind='combined_circular',address=0x380450,words=elf.words(0x380450,(0x380690-0x380450)//4),
        count_address=gp-19136,sway_count_address=gp-19132,part_offset=1184,part_count=8,
        radius_addresses=[gp-19160,gp-19156],radii=list(struct.unpack('<2f',elf.read(gp-19160,8))),
        curve=curve(gp-19152,gp-19144,2),sway_curve=curve(0x4aa5e0,0x4aa600,5),
        jump_table_address=0x4cc960,jump_table=elf.words(0x4cc960,8),
        rules=['minus_y','large','small_reflected','plus_y','plus_xy','minus_y','minus_y','plus_xy'],
        cosine_address=0x1859d8,sine_address=0x185c78,
        trig_model='Host math.cos/math.sin rounded to float32; native libm last-bit equivalence is not established.'))
    return dict(components=result,global_pointer=gp,limits='Idle motion covers all seven items. OPTIONS and DRAGON SUMMONING use host trigonometry. Emphasis remains pending; CUSTOMIZE secondary clock initialization is caller-supplied.')


def step_idle(age,component):
    age=f32(f32(age)+1);period=component['curve']['times'][-1]
    if age>=period:age=f32(age-period)
    value=sample_curve(component['curve'],age)
    return age,[[f32(value*x) if x else 0.0,f32(value*y) if y else 0.0] for x,y in component['weights']]


def step_coupled_idle(age,secondary_age,component):
    def advance(previous,curve):
        value=f32(f32(previous)+1);period=curve['times'][-1]
        return f32(value-period) if value>=period else value
    age=advance(age,component['curve']);secondary_age=advance(secondary_age,component['secondary_curve'])
    base=sample_curve(component['curve'],age);sway=sample_curve(component['secondary_curve'],secondary_age)
    y=f32(sway*component['secondary_y_factor'])
    return age,secondary_age,[[base,base],[f32(base+sway),f32(base+y)],[f32(base-sway),f32(base-y)]]


def step_circular_idle(age,component,cosine=None,sine=None):
    age=f32(f32(age)+1);period=component['curve']['times'][-1]
    if age>=period:age=f32(age-period)
    angle=sample_curve(component['curve'],age);radius=component['radius']
    c=f32(math.cos(angle) if cosine is None else cosine(angle));s=f32(math.sin(angle) if sine is None else sine(angle))
    offset=[f32(radius-f32(radius*c)),f32(radius*s)]
    return age,[list(offset) for _ in range(component['part_count'])]


def step_dragon_idle(age,component,cosine=None,sine=None):
    age=f32(f32(age)+1);period=component['curve']['times'][-1]
    if age>=period:age=f32(age-period)
    angle=sample_curve(component['curve'],age);circles=[]
    for radius in component['radii']:
        c=f32(math.cos(angle) if cosine is None else cosine(angle));s=f32(math.sin(angle) if sine is None else sine(angle))
        circles.append([f32(radius-f32(radius*c)),f32(radius*s)])
    (x,y),(small_x,small_y)=circles;sway=sample_curve(component['sway_curve'],age)
    offsets=[]
    for rule in component['rules']:
        if rule=='large':offset=[x,y]
        elif rule=='small_reflected':offset=[small_x,f32(-small_y)]
        elif rule=='minus_y':offset=[x,f32(y-sway)]
        elif rule=='plus_y':offset=[x,f32(y+sway)]
        elif rule=='plus_xy':offset=[f32(x+sway),f32(y+sway)]
        else:raise ValueError('unknown dragon idle rule')
        offsets.append(offset)
    return age,offsets
