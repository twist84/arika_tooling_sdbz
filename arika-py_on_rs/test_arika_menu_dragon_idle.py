import json
from pathlib import Path
import random
import unittest
from arika_menu_idle import step_dragon_idle
from arika_menu_banner import sample_curve
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class MenuDragonIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text());cls.c=next(c for c in cls.report['character_idle']['components'] if c['item']==3)

    def test_600_native_callback_cases_with_controlled_trig(self):
        rng=random.Random(0x380450);c=self.c
        ages=list(range(480))+[480,481,960,100000]+[rng.uniform(0,1440) for _ in range(116)]
        for age in ages:
            cosines=[rng.uniform(-1,1) for _ in range(2)];sines=[rng.uniform(-1,1) for _ in range(2)];angles=[]
            machine=c_banner_oracle(self.report['shared_banner']);machine.m_code.update({c['address']+i*4:w for i,w in enumerate(c['words'])})
            machine.write_float(0x1008,age);machine.write_int(c['count_address'],2,1);machine.write_int(c['sway_count_address'],5,1)
            for address,radius in zip(c['radius_addresses'],c['radii']):machine.write_float(address,radius)
            for i,target in enumerate(c['jump_table']):machine.write_int(c['jump_table_address']+i*4,target,4)
            for curve in (c['curve'],c['sway_curve']):
                for name in ('times','values'):
                    for i,value in enumerate(curve[name]):machine.write_float(curve[name+'_address']+i*4,value)
            def trig(values):
                stream=iter(values)
                def stub(m):angles.append(m.m_floats[12]);m.m_floats[0]=bits(next(stream))
                return stub
            machine.m_direct_stubs[c['cosine_address']]=trig(cosines);machine.m_direct_stubs[c['sine_address']]=trig(sines)
            machine.run(c['address']);cs=iter(cosines);ss=iter(sines)
            new_age,offsets=step_dragon_idle(age,c,lambda a:next(cs),lambda a:next(ss))
            self.assertEqual(bits(new_age),machine.read_int(0x1008,4));self.assertEqual(angles,[bits(sample_curve(c['curve'],new_age))]*4)
            for i,offset in enumerate(offsets):self.assertEqual([bits(v) for v in offset],[machine.read_int(0x1000+c['part_offset']+i*8+j*4,4) for j in range(2)])

    def test_host_trig_radii_sway_and_wrap(self):
        age,parts=step_dragon_idle(119,self.c)
        self.assertEqual(age,120);self.assertEqual(len(parts),8)
        for actual,expected in zip(parts[0],[15,-13]):self.assertAlmostEqual(actual,expected,places=4)
        for actual,expected in zip(parts[2],[10,10]):self.assertAlmostEqual(actual,expected,places=4)
        self.assertEqual(step_dragon_idle(479,self.c)[0],0)
        self.assertTrue(all(v==0 for p in step_dragon_idle(479,self.c)[1] for v in p))


if __name__=='__main__':unittest.main()
