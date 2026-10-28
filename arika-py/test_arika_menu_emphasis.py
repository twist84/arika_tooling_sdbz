import json
from pathlib import Path
import math
import random
import unittest
from arika_menu_emphasis import emphasis_offset
from arika_menu_labels import initialize_label,emphasize_label,step_label,trace_labels
from arika_menu_characters import trace_characters
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits,real


class MenuEmphasisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())

    def test_1120_native_helper_cases_with_modulo_stub(self):
        rng=random.Random(0x37e460)
        ages=[-1,0,.5,1,2,3,3.5,4,5,7.5,8,11,14,14.99,15,16]+[rng.uniform(0,25) for _ in range(64)]
        for kind in ('labels','characters'):
            kernel=self.report['item_emphasis']['kernels'][kind]
            components=self.report['item_label_animation' if kind=='labels' else 'item_character_animation']['components']
            for component in components:
                for age in ages:
                    machine=c_banner_oracle(self.report['shared_banner']);machine.m_code.update({kernel['address']+i*4:w for i,w in enumerate(kernel['words'])})
                    for curve in (kernel['wave'],kernel['envelope']):
                        for name in ('times','values'):
                            for i,value in enumerate(curve[name]):machine.write_float(curve[name+'_address']+i*4,value)
                    for i,value in enumerate(component['direction']):machine.write_int(0x1018+i,value,1)
                    machine.write_float(0x1008,age);machine.m_registers[5]=0x100c;machine.m_floats[12]=bits(age)
                    remainders=[]
                    def modulo(m):
                        a,b=real(m.m_floats[12]),real(m.m_floats[13]);remainders.append((a,b));m.m_floats[0]=bits(math.fmod(a,b))
                    machine.m_direct_stubs[0x185e50]=modulo;machine.run(kernel['address'])
                    offsets,done=emphasis_offset(age,component['direction'],kernel,reset_on_completion=kind=='labels')
                    self.assertEqual([bits(v) for v in offsets],[machine.read_int(0x100c+i*4,4) for i in range(2)])
                    self.assertEqual(bool(machine.m_registers[2]),done);self.assertEqual(remainders,[(real(bits(age)),4.0)])

    def test_label_phase_persists_after_envelope_completion(self):
        state=initialize_label();state['depth']=45;kernel=self.report['item_label_animation'];component=kernel['components'][0]
        emphasize_label(state,kernel)
        for _ in range(16):step_label(state,component,kernel,self.report['item_emphasis']['kernels']['labels'])
        self.assertEqual((state['phase'],state['age'],state['offset'],state['depth']),(3,16,[0,0],45))

    def test_authored_trace_shake_and_idle_freeze(self):
        base=trace_characters(self.report,idle=True);shake=trace_characters(self.report,idle=True,emphasis_tick=80)
        self.assertEqual(base['frames'][79],shake['frames'][79]);self.assertNotEqual(base['frames'][82],shake['frames'][82])
        labels=trace_labels(self.report,emphasis_tick=80)
        self.assertEqual(labels['frames'][95]['labels'][0]['phase'],3)
        self.assertEqual(labels['frames'][95]['labels'][0]['offset'],[0,0]);self.assertEqual(labels['frames'][130]['labels'][0]['phase'],0)


if __name__=='__main__':unittest.main()
