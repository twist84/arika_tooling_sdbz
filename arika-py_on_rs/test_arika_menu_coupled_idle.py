import json
from pathlib import Path
import random
import unittest
from arika_menu_idle import step_coupled_idle
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class MenuCoupledIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        cls.component=next(c for c in cls.report['character_idle']['components'] if c['item']==5)

    def test_400_native_coupled_idle_updates(self):
        rng=random.Random(0x37f7f0);c=self.component
        cases=[(0,s) for s in (0,9,10,19,20,29,30,39,40,638,639,640,641,1280)]
        cases += [(p,639) for p in (0,79,80,158,159,160,161,320,100000)]
        cases += [(rng.uniform(0,600),rng.uniform(0,2000)) for _ in range(400-len(cases))]
        for age,secondary in cases:
            machine=c_banner_oracle(self.report['shared_banner']);machine.m_code.update({c['address']+i*4:w for i,w in enumerate(c['words'])})
            machine.write_float(0x1008,age);machine.write_float(0x1000+c['secondary_age_offset'],secondary)
            machine.write_int(c['count_address'],3,1);machine.write_int(c['secondary_count_address'],6,1)
            machine.write_float(self.report['character_idle']['global_pointer']-19232,c['secondary_y_factor'])
            for curve in (c['curve'],c['secondary_curve']):
                for name in ('times','values'):
                    for i,value in enumerate(curve[name]):machine.write_float(curve[name+'_address']+i*4,value)
            machine.run(c['address']);new_age,new_secondary,offsets=step_coupled_idle(age,secondary,c)
            self.assertEqual(bits(new_age),machine.read_int(0x1008,4));self.assertEqual(bits(new_secondary),machine.read_int(0x1000+c['secondary_age_offset'],4))
            for i,offset in enumerate(offsets):self.assertEqual([bits(v) for v in offset],[machine.read_int(0x1000+c['part_offset']+i*8+j*4,4) for j in range(2)])


if __name__=='__main__':unittest.main()
