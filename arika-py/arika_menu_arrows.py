"""Native arrow placement baselines, including conditional history variants."""
import struct
from arika_menu_plain import plain_sprite


def recover_arrow_baselines(elf,gp):
    specs=[(0x375980,0x3759e0,1808,[(3,-19856),(0,-19840)],[(3,-19848),(0,-19840)]),
        (0x375bc0,0x375c10,None,[(2,-19832),(3,-19824),(0,-19816)],None),
        (0x37a3d0,0x37a470,2096,[(2,-19640),(1,-19616),(0,-19608)],[(2,-19640),(1,-19632),(0,-19624)]),
        (0x37b440,0x37b480,None,[(3,-19544),(1,-19536)],None),
        (0x375dc0,0x375e00,None,[(2,-19808),(0,-19800)],None),
        (0x37b8e0,0x37b930,None,[(2,-19520),(3,-19512),(1,-19504)],None),
        (0x37baf0,0x37bb30,None,[(2,-19496),(1,-19488)],None)]
    result=[]
    for item,(address,end,flag,zero,one) in enumerate(specs):
        variants=[]
        for entries in (zero,one or zero):
            parts=[]
            for direction,offset in entries:
                uv=list(struct.unpack('<4h',elf.read(0x4a9e60+direction*8,8)));position=list(struct.unpack('<2f',elf.read(gp+offset,8)))
                geometry=plain_sprite(uv,[0,0],uv_interpretation='endpoints');w=abs(uv[2]-uv[0]);h=abs(uv[3]-uv[1])
                geometry=plain_sprite(uv,[position[0]-w/2,position[1]-h/2],uv_interpretation='endpoints')
                geometry['depth']=95
                parts.append(dict(direction=direction,position_address=gp+offset,base=position,geometry=geometry))
            variants.append(parts)
        result.append(dict(item=item,address=address,words=elf.words(address,(end-address)//4),flag_offset=flag,variants=variants))
    return dict(items=result,global_pointer=gp,texture_entry=0,depth=95,
        limits='Static base positions; bob displacement is zero in the preview. Conditional history flags default to zero.')
