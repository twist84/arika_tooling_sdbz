"""Test-only integer R5900 subset for the native RNG and 64-bit multiply helper."""
MASK64=(1<<64)-1


def signed(value,width):return ((value+(1<<(width-1)))&((1<<width)-1))-(1<<(width-1))


class c_rng_oracle:
    def __init__(self,kernel):
        self.m_kernel=kernel;self.m_code={};self.m_memory={};self.m_registers=[0]*32
        self.m_hi=0;self.m_lo=0
        for address,words in [(kernel['address'],kernel['words']),(kernel['multiply_address'],kernel['multiply_words'])]:
            self.m_code.update({address+i*4:word for i,word in enumerate(words)})
        self.write(kernel['context_pointer_address'],0x500000,4)

    def write(self,address,value,size):
        for i in range(size):self.m_memory[address+i]=(value>>(8*i))&255
    def read(self,address,size):return sum(self.m_memory.get(address+i,0)<<(8*i) for i in range(size))

    def scalar(self,word):
        if word==0:return
        r=self.m_registers;op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;fn=word&63;shift=(word>>6)&31
        imm=signed(word&65535,16);address=(r[rs]+imm)&0xffffffff
        if op==15:r[rt]=signed((word&65535)<<16,32)
        elif op==13:r[rt]=r[rs]|(word&65535)
        elif op==9:r[rt]=signed(r[rs]+imm,32)
        elif op==25:r[rt]=r[rs]+imm
        elif op==35:r[rt]=signed(self.read(address,4),32)
        elif op==55:r[rt]=self.read(address,8)
        elif op==63:self.write(address,r[rt],8)
        elif op==0 and fn in (0x38,0x3c):r[rd]=r[rt]<<(shift+(32 if fn==0x3c else 0))
        elif op==0 and fn==0x3e:r[rd]=r[rt]>>(shift+32)
        elif op==0 and fn==0x3f:r[rd]=signed(r[rt],64)>>(shift+32)
        elif op==0 and fn==0x21:r[rd]=signed(r[rs]+r[rt],32)
        elif op==0 and fn==0x24:r[rd]=r[rs]&r[rt]
        elif op==0 and fn==0x25:r[rd]=r[rs]|r[rt]
        elif op==0 and fn in (0x18,0x19):
            a,b=(signed(r[rs],32),signed(r[rt],32)) if fn==0x18 else (r[rs]&0xffffffff,r[rt]&0xffffffff)
            product=(a*b)&MASK64;self.m_lo=signed(product,32)&MASK64;self.m_hi=signed(product>>32,32)&MASK64
            if rd:r[rd]=self.m_lo
        elif op==0 and fn==0x12:r[rd]=self.m_lo
        elif op==0 and fn==0x10:r[rd]=self.m_hi
        elif op==28 and fn==0x18:r[rd]=signed(signed(r[rs],32)*signed(r[rt],32),32)
        else:raise AssertionError('unsupported RNG word 0x%08X'%word)
        for index in (rt,rd):r[index]&=MASK64
        r[0]=0

    def run(self,address):
        pc=address;r=self.m_registers;r[29]=0x100000;r[31]=0xf00000
        for _ in range(512):
            if pc==0xf00000:return r[2]
            word=self.m_code[pc];op=word>>26
            if op==3:
                target=(word&0x3ffffff)<<2;r[31]=pc+8
                self.scalar(self.m_code[pc+4]);pc=target
            elif op==0 and word&63==8:
                target=r[(word>>21)&31]&0xffffffff
                self.scalar(self.m_code[pc+4]);pc=target
            else:self.scalar(word);pc+=4
        raise AssertionError('RNG instruction bound exceeded')

    def step(self,state):
        address=0x500000+self.m_kernel['state_offset'];self.write(address,state,8)
        output=self.run(self.m_kernel['address'])
        return self.read(address,8),output

    def multiply(self,a,b):
        self.m_registers[4]=a;self.m_registers[5]=b
        return self.run(self.m_kernel['multiply_address'])
