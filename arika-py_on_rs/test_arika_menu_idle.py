import json
from pathlib import Path
import random
import unittest
from arika_menu_idle import step_idle
from arika_menu_characters import trace_characters
from arika_menu_layout import f32
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class MenuIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())

    def test_840_native_idle_updates(self):
        rng=random.Random(0x37ffe0)
        for component in self.report['character_idle']['components']:
            if component.get('kind') is not None:continue
            curve=component['curve'];period=curve['times'][-1]
            ages=[0,1,period/2-1,period/2,period-2,period-1,period,period+1,period*2,100000]+[rng.uniform(0,period*2) for _ in range(200)]
            for age in ages:
                machine=c_banner_oracle(self.report['shared_banner'])
                machine.m_code.update({component['address']+i*4:w for i,w in enumerate(component['words'])})
                machine.write_int(component['count_address'],3,1);machine.write_float(0x1008,age)
                for i,target in enumerate(component['jump_table']):machine.write_int(component['jump_table_address']+i*4,target,4)
                for name in ('times','values'):
                    for i,v in enumerate(curve[name]):machine.write_float(curve[name+'_address']+i*4,v)
                machine.run(component['address']);actual_age,offsets=step_idle(age,component)
                self.assertEqual(bits(actual_age),machine.read_int(0x1008,4))
                for i,offset in enumerate(offsets):
                    self.assertEqual([bits(v) for v in offset],[machine.read_int(0x1000+component['part_offset']+i*8+j*4,4) for j in range(2)])

    def test_trace_idle_activation_and_exit_preservation(self):
        static=trace_characters(self.report);animated=trace_characters(self.report,idle=True)
        self.assertEqual(animated['frames'][22],static['frames'][22])
        for item in range(7):self.assertNotEqual(animated['frames'][70]['characters'][item],static['frames'][70]['characters'][item])
        self.assertEqual(animated['frames'][130]['characters'],[[]]*7)

    def test_versus_relative_part_weights_and_wrap(self):
        component=next(c for c in self.report['character_idle']['components'] if c['item']==2)
        age,parts=step_idle(59,component)
        self.assertEqual(age,60);self.assertEqual(len(parts),9)
        self.assertEqual(parts[0],[f32(f32(-.3)*4),3]);self.assertEqual(parts[4],[1,2]);self.assertEqual(parts[6],[f32(f32(-.2)*4),2])
        self.assertEqual(step_idle(119,component)[0],0)


if __name__=='__main__':unittest.main()
