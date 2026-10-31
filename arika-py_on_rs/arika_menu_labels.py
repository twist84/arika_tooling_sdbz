"""Selected-item label entry/exit with optional recovered common emphasis."""
import struct
from arika_menu_banner import sample_curve
from arika_menu_layout import f32


def recover_labels(elf,gp,layers):
    components=[]
    for item in layers['item_overlays']:
        callbacks=elf.words(item['vtable']+8,12);registers=[0]*32;direction={}
        for word in elf.words(callbacks[0],4):
            op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;imm=word&65535;imm=imm-65536 if imm&32768 else imm
            if op==9:registers[rt]=registers[rs]+imm
            if rs==4 and op in (0x28,0x29):
                for i in range(1 if op==0x28 else 2):direction[imm+i]=((registers[rt]>>(i*8)&255)+128)%256-128
        if set(direction)!={24,25}:raise ValueError('unexpected label direction setup')
        if callbacks[2]!=0x37e1c0 or callbacks[6]!=0x37e2d0 or callbacks[8]!=0x37e3d0:raise ValueError('unexpected label callbacks')
        active_start=elf.words(callbacks[3],2);active=elf.words(callbacks[7],2)
        if active_start!=[0x03e00008,0xac800008] or active!=[0x03e00008,0x0000102d]:raise ValueError('unexpected label active callbacks')
        components.append(dict(item=item['item'],vtable=item['vtable'],callbacks=callbacks,active_start_words=active_start,active_words=active,direction=[direction[24],direction[25]],base=item['base_position'],uv_xywh=item['uv_xywh']))
    functions={}
    for name,start,end in [('update',0x37df90,0x37e0d0),('start',0x37e120,0x37e140),('exit_start',0x37e140,0x37e160),
                           ('begin_entry',0x37e1c0,0x37e280),('begin_exit',0x37e290,0x37e2b0),('entry',0x37e2d0,0x37e3c0),('exit',0x37e3d0,0x37e460)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    def curve(values,times,n):return dict(values_address=values,times_address=times,values=list(struct.unpack('<'+'f'*n,elf.read(values,n*4))),times=list(struct.unpack('<'+'f'*n,elf.read(times,n*4))))
    return dict(components=components,functions=functions,global_pointer=gp,
        approach=curve(gp-19392,gp-19400,2),bounce=curve(0x4aa270,0x4aa230,13),exit=curve(gp-19360,gp-19368,2),
        reset_position=list(struct.unpack('<2f',elf.read(gp-10720,8))),
        limits='Entry/active/exit subset only. Common emphasis is provided by item_emphasis; outer selection scheduling and GPU compositing are not reproduced.')


def initialize_label():return dict(phase=0,age=0.0,offset=[0.0,0.0],depth=0.0)


def label_offset(age,component,kernel):
    value=sample_curve(kernel['approach'],age);delay=kernel['approach']['times'][-1]
    if age>=delay:value=f32(value+sample_curve(kernel['bounce'],f32(age-delay)))
    return [f32(value*d) for d in component['direction']]


def start_label(state,component,kernel):state.update(phase=1,age=0.0,offset=label_offset(0,component,kernel),depth=45.0)
def exit_label(state,kernel):state.update(phase=4,age=0.0,offset=list(kernel['reset_position']),depth=15.0)
def emphasize_label(state,kernel):state.update(phase=3,age=0.0,offset=list(kernel['reset_position']))


def step_label(state,component,kernel,emphasis_kernel=None):
    if state['phase']==3 and emphasis_kernel is None:raise ValueError('label emphasis requires the recovered emphasis kernel')
    if state['phase']==0:return
    age=f32(state['age']+1);state['age']=f32(age-99999) if age>99999 else age
    if state['phase']==1:
        state['offset']=label_offset(state['age'],component,kernel)
        if state['age']>=f32(kernel['approach']['times'][-1]+kernel['bounce']['times'][-1]):state.update(phase=2,age=0.0,offset=list(kernel['reset_position']))
    elif state['phase']==4:
        value=sample_curve(kernel['exit'],state['age']);state['offset']=[f32(value*d) for d in component['direction']]
        if state['age']>=kernel['exit']['times'][-1]:state['phase']=0
    elif state['phase']==3:
        from arika_menu_emphasis import emphasis_offset
        state['offset'],_=emphasis_offset(state['age'],component['direction'],emphasis_kernel)


def draw_label(state,component):
    if state['phase']==0:return None
    x,y=[f32(a+b) for a,b in zip(component['base'],state['offset'])];u,v,w,h=component['uv_xywh']
    return dict(position=[x,y],uv_endpoints=[u,v,u+w,v+h],vertices=[[f32(x-w/2),f32(y-h/2)],[f32(x+w/2),f32(y-h/2)],[f32(x-w/2),f32(y+h/2)],[f32(x+w/2),f32(y+h/2)]],depth=f32(state['depth']+25))


def trace_labels(report,steps=140,exit_tick=120,emphasis_tick=None):
    kernel=report['item_label_animation'];states=[initialize_label() for _ in range(7)];frames=[]
    for state,component in zip(states,kernel['components']):start_label(state,component,kernel)
    for tick in range(steps):
        for state,component in zip(states,kernel['components']):
            if tick==exit_tick:exit_label(state,kernel)
            elif tick==emphasis_tick:emphasize_label(state,kernel)
            elif tick>0:step_label(state,component,kernel,report['item_emphasis']['kernels']['labels'])
        frames.append(dict(tick=tick,labels=[dict(phase=s['phase'],age=s['age'],offset=list(s['offset']),depth=s['depth'],geometry=draw_label(s,c)) for s,c in zip(states,kernel['components'])]))
    result=dict(format='ARIKA_MENU_LABEL_TRACE',version=1,elf_sha256=report['elf_sha256'],frames=frames,
        limits=['Independent labels started before sample zero; exit requested at sample %d (authored schedule).'%exit_tick,
                'Emphasis is disabled unless requested; native selection scheduling is not reproduced. Other item layers remain static.'])
    if emphasis_tick is not None:
        result.update(version=2,emphasis_tick=emphasis_tick)
        result['limits'][1]='Recovered common emphasis is requested at an authored time; phase 3 persists until another request. Native selection scheduling remains pending.'
    return result
