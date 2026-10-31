"""ELF memory plus verified zero-fill/menu-constructor startup subset."""
import struct


class c_startup_image:
    def __init__(self,raw):
        self.m_data=raw.m_data;self.m_raw=raw;self.m_patches={};self.m_writes=[];self.m_load_segments=[]
        offset=struct.unpack_from('<I',self.m_data,28)[0];stride,count=struct.unpack_from('<HH',self.m_data,42)
        for index in range(count):
            kind,file_offset,base,_,file_size,memory_size,_,_=struct.unpack_from('<8I',self.m_data,offset+index*stride)
            if kind==1:
                if memory_size<file_size or base+memory_size>0x100000000:raise ValueError('invalid ELF memory extent')
                self.m_load_segments.append((file_offset,base,file_size,memory_size))

    def read(self,address,size):
        if size<0:raise ValueError('negative memory read size')
        for offset,base,file_size,memory_size in self.m_load_segments:
            if base<=address and address+size<=base+memory_size:
                result=bytearray(size);available=max(0,min(size,base+file_size-address))
                if available:result[:available]=self.m_data[offset+address-base:offset+address-base+available]
                for index in range(size):
                    if address+index in self.m_patches:result[index]=self.m_patches[address+index]
                return bytes(result)
        raise ValueError('address outside loaded ELF memory: 0x%08X'%address)

    def words(self,address,count):return list(struct.unpack('<'+'I'*count,self.read(address,count*4)))

    def source_kind(self,address,size):
        self.read(address,size)
        if any(address+i in self.m_patches for i in range(size)):return 'startup_constructor'
        for _,base,file_size,memory_size in self.m_load_segments:
            if base<=address and address+size<=base+memory_size:
                return 'file_backed' if address+size<=base+file_size else 'startup_zero_fill'
        raise ValueError('unmapped source')

    def run_initializer(self,address,gp):
        from arika_menus import signed16
        registers=[None]*32;registers[0]=0;registers[28]=gp
        floats=[None]*32;return_at=None
        for index in range(64):
            pc=address+index*4;word=self.words(pc,1)[0]
            op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;fs=(word>>11)&31;fd=(word>>6)&31;fn=word&63
            if word==0:pass
            elif word==0x03e00008:return_at=pc+4
            elif op==15:registers[rt]=(word&65535)<<16
            elif op==17 and rs==4:
                if registers[rt] is None:raise ValueError('unknown initializer GPR')
                floats[fs]=registers[rt]&0xffffffff
            elif op in (49,57):
                if registers[rs] is None:raise ValueError('unknown initializer pointer')
                target=(registers[rs]+signed16(word))&0xffffffff
                if op==49:floats[rt]=self.words(target,1)[0]
                else:
                    if floats[rt] is None:raise ValueError('unknown initializer float')
                    previous=self.words(target,1)[0]
                    for i,value in enumerate(struct.pack('<I',floats[rt])):self.m_patches[target+i]=value
                    self.m_writes.append(dict(function=address,instruction=pc,address=target,previous_bits=previous,bits=floats[rt],value=struct.unpack('<f',struct.pack('<I',floats[rt]))[0]))
            elif op==17 and rs==16 and fn in (0,1):
                if floats[fs] is None or floats[rt] is None:raise ValueError('unknown initializer operand')
                a,b=[struct.unpack('<f',struct.pack('<I',floats[i]))[0] for i in (fs,rt)]
                floats[fd]=struct.unpack('<I',struct.pack('<f',a+b if fn==0 else a-b))[0]
            else:raise ValueError('unsupported menu initializer instruction at 0x%08X'%pc)
            registers[0]=0
            if pc==return_at:return
        raise ValueError('initializer exceeded instruction bound')


def menu_startup(raw,gp):
    image=c_startup_image(raw)
    if raw.words(0x10011c,4)!=[0x3c020050,0x3c030064,0x2442c900,0x2463c380]:raise ValueError('startup zero-fill range mismatch')
    constructors=raw.words(0x4e3150,(0x4e32a8-0x4e3150)//4)
    if constructors[73:75]!=[0x4e2370,0x4e23b0]:raise ValueError('menu constructor order mismatch')
    functions=[]
    for address,end in [(0x4e2370,0x4e23a8),(0x4e23b0,0x4e23d0)]:
        functions.append(dict(address=address,words=raw.words(address,(end-address)//4)))
        image.run_initializer(address,gp)
    values=[]
    for offset in [-5952,-5948,-5944,-5940,-5936,-5932,-5920,-5916,-5912,-5908,-5904,-10720,-10716]:
        address=gp+offset
        values.append(dict(address=address,value=struct.unpack('<f',image.read(address,4))[0],source=image.source_kind(address,4)))
    metadata=dict(model='verified_menu_startup_subset_v1',zero_fill_start=0x4fc900,zero_fill_end=0x63c380,
        clear_loop_address=0x10011c,constructor_driver=0x1718c0,constructor_walker=0x171d20,
        constructor_table_start=0x4e3150,constructor_table_end=0x4e32a8,constructor_count=len(constructors),
        functions=functions,writes=image.m_writes,position_values=values,
        inputs=[dict(address=gp+o,bits=raw.words(gp+o,1)[0]) for o in [-19788,-19576,-19568]],
        limits='Loaded zero-fill plus two verified menu constructors only; not all global constructors or later runtime writes are simulated.')
    return image,metadata
