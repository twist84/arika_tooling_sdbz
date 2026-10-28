"""Common selected-character entry/exit with an optional verified per-part idle subset."""
import struct
from arika_menu_banner import sample_curve
from arika_menu_layout import f32,pose_part


def recover_characters(elf,gp,layout):
    components=[]
    for c in layout['composites']:
        callbacks=elf.words(c['vtable']+8,12);direction={};registers=[0]*32
        for word in elf.words(callbacks[0],12):
            op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;imm=word&65535;imm=imm-65536 if imm&32768 else imm
            if op==9:registers[rt]=registers[rs]+imm
            if op==0x28 and rs==4 and imm in (24,25):direction[imm]=registers[rt]
        if set(direction)!={24,25}:raise ValueError('unexpected character directions')
        if callbacks[6]!=0x37f350 or callbacks[8]!=0x37f3f0:raise ValueError('unexpected character entry/exit callbacks')
        components.append(dict(item=c['item'],direction=[direction[24],direction[25]],callbacks=callbacks))
    functions={}
    for name,start,end in [('entry',0x37f500,0x37f5f0),('exit',0x37f6d0,0x37f760)]:
        functions[name]=dict(address=start,words=elf.words(start,(end-start)//4))
    def curve(values,times,n):return dict(values_address=values,times_address=times,values=list(struct.unpack('<'+'f'*n,elf.read(values,n*4))),times=list(struct.unpack('<'+'f'*n,elf.read(times,n*4))))
    return dict(components=components,functions=functions,global_pointer=gp,
        approach=curve(gp-19288,gp-19296,2),bounce=curve(0x4aa310,0x4aa2d0,13),exit=curve(gp-19256,gp-19264,2),
        limits='Common whole-character entry/exit only. Per-part idle and common emphasis are provided by separate recovered modules; native selection scheduling is not reproduced.')


def character_offset(age,component,kernel,exiting=False):
    if exiting:value=sample_curve(kernel['exit'],age)
    else:
        value=sample_curve(kernel['approach'],age);delay=kernel['approach']['times'][-1]
        if age>=delay:value=f32(value+sample_curve(kernel['bounce'],f32(age-delay)))
    return [f32(value*d) for d in component['direction']]


def trace_characters(report,steps=140,exit_tick=120,idle=False,emphasis_tick=None):
    kernel=report['item_character_animation'];frames=[]
    from arika_menu_idle import step_idle,step_coupled_idle,step_circular_idle,step_dragon_idle
    idle_components={c['item']:c for c in report['character_idle']['components']} if idle else {}
    idle_ages=[0.0]*7;part_offsets=[[[0,0] for _ in c['parts']] for c in report['composite_layout']['composites']]
    secondary_ages=[0.0]*7 # Authored initial clock; native CUSTOMIZE initialization is not established.
    from arika_menu_emphasis import emphasis_offset
    for tick in range(steps):
        parts=[]
        for component,composite in zip(kernel['components'],report['composite_layout']['composites']):
            item=component['item']
            if item in idle_components and 22<tick<exit_tick and (emphasis_tick is None or tick<emphasis_tick):
                if idle_components[item].get('kind')=='coupled':idle_ages[item],secondary_ages[item],part_offsets[item]=step_coupled_idle(idle_ages[item],secondary_ages[item],idle_components[item])
                elif idle_components[item].get('kind')=='circular':idle_ages[item],part_offsets[item]=step_circular_idle(idle_ages[item],idle_components[item])
                elif idle_components[item].get('kind')=='combined_circular':idle_ages[item],part_offsets[item]=step_dragon_idle(idle_ages[item],idle_components[item])
                else:idle_ages[item],part_offsets[item]=step_idle(idle_ages[item],idle_components[item])
            exiting=tick>=exit_tick;age=tick-exit_tick if exiting else tick
            if exiting and age>=kernel['exit']['times'][-1]:parts.append([]);continue
            offset=character_offset(age,component,kernel,exiting)
            if not exiting and age>=kernel['approach']['times'][-1]+kernel['bounce']['times'][-1]:offset=[0,0]
            if not exiting and emphasis_tick is not None and tick>=emphasis_tick:offset,_=emphasis_offset(tick-emphasis_tick,component['direction'],report['item_emphasis']['kernels']['characters'])
            depth=15 if exiting else 45
            part_geometries=[]
            for i,p in enumerate(composite['parts']):
                component_offset=offset
                if item==2 and i>=4:component_offset=[-v for v in offset]
                part_geometries.append(dict(texture_entry=p['texture_entry'],geometry=dict(pose_part(composite,p,report['composite_layout']['anchors'],component_offset=component_offset,part_offset=part_offsets[item][i],component_depth=depth),depth=f32(depth+15+p['placement'][2]))))
            parts.append(part_geometries)
        frames.append(dict(tick=tick,characters=parts))
    result=dict(format='ARIKA_MENU_CHARACTER_TRACE',version=1,elf_sha256=report['elf_sha256'],frames=frames,
        limits=['Authored simultaneous entry before sample zero and exit at sample %d.'%exit_tick,'Idle covers all seven items; OPTIONS/DRAGON SUMMONING use host trig; CUSTOMIZE secondary clock starts at authored zero.' if idle else 'Per-part idle offsets are zero; emphasis is optional and native selection scheduling remains pending.'])
    if emphasis_tick is not None:
        result.update(version=2,emphasis_tick=emphasis_tick)
        result['limits'].append('Common emphasis begins at an authored tick; idle offsets freeze and phase 3 persists until exit. Native selection scheduling remains pending.')
    return result
