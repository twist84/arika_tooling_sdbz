"""Shared small-component entry curves, state transitions and geometry."""
import struct
from arika_menu_banner import sample_curve
from arika_menu_layout import f32
from arika_menu_plain import plain_sprite


def recover_small(elf,gp,layers):
    components=[]
    for item in layers['shared_small_components']:
        setup=[0x376f90,0x377110,0x377290,0x377410,0x377590,0x377710,0x377890][item['index']]
        registers=[0]*32;directions={}
        stop=False
        for word in elf.words(setup,16):
            op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;imm=word&65535;imm=imm-65536 if imm&32768 else imm
            if op==9:registers[rt]=registers[rs]+imm
            if op==0x28 and rs==4 and imm in (120,121):directions[imm]=registers[rt]
            if stop:break
            if op==3:stop=True
        if set(directions)!={120,121} or any(v not in (-1,0,1) for v in directions.values()):raise ValueError('unexpected small component direction setup')
        vtable=0x4f1a50+item['index']*64;callbacks=elf.words(vtable+8,12)
        if callbacks[2]!=0x376d10 or callbacks[6]!=0x376df0 or callbacks[8:10]!=[0x376ef0,0x376f00]:raise ValueError('unexpected small lifecycle callbacks')
        if elf.words(callbacks[7],2)!=[0x03e00008,0x0000102d]:raise ValueError('unexpected small active callback')
        if elf.words(callbacks[3],2)!=[0x03e00008,0]:raise ValueError('unexpected small active-start callback')
        for callback in callbacks[8:10]:
            if elf.words(callback,2)!=[0x03e00008,0x24020001]:raise ValueError('unexpected small completion callback')
        components.append(dict(index=item['index'],setup=setup,vtable=vtable,callbacks=callbacks,direction=[directions[120],directions[121]],
            base=list(item['base_position']),base_source=item['base_source'],base_address=item['base_address'],
            uv_xywh=item['evidence']['rectangles'][0]['xywh'],texture_entry=3,depth=5))
    functions={}
    for name,start,end in [('update',0x376ac0,0x376c20),('start',0x376c70,0x376c90),('stop',0x376c90,0x376cd0),
                           ('begin_entry',0x376d10,0x376dc0),('entry',0x376df0,0x376ee0),
                           ('empty_callbacks',0x376dc0,0x376df0),('completion_callbacks',0x376ee0,0x376f20)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    return dict(components=components,functions=functions,global_pointer=gp,
        approach=dict(times_address=gp-19776,values_address=gp-19768,times=list(struct.unpack('<2f',elf.read(gp-19776,8))),values=list(struct.unpack('<2f',elf.read(gp-19768,8)))),
        bounce=dict(times_address=0x4a9f00,values_address=0x4a9f40,times=list(struct.unpack('<13f',elf.read(0x4a9f00,52))),values=list(struct.unpack('<13f',elf.read(0x4a9f40,52)))),
        reset_position=list(struct.unpack('<2f',elf.read(gp-10720,8))),
        limits='Recovered small-component curves and lifecycle; host float32, no textures or final compositing.')


def initialize_small():return dict(phase=0,age=0.0,offset=[0.0,0.0])


def entry_offset(age,component,kernel):
    age=f32(age);value=sample_curve(kernel['approach'],age);delay=kernel['approach']['times'][-1]
    if age>=delay:value=f32(value+sample_curve(kernel['bounce'],f32(age-delay)))
    return [f32(value*v) for v in component['direction']]


def start_small(state,component,kernel):state.update(phase=1,age=0.0,offset=entry_offset(0,component,kernel))
def stop_small(state):state['phase']=4


def step_small(state,component,kernel):
    if state['phase']==0:return
    age=f32(state['age']+1);state['age']=f32(age-99999) if age>99999 else age
    if state['phase']==1:
        state['offset']=entry_offset(state['age'],component,kernel)
        if state['age']>=f32(kernel['approach']['times'][-1]+kernel['bounce']['times'][-1]):
            state.update(phase=2,offset=list(kernel['reset_position']))
    elif state['phase']==3:state['phase']=2
    elif state['phase']==4:state['phase']=0


def draw_small(state,component):
    if state['phase']==0:return None
    position=[f32(a+b) for a,b in zip(component['base'],state['offset'])]
    return dict(piece=component['index'],texture_entry=3,depth=component['depth'],**plain_sprite(component['uv_xywh'],position))
