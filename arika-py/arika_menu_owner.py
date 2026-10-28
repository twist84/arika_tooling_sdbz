"""Verified tile/companion owner lifecycle; outer menu scheduling is not simulated."""
import struct
from arika_menu_layout import f32
from arika_menu_companions import empty_slot,update_slot,advance_event


def recover_owner(elf,gp):
    vtable=0x4f19f0
    callbacks=elf.words(vtable+8,3)
    if callbacks!=[0x3761a0,0x3761b0,0x376280]:raise ValueError('unexpected tile owner callbacks')
    for address in (callbacks[0],callbacks[2]):
        if elf.words(address,2)!=[0x03e00008,0x24020001]:raise ValueError('unexpected owner completion callback')
    functions={}
    for name,start,end in [('initialize',0x375f90,0x375fe0),('update',0x376080,0x376198),
                           ('entry',0x3761a0,0x3761a8),('active',0x3761b0,0x376280),
                           ('exit',0x376280,0x376288),('start',0x376390,0x3763a4)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    return dict(vtable=vtable,callbacks=callbacks,functions=functions,
        fields=dict(owner_phase=112,owner_age=116,tile_phase=120,offset_x=124,offset_y=128,event_timer=132),
        initial_offset=list(struct.unpack('<2f',elf.read(gp-10720,8))),
        phase_names=['inactive','entry','active','exit'],age_wrap=99999,
        limits='Inner tile/companion owner only. Outer menu activation/exit, wall-clock timing and draw visibility are not inferred.')


def initialize_owner(kernel,owner_kernel):
    return dict(slots=[empty_slot(kernel['reset_position_initial']) for _ in range(kernel['slot_count'])],
        reset_position=list(kernel['reset_position_initial']),offset=list(owner_kernel['initial_offset']),
        owner_phase=0,owner_age=0.0,timer=0.0,phase=0.0)


def start_owner(state):
    # Native start does not reset slots, offsets or the event timer.
    state.update(owner_phase=1,owner_age=0.0,phase=0.0)


def step_owner(state,templates,draw_random):
    before=state['owner_phase']
    event=dict(attempted=False,spawned=None,owner_before=before,owner_after=before,
        slots_updated=False,callback=None)
    if before==0:return event
    age=f32(state['owner_age']+1)
    state['owner_age']=f32(age-99999) if age>99999 else age
    state['slots']=[update_slot(slot,state.get('reset_position')) for slot in state['slots']]
    event['slots_updated']=True
    if before==1:
        event['callback']='entry';state.update(owner_phase=2,owner_age=0.0)
    elif before==2:
        event['callback']='active';event.update(advance_event(state,templates,draw_random))
    elif before==3:
        event['callback']='exit';state.update(owner_phase=0,owner_age=0.0)
    event['owner_after']=state['owner_phase']
    return event
