import json
from pathlib import Path
import random
import unittest
from arika_menu_tiles import tile_draw, presentation_tile_geometry
from arika_menu_strips import step_phase
from arika_menu_plain import s16
from menu_strip_oracle import c_strip_oracle,bits


class c_tile_oracle(c_strip_oracle):
    def __init__(self,kernel,phase,base,offset,uv,depth):
        super().__init__(kernel,uv,0,0,1,1,0,[0,0])
        self.m_registers[28]=kernel['global_pointer']
        self.write_float(kernel['base_address'],base[0]);self.write_float(kernel['base_address']+4,base[1])
        self.write_int(0x1010,0x3000,4);self.write_float(0x1028,depth)
        self.write_int(0x1038,s16(uv[0]),2);self.write_int(0x103a,s16(uv[0]+uv[2]),2)
        for address,value in [(0x1078,phase),(0x107c,offset[0]),(0x1080,offset[1]),(0x1084,100)]:self.write_float(address,value)
        self.m_rect=uv
        self.m_direct_stubs={0x3763b0:{2:0x5000},0x376600:{2:0}}


class MenuTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        cls.kernel=report['tile_scroll_kernel'];k=cls.kernel
        cls.cases=[(phase,k['base_position'],[0,0],k['uv_xywh'],k['initial_depth']) for phase in [0,1,1024,2047,2048,2049,-1,4096]]
        rng=random.Random(376290)
        for _ in range(256):
            cls.cases.append((rng.randint(-10,8192)/2,[rng.randint(-100,100)/2,rng.randint(0,400)/2],
                [rng.randint(-100,100)/2,rng.randint(-100,100)/2],
                [rng.randint(0,100),0,rng.choice([1,32,128,512]),128],rng.randint(-10,100)/2))

    def test_264_draw_cases_match_native_helper(self):
        self.assertEqual(len(self.cases),264)
        for args in self.cases:
            machine=c_tile_oracle(self.kernel,*args);machine.run(self.kernel['draw_address'])
            result=tile_draw(*args)
            self.assertEqual(len(machine.m_commands),2)
            for expected,actual in zip(machine.m_commands,result['quads']):
                self.assertEqual([bits(v) for v in expected['position']],[bits(v) for v in actual['position']])
                self.assertEqual(bits(expected['depth']),bits(actual['depth']))
            self.assertEqual([bits(v) for v in result['final_sprite_position']],
                             [machine.read_int(0x1020,4),machine.read_int(0x1024,4)])
            self.assertEqual(machine.m_direct_calls,[0x3763b0,0x376600])

    def test_264_phase_steps_match_native_no_event_path(self):
        for args in self.cases:
            machine=c_tile_oracle(self.kernel,*args);machine.run(self.kernel['clock_address'])
            self.assertEqual(bits(step_phase(args[0],2048)),machine.read_int(0x1078,4))
            self.assertEqual(machine.read_float(0x1084),99)
            self.assertEqual(machine.m_direct_calls,[])

    def test_seam_and_wrap_boundary(self):
        result=tile_draw(2047,[0,320])
        self.assertEqual(result['quads'][0]['position'],[-511.75,320])
        self.assertEqual(result['quads'][1]['position'],[.25,320])
        self.assertEqual(result['final_sprite_position'],[512.25,320])
        self.assertEqual(step_phase(2047,2048),0)
        self.assertEqual(step_phase(4096,2048),2049)

    def test_signed_endpoint_spacing_matches_native(self):
        args=(10,[0,320],[0,0],[32760,0,20,128],85)
        machine=c_tile_oracle(self.kernel,*args);machine.run(self.kernel['draw_address'])
        result=tile_draw(*args)
        self.assertEqual(result['quads'][1]['position'],machine.m_commands[1]['position'])

    def test_square_canvas_cloud_presentation_keeps_native_positions(self):
        native = tile_draw(0, [0, 320])['quads'][0]
        presented = presentation_tile_geometry(native)
        self.assertEqual(native['bounds'], [0.0, 320.0, 512.0, 448.0])
        self.assertEqual(presented['bounds'], [0.0, 384.0, 512.0, 512.0])
        self.assertEqual(presented['position'], [0.0, 384.0])
        self.assertEqual(presented['uv_endpoints'], native['uv_endpoints'])
        self.assertEqual(native['vertices'][0], [0.0, 320.0])

    def test_invalid_inputs_fail(self):
        with self.assertRaises(ValueError):tile_draw(float('nan'),[0,320])
        with self.assertRaises(ValueError):tile_draw(0,[0,320],uv=[0,0,0,128])
        with self.assertRaises(ValueError):tile_draw(0,[0])


if __name__=='__main__':unittest.main()
