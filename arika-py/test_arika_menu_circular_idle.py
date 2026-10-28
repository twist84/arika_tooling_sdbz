import json
from pathlib import Path
import random
import unittest
from arika_menu_idle import step_circular_idle
from arika_menu_banner import sample_curve
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class MenuCircularIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text());cls.c=next(c for c in cls.report['character_idle']['components'] if c['item']==6)

    def test_400_native_callback_cases_with_controlled_trig(self):
        rng=random.Random(0x37fc00);c=self.c
        ages=list(range(240))+[rng.uniform(0,720) for _ in range(160)]
        for age in ages:
            cos_value=rng.uniform(-1,1);sin_value=rng.uniform(-1,1);angles=[]
            machine=c_banner_oracle(self.report['shared_banner']);machine.m_code.update({c['address']+i*4:w for i,w in enumerate(c['words'])})
            machine.write_float(0x1008,age);machine.write_int(c['count_address'],2,1);machine.write_float(c['radius_address'],c['radius'])
            for name in ('times','values'):
                for i,value in enumerate(c['curve'][name]):machine.write_float(c['curve'][name+'_address']+i*4,value)
            def trig(value):
                def stub(m):angles.append(m.m_floats[12]);m.m_floats[0]=bits(value)
                return stub
            machine.m_direct_stubs[c['cosine_address']]=trig(cos_value);machine.m_direct_stubs[c['sine_address']]=trig(sin_value)
            machine.run(c['address']);new_age,offsets=step_circular_idle(age,c,lambda a:cos_value,lambda a:sin_value)
            self.assertEqual(bits(new_age),machine.read_int(0x1008,4))
            self.assertEqual(angles,[bits(sample_curve(c['curve'],new_age))]*2)
            for i,offset in enumerate(offsets):self.assertEqual([bits(v) for v in offset],[machine.read_int(0x1000+c['part_offset']+i*8+j*4,4) for j in range(2)])

    def test_host_trig_quadrants_and_full_cycle(self):
        for previous,expected in [(239,[0,0]),(59,[5,5]),(119,[10,0]),(179,[5,-5])]:
            age,parts=step_circular_idle(previous,self.c)
            self.assertEqual(parts[0],parts[1])
            for actual,value in zip(parts[0],expected):self.assertAlmostEqual(actual,value,places=5)


if __name__=='__main__':unittest.main()
