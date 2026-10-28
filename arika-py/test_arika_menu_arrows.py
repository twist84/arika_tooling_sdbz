import json
from pathlib import Path
import unittest
from menu_strip_oracle import c_strip_oracle


class MenuArrowTests(unittest.TestCase):
    def test_14_native_conditional_arrow_layouts(self):
        kernel=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())['arrow_baselines']
        for item in kernel['items']:
            for flag in (0,1):
                machine=c_strip_oracle(dict(draw_address=item['address'],draw_words=item['words'],clock_address=0,clock_words=[]),[0,0,1,1],0,0,1,1,0,[0,0])
                machine.m_registers[28]=kernel['global_pointer']
                for variant in item['variants']:
                    for part in variant:
                        for i,value in enumerate(part['base']):machine.write_float(part['position_address']+i*4,value)
                if item['flag_offset'] is not None:machine.write_int(0x1000+item['flag_offset'],flag,1)
                calls=[]
                def record(m):calls.append((m.m_registers[5],[m.read_float(m.m_registers[6]+i*4) for i in range(2)]))
                machine.m_direct_stubs[0x3753a0]=record;machine.run(item['address'])
                self.assertEqual(calls,[(p['direction'],p['base']) for p in item['variants'][flag]])


if __name__=='__main__':unittest.main()
