import json
from pathlib import Path
import random
import struct
import unittest
import xml.etree.ElementTree as ET
from arika_menu_companions import empty_slot,spawn_slot,update_slot,attempt_spawn,step_state,random_fraction
from arika_menu_strip_preview import animated_svg
from menu_strip_oracle import c_strip_oracle,bits
from test_arika_menu_tiles import c_tile_oracle


class c_companion_oracle(c_strip_oracle):
    def __init__(self,kernel,template=0,randoms=(0,0)):
        code=dict(draw_address=kernel['spawn_address'],draw_words=kernel['spawn_words'],
                  clock_address=kernel['update_address'],clock_words=kernel['update_words'])
        super().__init__(code,[0,0,1,1],0,0,1,1,0,[0,0])
        self.m_registers[4]=0x1000;self.m_registers[5]=0x1000;self.m_registers[6]=template
        self.m_registers[28]=kernel['global_pointer'];self.write_int(0x1000,0x3000,4)
        self.write_int(0x3024,0xf00024,4)
        for record in kernel['templates']:
            self.write(record['address'],struct.pack('<4h5f',*record['uv_xywh'],record['depth'],record['y_base'],record['y_span'],record['speed_base'],record['speed_span']))
        values=iter(randoms)
        def rng(machine):machine.m_registers[2]=next(values)
        self.m_direct_stubs={0x374de0:{2:0x9000},0x3725e0:{2:0xa000},0x2fd8f0:{},0x190450:rng}
        self.m_indirect_stubs[0xf00024]=lambda machine:machine.write_float(0x1018,0)


class MenuCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        cls.kernel=cls.report['shared_companions']

    def test_192_spawn_cases_match_native(self):
        rng=random.Random(376790)
        for template in self.kernel['templates']:
            for _ in range(64):
                values=[rng.randrange(0x80000000) for _ in range(2)]
                machine=c_companion_oracle(self.kernel,template['index'],values);machine.run(self.kernel['spawn_address'])
                slot=spawn_slot(template,*values)
                for name,offset in [('x',96),('y',100),('speed',104),('depth',24)]:
                    self.assertEqual(bits(slot[name]),machine.read_int(0x1000+offset,4))
                self.assertEqual(machine.read_int(0x106c,4),1)
                self.assertEqual(machine.m_rect,slot['uv_xywh'])

    def test_134_updates_match_native(self):
        rng=random.Random(3768)
        cases=[(True,x,.5) for x in (-240,-239.5,-239,-241,0,576)]
        cases.extend((bool(rng.randrange(2)),rng.randint(-500,600)/2,rng.randint(0,10)/2) for _ in range(128))
        for active,x,speed in cases:
            machine=c_companion_oracle(self.kernel)
            machine.write_float(0x1060,x);machine.write_float(0x1064,12);machine.write_float(0x1068,speed)
            machine.write_float(0x1018,86);machine.write_int(0x106c,int(active),4)
            for address,value in zip(self.kernel['reset_position_addresses'],[11,22]):machine.write_float(address,value)
            machine.run(self.kernel['update_address'])
            slot=dict(active=active,x=x,y=12,speed=speed,depth=86,template=0,uv_xywh=[0,0,1,1])
            actual=update_slot(slot,[11,22])
            self.assertEqual(actual['active'],bool(machine.read_int(0x106c,4)))
            for name,offset in [('x',96),('y',100),('speed',104),('depth',24)]:self.assertEqual(bits(actual[name]),machine.read_int(0x1000+offset,4))

    def test_128_full_pool_event_timer_cases_match_native(self):
        rng=random.Random(3761)
        for _ in range(128):
            phase=rng.randint(0,4096)/2;timer=rng.choice([-1,0,.5,1,2,100]);value=rng.randrange(0x80000000)
            machine=c_tile_oracle(self.report['tile_scroll_kernel'],phase,[0,320],[0,0],[0,384,512,128],85)
            machine.write_float(0x1084,timer)
            gp=self.kernel['global_pointer'];machine.write_float(gp-19784,90);machine.write_float(gp-19780,120)
            machine.m_direct_stubs.update({0x3766c0:{},0x190450:{2:value}})
            machine.run(self.report['tile_scroll_kernel']['clock_address'])
            state=dict(slots=[dict(active=True,x=0,y=0,speed=0) for _ in range(10)],timer=timer,phase=phase)
            draws=[]
            def draw(role):draws.append(role);return value
            step_state(state,self.kernel['templates'],draw)
            self.assertEqual(bits(state['timer']),machine.read_int(0x1084,4));self.assertEqual(bits(state['phase']),machine.read_int(0x1078,4))
            self.assertEqual(len(draws),machine.m_direct_calls.count(0x190450))

    def test_first_free_slot_and_full_pool_random_consumption(self):
        slots=[dict(active=True) for _ in range(10)];slots[3]=empty_slot();slots[6]=empty_slot()
        values=iter([64,0,32767]);roles=[]
        def draw(role):roles.append(role);return next(values)
        self.assertEqual(attempt_spawn(slots,self.kernel['templates'],draw),3)
        self.assertEqual(slots[3]['template'],2)
        self.assertEqual(roles,['template','height','speed'])
        self.assertFalse(slots[6]['active'])
        self.assertIsNone(attempt_spawn([dict(active=True) for _ in range(10)],self.kernel['templates'],lambda role:self.fail('full pool consumed RNG')))

    def test_retirement_boundary_and_unknown_reset_position(self):
        slot=spawn_slot(self.kernel['templates'][0],0,0);slot.update(x=-239.5,speed=.5)
        self.assertTrue(update_slot(slot)['active'])
        slot['x']=-240;result=update_slot(slot)
        self.assertFalse(result['active']);self.assertIsNone(result['x']);self.assertIsNone(result['y'])

    def test_svg_has_ten_slot_timelines(self):
        trace=dict(preview_kind='companions',frames=[dict(tick=0,quads=[])])
        svg=animated_svg(trace);root=ET.fromstring(svg)
        self.assertEqual(len(root.findall('.//{http://www.w3.org/2000/svg}animate')),20)
        self.assertIn('ten slots',svg)

    def test_invalid_random_inputs_fail(self):
        for value in (-1,0x80000000,1.5):
            with self.assertRaises(ValueError):random_fraction(value)


if __name__=='__main__':unittest.main()
