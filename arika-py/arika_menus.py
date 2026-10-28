#!/usr/bin/env python3
"""Inspect verified main-menu tables in the researched SLES_541.61 ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

SUPPORTED_SHA256='80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
ITEM_VTABLES=[0x4f18f0,0x4f1940,0x4f1ce0,0x4f1dc0,0x4f1990,0x4f1e50,0x4f1ea0]


class c_elf_image:
    def __init__(self,data):
        self.m_data=data;self.m_segments=[]
        if len(data)<52 or data[:7]!=b'\x7fELF\x01\x01\x01':raise ValueError('expected little-endian ELF32')
        if struct.unpack_from('<H',data,18)[0]!=8:raise ValueError('expected MIPS ELF')
        offset=struct.unpack_from('<I',data,28)[0];stride,count=struct.unpack_from('<HH',data,42)
        if stride<32 or offset+stride*count>len(data):raise ValueError('invalid ELF program headers')
        for index in range(count):
            kind,file_offset,address,_,size,_,_,_=struct.unpack_from('<8I',data,offset+index*stride)
            if kind==1:
                if file_offset+size>len(data):raise ValueError('truncated ELF segment')
                self.m_segments.append((file_offset,address,size))

    def read(self,address,size):
        for offset,base,length in self.m_segments:
            if base<=address and address+size<=base+length:
                at=offset+address-base;return self.m_data[at:at+size]
        raise ValueError('address outside file-backed ELF segments: 0x%08X'%address)

    def words(self,address,count):return list(struct.unpack('<'+'I'*count,self.read(address,count*4)))


def signed16(value):return (value&65535)-(65536 if value&32768 else 0)


def elf_global_pointer(elf):
    data=elf.m_data
    offset=struct.unpack_from('<I',data,32)[0]
    stride,count=struct.unpack_from('<HH',data,46)
    if stride<40 or offset+stride*count>len(data):raise ValueError('invalid ELF section headers')
    matches=[]
    for index in range(count):
        section=struct.unpack_from('<10I',data,offset+stride*index)
        if section[1]==0x70000006:
            at,size=section[4:6]
            if size!=24 or at+size>len(data):raise ValueError('invalid MIPS reginfo')
            matches.append(struct.unpack_from('<I',data,at+20)[0])
    if len(matches)!=1:raise ValueError('expected one MIPS reginfo section')
    return matches[0]


def initializer_stores(elf,address,gp,max_instructions=2048):
    """Evaluate the straight-line LUI/ADDIU/SW text initializer, including JR delay slot.

    Deliberately rejects branches/calls and unknown instructions; not a general MIPS emulator.
    """
    registers=[None]*32;registers[0]=0;registers[28]=gp
    stores={};return_at=None
    for index in range(max_instructions):
        pc=address+index*4;word=elf.words(pc,1)[0]
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31
        if word==0:pass
        elif word==0x03e00008 and return_at is None:return_at=pc+4
        elif op==15:registers[rt]=(word&65535)<<16
        elif op==9:
            if registers[rs] is None:raise ValueError('unknown initializer source register')
            registers[rt]=(registers[rs]+signed16(word))&0xffffffff
        elif op==43:
            if registers[rs] is None or registers[rt] is None:raise ValueError('unknown initializer store')
            target=(registers[rs]+signed16(word))&0xffffffff
            if target in stores:raise ValueError('duplicate initializer store')
            stores[target]=dict(value=registers[rt],instruction=pc)
        else:raise ValueError('unsupported initializer instruction at 0x%08X'%pc)
        registers[0]=0
        if pc==return_at:return stores
    raise ValueError('initializer has no bounded return')


def text_block(elf,address):
    count=elf.words(address,1)[0]
    if not 1<=count<=64:raise ValueError('invalid text line count')
    lines=[]
    for pointer in elf.words(address+4,count):
        raw=bytearray()
        for index in range(1024):
            byte=elf.read(pointer+index,1)
            if byte==b'\0':break
            raw.extend(byte)
        else:raise ValueError('unterminated text line')
        lines.append(dict(address=pointer,text=raw.decode('ascii')))
    return dict(address=address,line_count=count,lines=lines)


def neighbor_getter(elf,address):
    words=elf.words(address,5)
    if words[0]>>26==0x24 and words[1]>>16==0x2402 and words[2]>>16==0x2403 and words[3]==0x03e00008 and words[4]==0x0064100a:
        return dict(function=address,flag_offset=words[0]&65535,if_clear=signed16(words[2]),if_set=signed16(words[1]))
    # Tiny getters return a signed constant in the JR delay slot.
    for index,word in enumerate(words[:2]):
        if word==0x03e00008 and words[index+1] in (0x102d,0x1021):return dict(function=address,value=0)
        if word==0x03e00008 and index+1<len(words) and words[index+1]>>16==0x2402:
            return dict(function=address,value=signed16(words[index+1]))
    raise ValueError('unrecognized menu neighbor getter at 0x%08X'%address)


def route_case(elf,address):
    mode=None;screen=46
    for word in elf.words(address,3):
        if word>>16==0x2411:mode=signed16(word)
        elif word>>16==0x2410:screen=signed16(word)
    if mode is None:raise ValueError('route has no mode-selector constant')
    return dict(branch_address=address,mode_selector=mode,next_app_id=screen)


def string_getter(elf,address):
    words=elf.words(address,3)
    if words[0]>>16!=0x3c02 or words[1]!=0x03e00008 or words[2]>>16!=0x2442:raise ValueError('unrecognized string getter')
    pointer=((words[0]&65535)<<16)+signed16(words[2]);value=bytearray()
    for index in range(256):
        byte=elf.read(pointer+index,1)
        if byte==b'\0':return pointer,value.decode('ascii')
        value.extend(byte)
    raise ValueError('unterminated menu name')


def analyze_menu(data):
    from arika_menu_layout import recover_layout
    from arika_menu_first import recover_first
    from arika_menu_plain import recover_plain
    from arika_menu_strips import recover_strip_kernels
    from arika_menu_strip_preview import recover_rotation_kernels
    from arika_menu_tiles import recover_tile_kernel
    from arika_menu_companions import recover_companions
    from arika_menu_rng import recover_rng_kernel
    from arika_menu_startup import menu_startup
    from arika_menu_owner import recover_owner
    from arika_menu_shared import recover_shared
    from arika_menu_banner import recover_banner
    from arika_menu_small import recover_small
    from arika_menu_labels import recover_labels
    from arika_menu_arrows import recover_arrow_baselines
    from arika_menu_characters import recover_characters
    from arika_menu_idle import recover_idle
    from arika_menu_emphasis import recover_emphasis
    digest=hashlib.sha256(data).hexdigest()
    if digest!=SUPPORTED_SHA256:raise ValueError('unsupported ELF build; fixed addresses are verified only for SHA256 '+SUPPORTED_SHA256)
    elf=c_elf_image(data)
    if elf.read(0x4cc8a8,14)!=b'dis/main_menu\0':raise ValueError('menu resource string mismatch')
    if elf.words(0x4f1888,2)!=[0x374f00,0x374f10]:raise ValueError('menu resource vtable mismatch')
    if string_getter(elf,0x374f00)!=(0x4cc8a8,'dis/main_menu'):raise ValueError('resource getter mismatch')
    app_name=string_getter(elf,0x3fe330)[1];menu_name=string_getter(elf,0x37a1e0)[1]
    resource_count=neighbor_getter(elf,0x374f10)['value']
    # Verify the loop bound that the old decompiler missed.
    if elf.words(0x378958,1)[0]!=0x2a430007:raise ValueError('seven-item constructor loop mismatch')
    gp=elf_global_pointer(elf)
    elf,startup=menu_startup(elf,gp)
    text_stores=initializer_stores(elf,0x3a2780,gp)
    items=[];routes=elf.words(0x4d85d0,7);constructors=elf.words(0x4cc8e0,7)
    text_ids=elf.words(0x4a9fa0,7)
    for index,table in enumerate(ITEM_VTABLES):
        neighbors=[neighbor_getter(elf,function) for function in elf.words(table+52,4)]
        store=text_stores[0x60c6c0+text_ids[index]*4]
        help_text=text_block(elf,store['value'])
        help_text['pointer_store_instruction']=store['instruction']
        items.append(dict(index=index,vtable=table,constructor_branch=constructors[index],text_lookup_id=text_ids[index],help_text=help_text,neighbors=neighbors,route=route_case(elf,routes[index])))
    functions={
        'resource_create':0x374df0,'resource_name':0x374f00,'resource_count':0x374f10,
        'resource_poll':0x372530,'resource_entry':0x3725e0,'resource_release':0x372660,
        'app_constructor':0x3fdd60,'app_enter':0x3fde00,'app_load':0x3fdeb0,
        'app_begin_exit':0x3fdfe0,'app_route_after_exit':0x3fe020,'app_unload':0x3fe240,
        'app_draw':0x3fe300,'app_type_name':0x3fe330,
        'menu_create_items':0x378860,'menu_cleanup':0x3798c0,'menu_update':0x379a40,
        'menu_input':0x379c80,'menu_draw':0x379e60,'menu_select':0x379f00,
        'menu_type_name':0x37a1e0}
    arrows=[]
    for direction in range(4):
        endpoints=list(struct.unpack('<4h',elf.read(0x4a9e60+direction*8,8)))
        arrows.append(dict(direction=direction,table_address=0x4a9e60+direction*8,uv_endpoints=endpoints))
    first=recover_first(elf,gp);layout=recover_layout(elf,gp)
    plain=recover_plain(elf,gp,first,layout['layers'])
    layout['first_plain_count']=plain['first_quad_count']
    for composite,group in zip(layout['composites'],plain['first_groups']):
        composite['plain_parts']=[dict(index=len(composite['parts'])+1+i,role='first',label=p['label'],
            texture_entry=p['texture_entry'],zero_offset_pose=p['geometry']) for i,p in enumerate(group['parts'])]
    layout['shared_plain_count']=plain['shared_quad_count']
    layout['shared_diagram_groups']=[dict(item=7,is_shared=True,parts=[dict(index=i,role='shared',label=p['label'],
        texture_entry=p['texture_entry'],zero_offset_pose=p['geometry']) for i,p in enumerate(plain['shared'])])]
    return dict(format='ARIKA_MAIN_MENU_RESEARCH',version=25,elf_sha256=digest,startup=startup,
        item_emphasis=recover_emphasis(elf,gp),
        character_idle=recover_idle(elf,gp),
        item_character_animation=recover_characters(elf,gp,layout),
        arrow_baselines=recover_arrow_baselines(elf,gp),
        item_label_animation=recover_labels(elf,gp,layout['layers']),
        shared_small_animation=recover_small(elf,gp,layout['layers']),
        shared_banner=recover_banner(elf,gp),
        shared_scheduler=recover_shared(elf,gp),
        tile_companion_owner=recover_owner(elf,gp),
        native_rng=recover_rng_kernel(elf),
        shared_companions=recover_companions(elf,gp),
        tile_scroll_kernel=recover_tile_kernel(elf,gp),
        strip_rotation_kernels=recover_rotation_kernels(elf),
        strip_kernels=recover_strip_kernels(elf),
        first_components=first,composite_layout=layout,plain_sprite_geometry=plain,
        text_lookup=dict(global_pointer=gp,initializer=0x3a2780,pointer_table=0x60c6c0,recovered_store_count=len(text_stores),format='u32 line_count; u32 line_pointers[line_count]'),
        resource=dict(name='dis/main_menu',string_address=0x4cc8a8,vtable=0x4f1880,entry_count=resource_count),
        app=dict(type_name=app_name,primary_vtable=0x4f6920,phase_vtable=0x4f6948),
        menu=dict(type_name=menu_name,vtable=0x4f1c50,entry_count=7,
            logical_direction_masks=[8,4,1,2],items=items),functions=functions,
        fields=dict(app=dict(exit_phase=40,load_phase=44,unload_phase=48,menu_controller=80,selected_index=272,cancel_flag=293),
            menu=dict(item_pointers=36,current_index=192,previous_index=196,phase=200,timer=204,idle_timer=208,flags=212)),
        sprite_research=dict(arrow_texture_entry=0,arrow_setup=0x375310,arrow_draw=0x3753a0,arrows=arrows,
            item_0_composite=dict(setup=0x380210,texture_entry=5,table_address=0x4aa450,record_count=7,record_stride=24,
                records=[dict(index=i,uv_fields=list(struct.unpack('<4h',elf.read(0x4aa450+i*24,8))),uv_interpretation='xywh' if i<5 else 'endpoints',placement=list(struct.unpack('<3f',elf.read(0x4aa450+i*24+8,12))),anchor_mode=elf.words(0x4aa450+i*24+20,1)[0]) for i in range(7)])),
        selection_flags=[dict(item=0,offset=0x710,writer=0x3758f0,rule='previous_index == 2'),dict(item=2,offset=0x830,writer=0x37a300,rule='previous_index in (0, 1, 5)')],
        notes=['Names recovered from binary strings; other names are research labels.',
               'Text IDs select help descriptions, not texture-rendered labels; spelling is preserved.',
               'Dynamic neighbor flags record the prior selected item; they are not unlock flags.',
               'Sprite table coordinates are recovered, but complete compositing/animation is not reconstructed.',
               'Mode-selector meaning and physical button mapping are not yet verified.',
               'Resource entry count 13 is distinct from seven selectable menu items.',
               'This is static analysis, not an in-game trace.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('elf');parser.add_argument('output')
    args=parser.parse_args();output=Path(args.output)
    if output.resolve()==Path(args.elf).resolve():parser.error('output must differ from ELF input')
    try:report=analyze_menu(Path(args.elf).read_bytes())
    except ValueError as error:parser.error(str(error))
    output.write_text(json.dumps(report,indent=2)+'\n');print('Wrote verified seven-entry menu map to',output)


if __name__=='__main__':main()
