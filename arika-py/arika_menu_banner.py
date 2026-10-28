"""Native shared-banner entry/exit curves and owner state transitions."""
import math
import struct
from arika_menu_layout import f32
from arika_menu_plain import plain_sprite


def recover_banner(elf,gp):
    initial_words=elf.words(0x3783c0,6)
    if initial_words!=[0x3c02c400,0xac800070,0xac800074,0xac820078,0x080de0f8,0xac80007c]:raise ValueError('unexpected banner initial state')
    callbacks=elf.words(0x4f1c38,3)
    if callbacks!=[0x378590,0x378610,0x378620]:raise ValueError('unexpected banner callbacks')
    curves={}
    for name,values,times,count in [('entry',gp-19696,gp-19688,gp-19680),('exit',gp-19672,gp-19664,gp-19656)]:
        n=struct.unpack('<b',elf.read(count,1))[0]
        if n!=2:raise ValueError('unexpected banner curve length')
        curves[name]=dict(values_address=values,times_address=times,count_address=count,
            values=list(struct.unpack('<2f',elf.read(values,8))),times=list(struct.unpack('<2f',elf.read(times,8))))
    functions={}
    for name,start,end in [('interpolate',0x2c2c10,0x2c2cf0),('update',0x378480,0x378590),
                           ('entry',0x378590,0x378610),('active',0x378610,0x378618),
                           ('exit',0x378620,0x3786a0),('start',0x3786f0,0x378700),('request_exit',0x378700,0x378710)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    return dict(vtable=0x4f1c30,callbacks=callbacks,functions=functions,curves=curves,initialize_address=0x3783c0,initialize_words=initial_words,
        global_pointer=gp,base=list(struct.unpack('<2f',elf.read(gp-19704,8))),initial_offset=[-512.0,0.0],
        texture_entry=2,uv_xywh=[0,256,264,48],depth=99,
        limits='Banner geometry and host-float32 curves only; textures, outer activation and final compositing are not reproduced.')


def sample_curve(curve,time):
    times=[f32(v) for v in curve['times']];values=[f32(v) for v in curve['values']];time=f32(time)
    if len(times)!=len(values) or len(times)<2 or not all(math.isfinite(v) for v in times+values+[time]):raise ValueError('finite curve samples required')
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('strictly increasing curve times required')
    if time<times[0]:return values[0]
    for i in range(len(times)-1):
        if time<times[i+1]:
            fraction=f32(f32(time-times[i])/f32(times[i+1]-times[i]))
            return f32(values[i]+f32(fraction*f32(values[i+1]-values[i])))
    return values[-1]


def initialize_banner(kernel):return dict(phase=0,age=0.0,offset=list(kernel['initial_offset']))
def start_banner(state):state.update(phase=1,age=0.0)
def exit_banner(state):state.update(phase=3,age=0.0)


def step_banner(state,kernel):
    if state['phase']==0:return
    age=f32(state['age']+1);state['age']=f32(age-99999) if age>99999 else age
    if state['phase'] in (1,3):
        curve=kernel['curves']['entry' if state['phase']==1 else 'exit']
        state['offset'][0]=sample_curve(curve,state['age'])
        if state['age']>=curve['times'][-1]:
            state['phase']=2 if state['phase']==1 else 0;state['age']=0.0


def draw_banner(state,kernel):
    position=[f32(a+b) for a,b in zip(kernel['base'],state['offset'])]
    return dict(texture_entry=kernel['texture_entry'],depth=kernel['depth'],**plain_sprite(kernel['uv_xywh'],position))
