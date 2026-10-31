"""Recovered common directional emphasis curves for labels and character groups."""
import math
import struct
from arika_menu_banner import sample_curve
from arika_menu_layout import f32


def recover_emphasis(elf,gp):
    def curve(values,times,n):return dict(values_address=values,times_address=times,values=list(struct.unpack('<'+'f'*n,elf.read(values,n*4))),times=list(struct.unpack('<'+'f'*n,elf.read(times,n*4))))
    result={}
    for name,address,end,pulse,times,envelope,envelope_times in [('labels',0x37e460,0x37e560,0x4aa2c0,0x4aa2b0,gp-19376,gp-19384),
        ('characters',0x37f5f0,0x37f6d0,0x4aa360,0x4aa350,gp-19272,gp-19280)]:
        wave=curve(pulse,times,4)
        result[name]=dict(address=address,words=elf.words(address,(end-address)//4),wave=wave,envelope=curve(envelope,envelope_times,2),period=f32(wave['times'][-1]+1))
    return dict(kernels=result,global_pointer=gp,remainder_address=0x185e50,
        limits='Common emphasis displacement only; activation is authored, native selection scheduling and GPU blending are not reproduced.')


def emphasis_offset(age,direction,kernel,reset_on_completion=True):
    age=f32(age);phase=f32(math.fmod(age,kernel['period']))
    pulse=sample_curve(kernel['wave'],phase);amplitude=sample_curve(kernel['envelope'],age)
    value=f32(pulse*amplitude);complete=age>=kernel['envelope']['times'][-1]
    offset=[f32(value*d) for d in direction]
    if complete and reset_on_completion:offset=[0.0,0.0]
    return offset,complete
