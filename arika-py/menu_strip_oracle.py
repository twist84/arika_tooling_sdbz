"""Test-only scalar R5900 subset for extracted strip/tile helpers; GPU calls are stubs.

Arithmetic uses host float32, not a PS2 hardware FPU implementation.
"""
import math
import struct


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def real(value):return struct.unpack('<f',struct.pack('<I',value&0xffffffff))[0]
def signed(value,width=64):return ((value+(1<<(width-1)))&((1<<width)-1))-(1<<(width-1))


class c_strip_oracle:
    def __init__(self,kernels,uv,orientation,start,end,period,phase,origin,motion_offset=0,depth=0):
        self.m_code={kernels['draw_address']+i*4:w for i,w in enumerate(kernels['draw_words'])}
        self.m_code.update({kernels['clock_address']+i*4:w for i,w in enumerate(kernels['clock_words'])})
        self.m_memory={};self.m_registers=[0]*32;self.m_floats=[0]*32;self.m_accumulator=0;self.m_condition=False
        self.m_commands=[];self.m_rect=None;self.m_direct_stubs={};self.m_direct_calls=[];self.m_indirect_stubs={}
        self.m_registers[4]=0x1000;self.m_registers[5]=0x2000;self.m_registers[29]=0x100000;self.m_registers[31]=0xf00000
        self.m_floats[12]=bits(depth);self.m_floats[13]=bits(motion_offset)
        self.write(0x1000,struct.pack('<4h',*uv));self.write_int(0x1014,orientation,1)
        for offset,value in [(8,start),(12,end),(16,period),(24,phase)]:self.write_float(0x1000+offset,value)
        self.write_int(0x1020,0x3000,4)
        self.write_int(0x3018,0xf00018,4);self.write_int(0x3010,0xf00010,4)
        self.write(0x2000,struct.pack('<2f',*origin))

    def write(self,address,data):
        for i,value in enumerate(data):self.m_memory[address+i]=value
    def read(self,address,size):return bytes(self.m_memory.get(address+i,0) for i in range(size))
    def read_int(self,address,size):return int.from_bytes(self.read(address,size),'little')
    def write_int(self,address,value,size):self.write(address,(value&((1<<(size*8))-1)).to_bytes(size,'little'))
    def write_float(self,address,value):self.write_int(address,bits(value),4)
    def read_float(self,address):return real(self.read_int(address,4))

    def scalar(self,word):
        if word==0:return
        r=self.m_registers;f=self.m_floats
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;fn=word&63;shift=(word>>6)&31
        immediate=signed(word&65535,16);address=(r[rs]+immediate)&0xffffffff
        if op==9:r[rt]=signed(r[rs]+immediate,32)
        elif op==15:r[rt]=signed((word&65535)<<16,32)
        elif op==13:r[rt]=r[rs]|(word&65535)
        elif op==12:r[rt]=r[rs]&(word&65535)
        elif op==10:r[rt]=int(r[rs]<immediate)
        elif op==11:r[rt]=int((r[rs]&0xffffffffffffffff)<(immediate&0xffffffffffffffff))
        elif op==0 and fn in (0x21,0x2d):r[rd]=signed(r[rs]+r[rt],32 if fn==0x21 else 64)
        elif op==0 and fn==0:r[rd]=signed(r[rt]<<shift,32)
        elif op==0 and fn==0x23:r[rd]=signed(r[rs]-r[rt],32)
        elif op==0 and fn==0x2a:r[rd]=int(r[rs]<r[rt])
        elif op==0 and fn==0x3c:r[rd]=signed(r[rt]<<(shift+32))
        elif op==0 and fn==0x3f:r[rd]=signed(r[rt])>>(shift+32)
        elif op in (0x20,0x21,0x23,0x24,0x25,0x37,0x1e):
            size={0x20:1,0x21:2,0x23:4,0x24:1,0x25:2,0x37:8,0x1e:16}[op]
            value=self.read_int(address,size)
            r[rt]=signed(value,64 if op==0x1e else size*8) if op not in (0x24,0x25) else value
        elif op in (0x28,0x29,0x2b,0x3f,0x1f):self.write_int(address,r[rt],{0x28:1,0x29:2,0x2b:4,0x3f:8,0x1f:16}[op])
        elif op==0x31:f[rt]=self.read_int(address,4)
        elif op==0x39:self.write_int(address,f[rt],4)
        elif op==17 and rs==4:f[rd]=r[rt]&0xffffffff
        elif op==17 and rs==0:r[rt]=signed(f[rd],32)
        elif op==17 and rs==20 and fn==32:f[shift]=bits(signed(f[rd],32))
        elif op==17 and rs==16:
            a,b=real(f[rd]),real(f[rt])
            if fn==0:f[shift]=bits(a+b)
            elif fn==1:f[shift]=bits(a-b)
            elif fn==2:f[shift]=bits(a*b)
            elif fn==3:f[shift]=bits(a/b)
            elif fn==6:f[shift]=f[rd]
            elif fn==7:f[shift]=bits(-a)
            elif fn==24:self.m_accumulator=bits(a+b)
            elif fn==28:f[shift]=bits(real(self.m_accumulator)+real(bits(a*b)))
            elif fn==29:f[shift]=bits(real(self.m_accumulator)-real(bits(a*b)))
            elif fn==36:f[shift]=math.trunc(a)&0xffffffff
            elif fn==52:self.m_condition=a<b
            elif fn==54:self.m_condition=a<=b
            else:raise AssertionError('unsupported FPU word 0x%08X'%word)
        else:raise AssertionError('unsupported scalar word 0x%08X'%word)
        r[0]=0

    def run(self,address):
        pc=address;r=self.m_registers
        for _ in range(4096):
            if pc==0xf00000:return
            word=self.m_code[pc];op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;fn=word&63
            is_branch=op in (4,5,6) or (op==17 and rs==8)
            is_jump=op==0 and fn in (8,9)
            if is_branch:
                if op==4:take=r[rs]==r[rt]
                elif op==5:take=r[rs]!=r[rt]
                elif op==6:take=r[rs]<=0
                else:take=self.m_condition==bool(rt&1)
                target=pc+4+signed(word&65535,16)*4
                self.scalar(self.m_code[pc+4]);pc=target if take else pc+8
            elif op==3:
                target=(word&0x3ffffff)<<2
                if target not in self.m_direct_stubs and target not in self.m_code:raise AssertionError('unstubbed direct call')
                r[31]=pc+8;self.scalar(self.m_code[pc+4]);self.m_direct_calls.append(target)
                if target not in self.m_direct_stubs:
                    pc=target;continue
                stub=self.m_direct_stubs[target]
                if callable(stub):stub(self)
                else:
                    for register,value in stub.items():r[register]=value
                pc+=8
            elif is_jump:
                target=r[rs]&0xffffffff
                if fn==9:r[(word>>11)&31]=pc+8
                self.scalar(self.m_code[pc+4])
                if target==0xf00018:
                    self.m_rect=list(struct.unpack('<4h',self.read(r[5]&0xffffffff,8)));pc+=8
                elif target==0xf00010:
                    sprite=r[4]&0xffffffff
                    self.m_commands.append(dict(uv_xywh=list(self.m_rect),position=[self.read_float(sprite+16),self.read_float(sprite+20)],depth=self.read_float(sprite+24)))
                    pc+=8
                elif target in self.m_indirect_stubs:
                    self.m_indirect_stubs[target](self);pc+=8
                else:pc=target
            else:self.scalar(word);pc+=4
        raise AssertionError('strip oracle instruction bound exceeded')
