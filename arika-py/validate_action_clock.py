#!/usr/bin/env python3
"""Check common startup arguments against original R5900 instructions."""
import argparse
import json
from pathlib import Path
import struct
from arika_actions import c_elf_reader,common_tables
from arika_action_clock import startup_control,startup_settings
from arika_face_player import f32
from arika_clock import c_native_clock
from arika_import import write_output


def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floating(v):return struct.unpack('<f',struct.pack('<I',v))[0]


def native_startup(reader,records,index,carry=.03125):
    memory={};r=[0]*32;f=[0]*32;obj=0x1000;table=0x2000;sp=0x3000
    def put(address,value,size=4):
        for i,b in enumerate((value&((1<<(8*size))-1)).to_bytes(size,'little')):memory[address+i]=b
    def get(address,size=4):
        return int.from_bytes(bytes(memory[address+i] if address+i in memory else reader.read(address+i,1)[0] for i in range(size)),'little')
    put(obj+0x88,table);put(obj+0x90,index);put(obj+0x8C,0);put(obj+12,0x4000);put(0x4004,0x5000)
    for i,record in enumerate(records):
        body=struct.pack('<HHfffI',record['motion_id'],record['variant'],record['speed'],record['start_frame'],record['end_frame'],record['flags'])
        for j,b in enumerate(body):put(table+20*i+j,b,1)
    r[4]=r[17]=obj;r[29]=sp;r[3]=0xBF800000;f[12]=bits(f32(carry));pc=0x1D7140;pending=None;lookups=[]
    for _ in range(400):
        if pc in (0x1D7404,0x1D7408):return None
        if pc==0x1D74A0:
            lookups.append((r[5],r[6]));r[2]=0x10007;pc=r[31];continue # Successful CHT bank 1/index 7 fixture.
        if pc==0x1B9690:
            return dict(segment=get(obj+0x90),motion_index=r[5],binding_bank=get(obj+0x94),lookup=lookups,
                wrapper_resource=get(0x4030),settings=dict(blend_request=floating(f[12]),stop_after=floating(f[13]),
                speed=floating(f[14]),start_frame=floating(f[15]),end_frame=floating(f[16]),flags=r[6]))
        word=struct.unpack('<I',reader.read(pc,4))[0];op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;sh=(word>>6)&31
        imm=word&65535;signed=imm if imm<32768 else imm-65536;old=pending;pending=None
        if op==0:
            fn=word&63
            if fn==0:r[rd]=r[rt]<<sh
            elif fn in (0x21,0x2D):r[rd]=r[rs]+r[rt]
            elif fn==0x23:r[rd]=r[rs]-r[rt]
            elif fn==0x24:r[rd]=r[rs]&r[rt]
            elif fn==0x3C:r[rd]=r[rt]<<(sh+32)
            elif fn==0x3F:
                v=r[rt];v=v-(1<<64) if v&(1<<63) else v;r[rd]=v>>(sh+32)
            else:raise ValueError('unsupported startup SPECIAL at '+hex(pc))
        elif op==15:r[rt]=imm<<16
        elif op in (9,25):r[rt]=r[rs]+signed
        elif op==12:r[rt]=r[rs]&imm
        elif op==13:r[rt]=r[rs]|imm
        elif op in (35,37):r[rt]=get((r[rs]+signed)&0xFFFFFFFF,4 if op==35 else 2)
        elif op in (40,43):put((r[rs]+signed)&0xFFFFFFFF,r[rt],1 if op==40 else 4)
        elif op in (4,5):pending=pc+4+signed*4 if (r[rs]==r[rt])==(op==4) else pc+8
        elif op in (2,3):
            if op==3:r[31]=pc+8
            pending=((pc+4)&0xF0000000)|((word&0x3FFFFFF)<<2)
        elif op==49:f[rt]=get((r[rs]+signed)&0xFFFFFFFF)
        elif op==57:put((r[rs]+signed)&0xFFFFFFFF,f[rt])
        elif op==17:
            if rs==4:f[rd]=r[rt]&0xFFFFFFFF
            elif rs==16 and word&63==6:f[sh]=f[rd]
            else:raise ValueError('unsupported startup COP1 at '+hex(pc))
        else:raise ValueError('unsupported startup opcode at '+hex(pc))
        r=[v&0xFFFFFFFFFFFFFFFF for v in r];r[0]=0;pc=old if old is not None else pc+4
    raise ValueError('startup interpreter limit')


def native_blend_setup(reader,total,remaining,request):
    # Valid-context initializer prefix, stopping after the previous-reference clear.
    obj=0x1000;memory={obj:0xF000FFFF,obj+24:bits(total),obj+28:bits(remaining),obj+44:0x12345678}
    r=[0]*32;f=[0]*32;r[18]=obj;f[12]=bits(request);condition=False;pc=0x1B96FC;pending=None
    for _ in range(40):
        if pc==0x1B9720:return floating(memory[obj+24]),floating(memory[obj+28]),memory[obj+44],memory[obj]
        word=struct.unpack('<I',reader.read(pc,4))[0];op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;sh=(word>>6)&31
        imm=word&65535;signed=imm if imm<32768 else imm-65536;old=pending;pending=None
        if word==0:pass
        elif op==0 and word&63==0:r[rd]=r[rt]<<sh
        elif op==35:r[rt]=memory.get(r[rs]+signed,0)
        elif op==43:memory[r[rs]+signed]=r[rt]
        elif op==57:memory[r[rs]+signed]=f[rt]
        elif op==12:r[rt]=r[rs]&imm
        elif op==4:pending=pc+4+signed*4 if r[rs]==r[rt] else pc+8
        elif op==17:
            if rs==4:f[rd]=r[rt]
            elif rs==8:pending=pc+4+signed*4 if condition==bool(rt&1) else pc+8
            elif rs==16 and word&63==0x34:condition=floating(f[rd])<floating(f[rt])
            else:raise ValueError('unsupported blend setup COP1')
        else:raise ValueError('unsupported blend setup opcode at '+hex(pc))
        r[0]=0;pc=old if old is not None else pc+4
    raise ValueError('blend setup prefix limit')


def audit(data):
    tables=common_tables(data);reader=c_elf_reader(data);checked=synthetic=0;unsupported=[]
    def check(records,index):
        control=startup_control(records,index);actual=native_startup(reader,records,index)
        if control['segment'] is None:
            if actual is not None:raise ValueError('native startup stop mismatch')
            return
        target=control['segment'];record=records[target]
        expected=startup_settings(record,control['blend_request'])
        if actual['segment']!=target or actual['settings']!=expected or actual['lookup']!=[(record['motion_id'],record['variant'])]:
            raise ValueError('native startup argument mismatch '+repr((actual,control,expected)))
        if (actual['motion_index'],actual['binding_bank'],actual['wrapper_resource'])!=(7,1,0x5018):
            raise ValueError('native wrapper binding mismatch')
    for action in tables['actions']:
        for index in range(len(action['records'])):
            try:startup_control(action['records'],index)
            except ValueError as error:unsupported.append(dict(slot=action['slot'],segment=index,reason=str(error)));continue
            check(action['records'],index);checked+=1
    for index in range(4):
        for flags in [0,0x10000,0x20000,0x30000,0x200000,0x210000,0x220000,0x230000]+[base|target for base in (0x40000,0x50000,0x60000,0x70000,0x240000,0x250000,0x260000,0x270000) for target in range(4)]:
            records=[dict(motion_id=i,variant=i+1,speed=f32(.5+i*.25),start_frame=f32(i+.5),end_frame=f32(i+10),flags=0x10000) for i in range(4)]
            records[index]['flags']=flags
            try:startup_control(records,index)
            except ValueError:continue
            check(records,index);synthetic+=1
    inherited=0
    for total in (0.,f32(.17),4.):
        for remaining in (total,f32(total*.5),f32(-.01)):
            for request in (-1.,0.,f32(.17),2.):
                expected_total,expected_remaining,previous,flags=native_blend_setup(reader,total,remaining,request)
                clock=c_native_clock(60,3,blend=request,inherited_blend=(total,remaining))
                if (bits(clock.m_blend_total),bits(clock.m_blend_remaining),previous,flags)!=(bits(expected_total),bits(expected_remaining),0,0xF):
                    raise ValueError('blend inheritance mismatch')
                inherited+=1
    return dict(format='ARIKA_COMMON_STARTUP_VALIDATION',elf_sha256=tables['elf_sha256'],common_cases_checked=checked,
        blend_initializer_cases_checked=inherited,
        synthetic_cases_checked=synthetic,unsupported=unsupported,
        scope='Original 0x1D7120 control/startup prefix and 0x1D7470 wrapper through entry to 0x1B9690; separate valid-context initializer prefix 0x1B96FC through 0x1B971C checks blend inheritance/reset and previous-reference clear. Successful CHT lookup is stubbed to bank 1/index 7. Checks target, requested ID/variant, raw float arguments, flags, bank and resource-pointer arithmetic. Does not validate CHT lookup implementation, root transforms, callbacks, complete scalar chain, or pose evaluation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('elf');parser.add_argument('output');args=parser.parse_args()
    result=audit(Path(args.elf).read_bytes());write_output(args.output,json.dumps(result,indent=2).encode(),[args.elf])
    print('Native common startup cases:',result['common_cases_checked'],'synthetic:',result['synthetic_cases_checked'])


if __name__=='__main__':main()
