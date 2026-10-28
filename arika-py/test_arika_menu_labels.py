import json
from pathlib import Path
import unittest
from arika_menu_labels import initialize_label,start_label,exit_label,step_label,draw_label
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class c_label_oracle(c_banner_oracle):
    def __init__(self,report,component,state):
        super().__init__(report['shared_banner']);kernel=report['item_label_animation']
        for function in kernel['functions'].values():self.m_code.update({function['address']+i*4:w for i,w in enumerate(function['words'])})
        for index,key in [(3,'active_start_words'),(7,'active_words')]:self.m_code.update({component['callbacks'][index]+i*4:w for i,w in enumerate(component[key])})
        for i,address in enumerate(component['callbacks']):self.write_int(0x4008+i*4,address,4)
        for curve in (kernel['approach'],kernel['bounce'],kernel['exit']):
            for name in ('times','values'):
                for i,value in enumerate(curve[name]):self.write_float(curve[name+'_address']+i*4,value)
        self.write_int(0x1004,state['phase'],4);self.write_float(0x1008,state['age'])
        for i,value in enumerate(state['offset']):self.write_float(0x100c+i*4,value)
        self.write_float(0x1014,state['depth'])
        for i,value in enumerate(component['direction']):self.write_int(0x1018+i,value,1)
        for i,value in enumerate(kernel['reset_position']):self.write_float(kernel['global_pointer']-10720+i*4,value)


class MenuLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text());cls.kernel=cls.report['item_label_animation']

    def compare(self,state,component,action):
        machine=c_label_oracle(self.report,component,state);machine.run(self.kernel['functions'][action]['address'])
        if action=='start':start_label(state,component,self.kernel)
        elif action=='exit_start':exit_label(state,self.kernel)
        else:step_label(state,component,self.kernel)
        self.assertEqual(state['phase'],machine.read_int(0x1004,4))
        for value,address in [(state['age'],0x1008),(state['offset'][0],0x100c),(state['offset'][1],0x1010),(state['depth'],0x1014)]:self.assertEqual(bits(value),machine.read_int(address,4))

    def test_875_updates_match_native_entry_and_exit(self):
        ages=[0,1,8,9,10,11,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,99998,99999,199998,1000000]
        for component in self.kernel['components']:
            for phase in (0,1,2,4,5):
                for age in ages:
                    state=initialize_label();state.update(phase=phase,age=age,offset=[13,27],depth=45)
                    self.compare(state,component,'update')

    def test_complete_seven_label_sequences_and_geometry(self):
        for component in self.kernel['components']:
            state=initialize_label();self.assertIsNone(draw_label(state,component));self.compare(state,component,'start')
            self.assertEqual(state['offset'],[512*d for d in component['direction']])
            for _ in range(32):self.compare(state,component,'update')
            self.assertEqual((state['phase'],state['age'],state['offset']),(2,0,[0,0]))
            self.assertEqual(draw_label(state,component)['position'],component['base']);self.assertEqual(draw_label(state,component)['depth'],70)
            self.compare(state,component,'exit_start');self.assertEqual(state['depth'],15)
            for _ in range(10):self.compare(state,component,'update')
            self.assertEqual(state['phase'],0);self.assertIsNone(draw_label(state,component))
            self.assertEqual(state['offset'],[512*d for d in component['direction']])

    def test_unreconstructed_emphasis_is_explicit(self):
        state=initialize_label();state['phase']=3
        with self.assertRaises(ValueError):step_label(state,self.kernel['components'][0],self.kernel)


if __name__=='__main__':unittest.main()
