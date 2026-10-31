import json
from pathlib import Path
import random
import unittest
from arika_menu_strips import step_phase,clipped_strip
from menu_strip_oracle import c_strip_oracle,bits


class MenuStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        cls.kernels=cls.report['strip_kernels'];cls.cases=[]
        for group in cls.report['first_components']['groups']:
            if 'scroll_strip' not in group:continue
            strip=group['scroll_strip'];p=strip['parameters']
            for phase in (0,1,p['period']/2,p['period']-1,p['period'],p['period']+1):
                cls.cases.append((strip['uv_xywh'],p['orientation'],p['start'],p['end'],p['period'],phase,[100,50],0,2))
        rng=random.Random(374110)
        for _ in range(256):
            start=rng.randint(-100,100);period=rng.choice([1,3,32,100,2450,3150])
            cls.cases.append(([rng.randint(0,100),rng.randint(0,100),rng.randint(1,512),rng.randint(1,512)],
                rng.randrange(2),start,start+rng.randint(0,600),period,rng.randint(-5,period*2)/2,
                [rng.randint(-600,800)/2,rng.randint(-100,400)/2],rng.randint(-20,20)/2,rng.randint(-10,20)/2))

    def test_280_clipping_cases_match_native_instruction_oracle(self):
        self.assertEqual(len(self.cases),280)
        for args in self.cases:
            machine=c_strip_oracle(self.kernels,*args);machine.run(self.kernels['draw_address'])
            result=clipped_strip(*args)
            self.assertEqual(len(result['commands']),len(machine.m_commands))
            for expected,actual in zip(machine.m_commands,result['commands']):
                self.assertEqual(actual['uv_xywh'],expected['uv_xywh'])
                self.assertEqual([bits(v) for v in actual['position']],[bits(v) for v in expected['position']])
                self.assertEqual(bits(actual['depth']),bits(expected['depth']))
            self.assertEqual(bits(result['final_position']),machine.read_int(0x1030,4))
            self.assertEqual(bits(result['final_depth']),machine.read_int(0x1038,4))

    def test_280_clock_steps_match_native_instruction_oracle(self):
        for args in self.cases:
            machine=c_strip_oracle(self.kernels,*args);machine.run(self.kernels['clock_address'])
            self.assertEqual(bits(step_phase(args[5],args[4])),machine.read_int(0x1018,4))

    def test_clock_subtracts_period_once(self):
        self.assertEqual(step_phase(7,3),5)
        self.assertEqual(step_phase(2,3),0)
        self.assertEqual(step_phase(-1,3),0)

    def test_clipped_source_extent_and_depth(self):
        result=clipped_strip([0,0,10,4],0,2,6,100,0,[0,7],depth=10)
        self.assertEqual(len(result['commands']),1)
        command=result['commands'][0]
        self.assertEqual(command['uv_xywh'],[2,0,5,4])
        self.assertEqual(command['position'],[2,7])
        self.assertEqual(command['depth'],10)
        self.assertEqual(result['final_depth'],12)

    def test_invalid_parameters_fail(self):
        for period in (0,-1,float('nan')):
            with self.assertRaises(ValueError):step_phase(0,period)
        with self.assertRaises(ValueError):clipped_strip([0,0,0,5],0,0,10,10,0,[0,0])
        with self.assertRaises(ValueError):clipped_strip([0,0,5,5],0,10,0,10,0,[0,0])


if __name__=='__main__':unittest.main()
