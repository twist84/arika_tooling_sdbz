import json
from pathlib import Path
import unittest
from arika_menu_characters import character_offset,trace_characters
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class MenuCharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text());cls.kernel=cls.report['item_character_animation']

    def test_560_native_curve_calls(self):
        ages=list(range(35))+[-1,.5,9.5,10.5,21.5]
        for component in self.kernel['components']:
            for exiting in (False,True):
                for age in ages:
                    machine=c_banner_oracle(self.report['shared_banner'])
                    for f in self.kernel['functions'].values():machine.m_code.update({f['address']+i*4:w for i,w in enumerate(f['words'])})
                    for curve in (self.kernel['approach'],self.kernel['bounce'],self.kernel['exit']):
                        for name in ('times','values'):
                            for i,value in enumerate(curve[name]):machine.write_float(curve[name+'_address']+i*4,value)
                    for i,direction in enumerate(component['direction']):machine.write_int(0x1018+i,direction,1)
                    machine.m_registers[5]=0x100c;machine.m_floats[12]=bits(age)
                    machine.run(self.kernel['functions']['exit' if exiting else 'entry']['address'])
                    result=character_offset(age,component,self.kernel,exiting)
                    self.assertEqual([bits(v) for v in result],[machine.read_int(0x100c+i*4,4) for i in range(2)])
                    self.assertEqual(machine.m_registers[2],int(age>=(10 if exiting else 22)))

    def test_trace_settled_pose_and_exit_visibility(self):
        trace=trace_characters(self.report)
        self.assertEqual([c['direction'] for c in self.kernel['components']],[[1,1],[0,1],[-1,0],[0,1],[1,0],[1,1],[0,-1]])
        for item,c in enumerate(self.report['composite_layout']['composites']):
            for actual,part in zip(trace['frames'][70]['characters'][item],c['parts']):
                self.assertEqual(actual['geometry']['vertices'],part['zero_offset_pose']['vertices'])
                self.assertEqual(actual['geometry']['depth'],part['zero_offset_pose']['position'][2]+45)
            self.assertTrue(trace['frames'][129]['characters'][item]);self.assertEqual(trace['frames'][130]['characters'][item],[])


if __name__=='__main__':unittest.main()
