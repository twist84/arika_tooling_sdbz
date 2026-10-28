"""Recovered single-sprite setup calls and shared menu draw structure."""
import struct


def setup_calls(elf,address,max_instructions=256,stop_before_branch=False,gp=None):
    """Bounded constant propagation for the researched straight-line setup routines.

    Calls are not emulated. Caller-saved registers become unknown after each call.
    Direct local jumps are followed. Conditional branches and unsupported instructions fail.
    """
    from arika_menus import signed16
    registers=[None]*32;registers[0]=0;registers[28]=gp
    floats=[None]*32
    last_slot=None;resources=[];rectangles=[];effects=[]

    def step(word):
        nonlocal last_slot
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;fn=word&63
        if word==0:pass
        elif op==15:registers[rt]=(word&65535)<<16
        elif op in (9,25):registers[rt]=None if registers[rs] is None else (registers[rs]+signed16(word))&0xffffffff
        elif op==13:registers[rt]=None if registers[rs] is None else registers[rs]|(word&65535)
        elif op in (10,11):registers[rt]=None # comparison result is not needed for literal setup arguments
        elif op==0 and fn in (0x21,0x2d,0x25):
            a,b=registers[rs],registers[rt]
            registers[rd]=None if a is None or b is None else ((a|b) if fn==0x25 else (a+b)&0xffffffff)
        elif op in (0x23,0x37,0x1e):
            if rt==25:last_slot=word&65535
            registers[rt]=None
        elif op in (0x28,0x29,0x2b,0x3f,0x1f):pass # stores do not change GPRs
        elif op==17 and rs==4:
            floats[rd]=None if registers[rt] is None else struct.unpack('<f',struct.pack('<I',registers[rt]))[0]
        elif op==0x31:
            at=None if registers[rs] is None else registers[rs]+signed16(word)
            floats[rt]=None if at is None else struct.unpack('<f',elf.read(at,4))[0]
        elif op==0x39:pass # SWC1 does not change registers
        else:raise ValueError('unsupported sprite setup instruction: 0x%08X'%word)
        registers[0]=0

    pc=address;visited=set()
    while pc<address+max_instructions*4:
        if pc in visited:raise ValueError('sprite setup contains a loop')
        visited.add(pc)
        word=elf.words(pc,1)[0];op=word>>26
        if stop_before_branch and op in (1,4,5,6,7,20,21,22,23):
            return dict(setup=address,resources=resources,rectangles=rectangles,
                strip_effects=effects,tail_target=None,stopped_before_branch=pc)
        is_return=word==0x03e00008
        is_tail=op==2
        is_call=op==3 or (op==0 and word&63==9)
        if is_call and op==0 and (word>>21)&31!=25:raise ValueError('unsupported indirect setup target')
        if is_return or is_tail or is_call:
            target=(word&0x3ffffff)<<2 if op in (2,3) else None
            step(elf.words(pc+4,1)[0])
            if is_call:
                if target==0x3725e0:
                    if registers[5] is None:raise ValueError('unknown resource index')
                    resources.append(dict(instruction=pc,entry=registers[5]))
                if target is None and last_slot==20:
                    rect=registers[5:9]
                    if any(v is None for v in rect):raise ValueError('unknown sprite rectangle')
                    rectangles.append(dict(instruction=pc,xywh=[signed16(v) for v in rect]))
                if target==0x373ff0:
                    if registers[7] is None or any(v is None for v in floats[12:15]):raise ValueError('unknown strip effect parameters')
                    effects.append(dict(instruction=pc,orientation=registers[7],start=floats[12],end=floats[13],period=floats[14]))
                for reg in list(range(1,16))+[24,25,31]:registers[reg]=None
                for reg in range(20):floats[reg]=None
                last_slot=None;pc+=8;continue
            if is_tail and address<=target<address+max_instructions*4:
                pc=target;continue
            return dict(setup=address,resources=resources,rectangles=rectangles,
                strip_effects=effects,tail_target=target if is_tail else None)
        step(word);pc+=4
    raise ValueError('sprite setup exceeds instruction bound')


def recover_layers(elf,gp):
    titles=[]
    # item, component vtable, setup, draw, GP position offset
    specs=[(0,0x4f2050,0x37e960,0x37e8c0,-19336),
           (1,0x4f20d0,0x37ec80,0x37ebe0,-19320),
           (2,0x4f2150,0x37efa0,0x37ef00,-19304),
           (3,0x4f2090,0x37eaf0,0x37ea50,-19328),
           (4,0x4f2110,0x37ee10,0x37ed70,-19312),
           (5,0x4f1fd0,0x37e640,0x37e5a0,-19352),
           (6,0x4f2010,0x37e7d0,0x37e730,-19344)]
    for item,vtable,setup,draw,offset in specs:
        if elf.words(vtable+48,1)[0]!=draw:raise ValueError('overlay draw vtable mismatch')
        calls=setup_calls(elf,setup)
        if len(calls['rectangles'])!=1 or [r['entry'] for r in calls['resources']]!=[2]:raise ValueError('unexpected item overlay setup')
        titles.append(dict(item=item,vtable=vtable,draw=draw,base_address=gp+offset,
            base_position=list(struct.unpack('<2f',elf.read(gp+offset,8))),depth_bias=25,
            anchor_mode=0,texture_entry=2,uv_xywh=calls['rectangles'][0]['xywh'],evidence=calls))
    shared=[]
    for setup,role in [(0x377a70,'background_and_conditional_overlay'),(0x3783c0,'shared_banner'),(0x375fe0,'tiled_element')]:
        shared.append(dict(role=role,evidence=setup_calls(elf,setup)))
    small=[]
    for index,(setup,draw,offset) in enumerate([(0x376f90,0x377050,-19760),(0x377110,0x3771d0,-19752),
        (0x377290,0x377350,-5920),(0x377410,0x3774d0,-19744),(0x377590,0x377650,-19736),
        (0x377710,0x3777d0,-19728),(0x377890,0x377950,-19720)]):
        calls=setup_calls(elf,setup)
        if len(calls['rectangles'])!=1 or [r['entry'] for r in calls['resources']]!=[3]:raise ValueError('unexpected shared small component setup')
        try:position=list(struct.unpack('<2f',elf.read(gp+offset,8)))
        except ValueError:position=None
        source=getattr(elf,'source_kind',lambda address,size:'file_backed')(gp+offset,8) if position is not None else 'runtime_memory_unresolved'
        small.append(dict(index=index,draw=draw,base_address=gp+offset,
            base_position=position,base_source=source,evidence=calls))
    return dict(version=1,item_overlays=titles,shared_setups=shared,shared_small_components=small,
        shared_draw=dict(function=0x378170,call_order=['background sprite','shared banner','tiled element (two draws)',
            'seven small components (state-gated)','overlay if shared byte +224 is zero']),
        main_draw=dict(function=0x379e60,call_order=['shared draw','previous item if index >= 0',
            'current item if index >= 0','embedded component at menu +64']),
        limits=['Call order is not the final depth/compositing order.',
                'Shared plain sprites use a different draw helper; their screen quads are not exported here.',
                'First item component group and native animation curves remain incomplete.'])
