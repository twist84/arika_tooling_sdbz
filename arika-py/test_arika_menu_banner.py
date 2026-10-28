import json
from pathlib import Path
import random
import unittest
from arika_menu_banner import sample_curve,initialize_banner,start_banner,exit_banner,step_banner,draw_banner
from menu_strip_oracle import c_strip_oracle,bits


class c_banner_oracle(c_strip_oracle):
    def __init__(self,kernel):
        super().__init__(dict(draw_address=0,draw_words=[],clock_address=0,clock_words=[]),[0,0,1,1],0,0,1,1,0,[0,0])
        for f in kernel['functions'].values():self.m_code.update({f['address']+i*4:w for i,w in enumerate(f['words'])})
        self.m_registers[28]=kernel['global_pointer'];self.write_int(0x1000,0x4000,4)
        for i,a in enumerate(kernel['callbacks']):self.write_int(0x4008+i*4,a,4)
        for curve in kernel['curves'].values():
            for key in ('values','times'):
                for i,v in enumerate(curve[key]):self.write_float(curve[key+'_address']+i*4,v)
            self.write_int(curve['count_address'],2,1)


class MenuBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kernel=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())['shared_banner']

    def test_520_curve_samples_match_native_interpolator(self):
        rng=random.Random(0x2c2c10)
        for curve in self.kernel['curves'].values():
            times=[-1,0,.5,1,4.999,5,9.999,10,11,100]+[rng.uniform(-5,20) for _ in range(250)]
            for time in times:
                machine=c_banner_oracle(self.kernel);machine.m_registers[4]=curve['values_address']
                machine.m_registers[5]=curve['times_address'];machine.m_registers[6]=2;machine.m_floats[12]=bits(time)
                machine.run(self.kernel['functions']['interpolate']['address'])
                self.assertEqual(bits(sample_curve(curve,time)),machine.m_floats[0])

    def test_180_owner_updates_match_native_with_real_curve_calls(self):
        for phase in (0,1,2,3,4):
            for age in (-1,0,1,3,4,8,9,10,99998,99999,199998,1000000):
                for x in (-512,0,40):
                    state=initialize_banner(self.kernel);state.update(phase=phase,age=age);state['offset']=[x,13]
                    machine=c_banner_oracle(self.kernel);machine.write_int(0x1070,phase,4)
                    for a,v in [(0x1074,age),(0x1078,x),(0x107c,13)]:machine.write_float(a,v)
                    machine.run(self.kernel['functions']['update']['address']);step_banner(state,self.kernel)
                    self.assertEqual(state['phase'],machine.read_int(0x1070,4))
                    for a,v in [(0x1074,state['age']),(0x1078,state['offset'][0]),(0x107c,state['offset'][1])]:self.assertEqual(bits(v),machine.read_int(a,4))

    def test_start_exit_and_geometry(self):
        state=initialize_banner(self.kernel)
        self.assertEqual(state['offset'],[-512,0]);start_banner(state)
        for _ in range(10):step_banner(state,self.kernel)
        self.assertEqual((state['phase'],state['offset']),(2,[0,0]))
        self.assertEqual(draw_banner(state,self.kernel)['position'],[0,16])
        exit_banner(state)
        for _ in range(5):step_banner(state,self.kernel)
        self.assertEqual((state['phase'],state['offset']),(0,[-256,0]))
        for name,fn in [('start',start_banner),('request_exit',exit_banner)]:
            machine=c_banner_oracle(self.kernel);machine.write_float(0x1074,77);machine.write_float(0x1078,12)
            machine.run(self.kernel['functions'][name]['address']);state.update(age=77);state['offset'][0]=12;fn(state)
            self.assertEqual(state['phase'],machine.read_int(0x1070,4));self.assertEqual(machine.read_float(0x1074),0)
            self.assertEqual(machine.read_float(0x1078),12)

    def test_invalid_curves_fail(self):
        for curve,time in [({'times':[0,0],'values':[1,2]},0),({'times':[0,1],'values':[1]},0),({'times':[0,1],'values':[1,2]},float('nan'))]:
            with self.assertRaises(ValueError):sample_curve(curve,time)


if __name__=='__main__':unittest.main()
