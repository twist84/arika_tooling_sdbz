import json
from pathlib import Path
import unittest
from arika_menu_small import initialize_small,start_small,stop_small,step_small,entry_offset,draw_small
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class c_small_oracle(c_banner_oracle):
    def __init__(self,report,component,state):
        super().__init__(report['shared_banner']);kernel=report['shared_small_animation']
        for function in kernel['functions'].values():self.m_code.update({function['address']+i*4:w for i,w in enumerate(function['words'])})
        for i,callback in enumerate(component['callbacks']):self.write_int(0x4008+i*4,callback,4)
        for index in (3,7):
            address=component['callbacks'][index]
            self.m_code.update({address:0x03e00008,address+4:0 if index==3 else 0x0000102d})
        for curve in (kernel['approach'],kernel['bounce']):
            for name in ('times','values'):
                for i,v in enumerate(curve[name]):self.write_float(curve[name+'_address']+i*4,v)
        self.write_int(0x1004,state['phase'],4);self.write_float(0x1008,state['age'])
        for i,v in enumerate(state['offset']):self.write_float(0x1070+i*4,v)
        for i,v in enumerate(component['direction']):self.write_int(0x1078+i,v,1)
        gp=kernel['global_pointer']
        for i,v in enumerate(kernel['reset_position']):self.write_float(gp-10720+i*4,v)


class MenuSmallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text());cls.kernel=cls.report['shared_small_animation']

    def compare(self,state,component,action):
        machine=c_small_oracle(self.report,component,state)
        machine.run(self.kernel['functions'][action]['address'])
        if action=='start':start_small(state,component,self.kernel)
        elif action=='stop':stop_small(state)
        else:step_small(state,component,self.kernel)
        self.assertEqual(state['phase'],machine.read_int(0x1004,4))
        self.assertEqual(bits(state['age']),machine.read_int(0x1008,4))
        for i,v in enumerate(state['offset']):self.assertEqual(bits(v),machine.read_int(0x1070+i*4,4))

    def test_1050_updates_match_native_curves_and_dispatch(self):
        count=0
        for component in self.kernel['components']:
            for phase in (0,1,2,3,4,5):
                for age in list(range(20))+[99998,99999,100000,199998,1000000]:
                    state=initialize_small();state.update(phase=phase,age=age,offset=[13,27])
                    self.compare(state,component,'update');count+=1
        self.assertEqual(count,1050)

    def test_seven_complete_entry_start_stop_sequences(self):
        for component in self.kernel['components']:
            state=initialize_small();self.assertIsNone(draw_small(state,component))
            self.compare(state,component,'start')
            self.assertEqual(state['offset'],[256*d for d in component['direction']])
            for _ in range(17):self.compare(state,component,'update')
            self.assertEqual((state['phase'],state['age'],state['offset']),(2,17,[0,0]))
            geometry=draw_small(state,component);self.assertEqual(geometry['position'],component['base'])
            self.compare(state,component,'update');self.assertEqual(state['phase'],2)
            self.compare(state,component,'stop');self.assertEqual(state['phase'],4)
            self.compare(state,component,'update');self.assertEqual(state['phase'],0)

    def test_direction_and_bounce_samples(self):
        self.assertEqual([c['direction'] for c in self.kernel['components']],[[1,0],[1,1],[-1,-1],[1,-1],[-1,0],[-1,1],[0,1]])
        component=self.kernel['components'][1]
        for age,value in [(0,256),(5,0),(6,3),(7,6),(9,0),(11,4),(15,2),(17,0)]:
            self.assertEqual(entry_offset(age,component,self.kernel),[value,value])


if __name__=='__main__':unittest.main()
