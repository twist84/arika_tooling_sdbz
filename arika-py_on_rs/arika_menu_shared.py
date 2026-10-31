"""Shared-menu scheduler. Child animation updates are explicit caller callbacks."""
import struct
from arika_menu_layout import f32


def recover_shared(elf,gp):
    callbacks=elf.words(0x4f1c18,3)
    if callbacks!=[0x377fb0,0x3780e0,0x3780f0]:raise ValueError('unexpected shared callbacks')
    functions={}
    for name,start,end in [('update',0x377de0,0x377f40),('fade',0x377f40,0x377f94),
                           ('entry',0x377fb0,0x3780e0),('active',0x3780e0,0x3780e8),
                           ('exit',0x3780f0,0x378170),('request_exit',0x3782c0,0x3782d8)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    return dict(vtable=0x4f1c10,callbacks=callbacks,functions=functions,
        small_start_times=list(struct.unpack('<7f',elf.read(0x4a9f80,28))),
        entry_wait=struct.unpack('<f',elf.read(gp-19712,4))[0],
        overlay_target=struct.unpack('<f',elf.read(gp-19708,4))[0],overlay_rate=f32(.1),
        fields=dict(phase=208,subphase=212,age=216,started_count=220,overlay_hidden=224,overlay_alpha=172,small_pointers=228),
        limits='Shared scheduler only. Caller supplies banner/small animation updates; outer menu activation, textures and compositing remain unresolved.')


def initialize_shared():
    # Scheduler fields from 0x377A10; setup 0x377A70 zeros overlay alpha.
    return dict(phase=0,subphase=0,age=0.0,started_count=0,overlay_hidden=True,
        overlay_alpha=0.0,small_phases=[0]*7)


def request_exit(state):state.update(phase=3,subphase=0,age=0.0)


def step_shared(state,kernel,child):
    """child(role,index) handles child updates/starts; it may mutate small_phases.

    Initialization/activation of the outer shared object is caller-controlled.
    """
    calls=[]
    def call(role,index=None):calls.append(dict(role=role,index=index));child(role,index)
    if state['phase']==0:return calls
    call('update_banner');call('update_owner')
    for index in range(7):call('update_small',index)
    alpha=state['overlay_alpha'];target=kernel['overlay_target']
    if not state['overlay_hidden'] and alpha<target:
        state['overlay_alpha']=min(target,f32(alpha+f32(kernel['overlay_rate']*target)))
    age=f32(state['age']+1);state['age']=f32(age-99999) if age>99999 else age
    complete=False
    if state['phase']==1:
        if state['subphase']==0:
            call('start_banner');call('start_owner');state['subphase']=1
        elif state['subphase']==1:
            for index,threshold in enumerate(kernel['small_start_times']):
                if state['small_phases'][index]==0 and state['age']>=threshold:
                    state['small_phases'][index]=1;call('start_small',index);state['started_count']+=1
            if state['started_count']>=7:state.update(subphase=2,age=0.0)
        elif state['subphase']==2 and state['age']>=kernel['entry_wait']:
            state.update(overlay_hidden=False,overlay_alpha=0.0);complete=True
        if complete:state.update(phase=2,subphase=0,age=0.0)
    elif state['phase']==3:
        if state['subphase']==0:call('exit_banner');state['subphase']=1
        elif state['subphase']==1 and state['age']>=10:state.update(phase=0,subphase=0,age=0.0)
    return calls
