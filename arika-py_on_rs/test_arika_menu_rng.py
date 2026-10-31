import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from arika_menu_rng import c_native_rng,next_rng,MASK64
from menu_rng_oracle import c_rng_oracle


class MenuRngTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).parent
        cls.kernel=json.loads((cls.root/'research/main_menu_map.json').read_text())['native_rng']
        r=random.Random(190450)
        cls.seeds=[0,1,MASK64,0x123456789abcdef0]+[r.getrandbits(64) for _ in range(92)]

    def test_1024_multiply_helper_cases(self):
        machine=c_rng_oracle(self.kernel);r=random.Random(195)
        for _ in range(1024):
            a,b=r.getrandbits(64),r.getrandbits(64)
            self.assertEqual(machine.multiply(a,b),(a*b)&MASK64)

    def test_1536_steps_match_complete_native_rng(self):
        machine=c_rng_oracle(self.kernel)
        for seed in self.seeds:
            generator=c_native_rng(seed);state=seed
            for _ in range(16):
                state,value=machine.step(state)
                self.assertEqual(generator.next(),value);self.assertEqual(generator.m_state,state)

    @unittest.skipUnless(shutil.which('g++'),'g++ required for C++03 comparison')
    def test_cpp03_matches_256_native_results(self):
        machine=c_rng_oracle(self.kernel);lines=[]
        def literal(value):return '((static_cast<uint64_t>(0x%08Xu) << 32) | 0x%08Xu)'%(value>>32,value&0xffffffff)
        for seed in self.seeds[:32]:
            lines.append('{ c_menu_rng rng(%s);'%literal(seed));state=seed
            for _ in range(8):
                state,value=machine.step(state)
                lines+=['assert(rng.next() == %du);'%value,'assert(rng.get_state() == %s);'%literal(state)]
            lines.append('}')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'test.cpp';exe=Path(tmp)/'test'
            source.write_text('#include "arika_menu_rng.h"\n#include <cassert>\nint main()\n{\n'+'\n'.join(lines)+'\n}\n')
            subprocess.run(['g++','-std=c++03','-Wall','-Wextra','-pedantic','-I',str(self.root),str(source),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)

    def test_zero_and_one_state_vectors(self):
        self.assertEqual(next_rng(0),(1,0))
        self.assertEqual(next_rng(1),(0x5851f42d4c957f2e,1481765933))

    def test_invalid_state_rejected(self):
        for state in (-1,MASK64+1,1.5,None):
            with self.assertRaises(ValueError):next_rng(state)
            with self.assertRaises(ValueError):c_native_rng(state)


if __name__=='__main__':unittest.main()
