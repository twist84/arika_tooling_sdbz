import json
from pathlib import Path
import random
import struct
import unittest
from arika_menu_plain import plain_sprite


def float_bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def bits_float(value):return struct.unpack('<f',struct.pack('<I',value&0xffffffff))[0]
def signed32(value):return ((value+0x80000000)&0xffffffff)-0x80000000


def native_endpoint(words,uv,position,scale):
    """Interpret the ELF scalar endpoint block, with host float32 accumulator math."""
    sprite=bytearray(96)
    struct.pack_into('<2f',sprite,16,*position);struct.pack_into('<2f',sprite,32,*scale)
    u0,v0,u1,v1=uv;struct.pack_into('<4h',sprite,40,u0,u1,v0,v1)
    registers=[0]*32;registers[20]=0x1000;registers[28]=0x2000
    floats=[0]*32;accumulator=0
    for word in words:
        op=word>>26;rs=(word>>21)&31;rt=(word>>16)&31;rd=(word>>11)&31;fn=word&63
        immediate=((word&65535)+32768)%65536-32768
        if op==0x21:registers[rt]=struct.unpack_from('<h',sprite,registers[rs]+immediate-0x1000)[0]
        elif op==0x31:
            floats[rt]=struct.unpack_from('<I',sprite,registers[rs]+immediate-0x1000)[0] if rs==20 else 0
        elif op==9:registers[rt]=signed32(registers[rs]+immediate)
        elif op==0 and fn in (0x22,0x23):registers[rd]=signed32(registers[rs]-registers[rt])
        elif op==0 and fn==0x2a:registers[rd]=int(registers[rs]<registers[rt])
        elif op==0 and fn==0x0a:
            if registers[rt]==0:registers[rd]=registers[rs]
        elif op==17 and rs==4:floats[rd]=registers[rt]&0xffffffff
        elif op==17 and rs==20 and fn==0x20:floats[(word>>6)&31]=float_bits(signed32(floats[rd]))
        elif op==17 and rs==16:
            fd=(word>>6)&31
            if fn==0x18:accumulator=float_bits(bits_float(floats[rd])+bits_float(floats[rt]))
            elif fn==0x1c:
                product=float_bits(bits_float(floats[rd])*bits_float(floats[rt]))
                floats[fd]=float_bits(bits_float(accumulator)+bits_float(product))
            elif fn==6:floats[fd]=floats[rd]
            else:raise AssertionError('unsupported native FPU word')
        elif op==3:pass # only the final vertex call; its delay-slot MADD follows
        else:raise AssertionError('unsupported native word 0x%08X'%word)
        registers[0]=0
    return floats[12],floats[13]


class MenuPlainTests(unittest.TestCase):
    def setUp(self):
        self.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())['plain_sprite_geometry']

    def test_plain_sprite_is_top_left_scaled(self):
        geometry=plain_sprite([474,0,15,26],[0,116],[21.5,1])
        self.assertEqual(geometry['vertices'],[[0,116],[322.5,116],[0,142],[322.5,142]])
        self.assertEqual(geometry['uv_endpoints'],[474,0,489,26])

    def test_reversed_uv_negative_scale_and_s16_wrap(self):
        geometry=plain_sprite([20,30,0,0],[100,200],[-2,.5],'endpoints')
        self.assertEqual(geometry['bounds'],[60,200,100,215])
        self.assertEqual(geometry['uv_endpoints'],[20,30,0,0])
        self.assertEqual(plain_sprite([32760,0,20,1],[0,0])['uv_endpoints'][2],-32756)
        with self.assertRaises(ValueError):plain_sprite([0,0,1,1],[0,0],uv_interpretation='unknown')

    def test_native_scalar_endpoint_block_matches_159_cases(self):
        geometries=[p['geometry'] for g in self.report['first_groups'] for p in g['parts']]
        geometries.extend(p['geometry'] for p in self.report['shared'])
        rng=random.Random(840)
        for _ in range(128):
            uv=[rng.randint(-100,500) for _ in range(4)]
            position=[rng.randint(-1000,1000)/2 for _ in range(2)]
            scale=[rng.choice([-2,-.5,.25,1,2,21.5]) for _ in range(2)]
            geometries.append(plain_sprite(uv,position,scale,'endpoints'))
        self.assertEqual(len(geometries),159)
        for geometry in geometries:
            actual=native_endpoint(self.report['endpoint_kernel']['words'],geometry['uv_endpoints'],geometry['position'],geometry['scale'])
            expected=tuple(float_bits(v) for v in geometry['vertices'][3])
            self.assertEqual(actual,expected)

    def test_runtime_omissions_and_shared_overlay_are_explicit(self):
        self.assertEqual(self.report['first_quad_count'],21)
        self.assertEqual(self.report['shared_quad_count'],10)
        first=[v for v in self.report['unresolved'] if v['group']=='first']
        self.assertEqual(len(first),0)
        overlay=next(v for v in self.report['shared'] if v['label']=='conditional_overlay')
        self.assertEqual(overlay['geometry']['bounds'],[0,0,512,448])
        self.assertIn('state-driven',overlay['draw_condition'])


if __name__=='__main__':unittest.main()
