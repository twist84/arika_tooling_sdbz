"""Test-only masked VU arithmetic subset for the extracted strip rotation blocks.

Uses host float32, not VU hardware flags, pipeline or accumulator precision.
"""
import math
from arika_menu_layout import f32


def vu_word(word,vectors,accumulator,q):
    mask=(word>>21)&15;ft=(word>>16)&31;fs=(word>>11)&31;fd=(word>>6)&31;fn=word&63;low=word&2047
    result=None;target=fd;write_acc=False
    if low in (0x2ff,0x3bf):return accumulator,q
    if low==0x3bd:return accumulator,f32(math.sqrt(max(0,vectors[ft][3])))
    if low==0x33d:result=vectors[fs][1:]+vectors[fs][:1];target=ft
    elif low in (0x1bc,0x1bd,0x1be,0x1bf):
        result=[f32(v*vectors[ft][low&3]) for v in vectors[fs]];write_acc=True
    elif low in (0xbc,0xbd,0xbe,0xbf):
        result=[f32(accumulator[i]+f32(v*vectors[ft][low&3])) for i,v in enumerate(vectors[fs])];write_acc=True
    elif fn in (0,4,8,9,10,11,24,25,26,27):
        component=fn&3
        if fn in (0,4):result=[f32(v+vectors[ft][component]) if fn==0 else f32(v-vectors[ft][component]) for v in vectors[fs]]
        elif 8<=fn<=11:result=[f32(accumulator[i]+f32(v*vectors[ft][component])) for i,v in enumerate(vectors[fs])]
        else:result=[f32(v*vectors[ft][component]) for v in vectors[fs]]
    elif fn in (0x28,0x2a,0x2c):
        result=[f32(a+b) if fn==0x28 else f32(a*b) if fn==0x2a else f32(a-b) for a,b in zip(vectors[fs],vectors[ft])]
    elif fn in (0x20,0x24):result=[f32(v+q) if fn==0x20 else f32(v-q) for v in vectors[fs]]
    else:raise AssertionError('unsupported VU word 0x%08X'%word)
    for i in range(4):
        if mask&(8>>i):
            if write_acc:accumulator[i]=result[i]
            else:vectors[target][i]=result[i]
    vectors[0]=[0,0,0,1]
    return accumulator,q


def native_matrix(kernel,command_angle):
    from arika_menu_strip_preview import HALF_PI
    angle=f32(-command_angle);negative=angle<0
    t=f32(angle+HALF_PI) if negative else f32(HALF_PI-angle)
    v=[[0.0]*4 for _ in range(32)];v[0]=[0,0,0,1];v[5]=list(kernel['polynomial']);v[6][0]=t
    acc=[0.0]*4;q=0
    for record in kernel['trig_words']:
        word=record['word']
        if word==0x4b0001a0 and negative:continue
        if word==0x4b0001a4 and not negative:continue
        acc,q=vu_word(word,v,acc,q)
    a,b=v[6][:2]
    v=[[0.0]*4 for _ in range(32)];v[0]=[0,0,0,1]
    v[4]=[1,0,0,0];v[5]=[0,1,0,0];v[6]=[0,0,1,0];v[20][0]=a;v[21][0]=b
    acc=[0.0]*4
    for record in kernel['matrix_words']:acc,q=vu_word(record['word'],v,acc,q)
    return [v[4],v[5],v[6]]
