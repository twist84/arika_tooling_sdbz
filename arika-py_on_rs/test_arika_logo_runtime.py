"""Deterministic CAppLogoMain state machine tests, no copyrighted game data."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from arika_logo_runtime import (
    c_logo_runtime, ELF_SHA256, LOGO_DURATION, LOOP_PAUSE,
    LOOP_PAUSE_BITS, verify_logo_elf,
)


class LogoRuntimeTests(unittest.TestCase):
    def test_elf_constants_and_initialization(self):
        self.assertEqual(LOOP_PAUSE_BITS, 0x3DAAAAAB)
        self.assertEqual(struct.unpack('<I', struct.pack('<f', LOOP_PAUSE))[0],
                         LOOP_PAUSE_BITS)
        self.assertEqual(LOGO_DURATION, 2.0)
        runtime = c_logo_runtime()
        self.assertEqual(runtime.snapshot(), {
            'phase': 0, 'current_logo': 0, 'next_logo': 0,
            'skip_latched': False, 'age_bits': 0,
            'age_seconds': 0.0, 'finished': False, 'updates': 0,
        })
        self.assertEqual(runtime.begin(), [
            {'address': '0x2c0c90', 'arguments': [1]},
            {'address': '0x2c08a0', 'arguments': [1, 60, 1.0, -1.0]},
        ])
        self.assertEqual(runtime.snapshot()['updates'], 0)

    def test_zero_one_two_fallthrough_and_two_second_gate(self):
        runtime = c_logo_runtime()
        first = runtime.step(0.5, audio_busy=False)
        self.assertEqual(first['snapshot']['phase'], 2)
        self.assertEqual(first['snapshot']['age_seconds'], 0.0)
        self.assertEqual(first['snapshot']['next_logo'], 1)
        self.assertEqual(first['calls'], [])
        self.assertEqual(runtime.step(1.5, False)['snapshot']['phase'], 2)
        result = runtime.step(0.5, False)
        self.assertEqual(result['snapshot']['phase'], 3)
        self.assertEqual(result['calls'], [])
        result = runtime.step(0.0, False)
        self.assertEqual(result['snapshot']['phase'], 4)
        self.assertEqual([x['address'] for x in result['calls']],
                         ['0x2c0c90', '0x2c08a0'])
        self.assertEqual(result['calls'][1]['arguments'], [2, 60, -1.0, -1.0])

    def test_audio_busy_holds_phase_one_four_and_ten(self):
        runtime = c_logo_runtime()
        self.assertEqual(runtime.step(3.0, True)['snapshot']['phase'], 1)
        self.assertEqual(runtime.step(5.0, True)['snapshot']['phase'], 1)
        self.assertEqual(runtime.step(0, False)['snapshot']['phase'], 2)
        runtime.step(2.0, True)
        self.assertEqual(runtime.snapshot()['phase'], 3)
        self.assertEqual(runtime.step(0.0, True)['snapshot']['phase'], 4)
        self.assertEqual(runtime.step(42.0, True)['snapshot']['phase'], 4)
        self.assertEqual(runtime.step(1.0, False)['snapshot']['phase'], 5)
        self.assertEqual(runtime.snapshot()['age_seconds'], 0)

    def test_skip_controller_words_both_supported(self):
        for index in (0, 1):
            with self.subTest(controller=index):
                runtime = c_logo_runtime()
                runtime.step(0.0, False)
                words = ({'controller0': 0x10} if index == 0 else
                         {'controller1': 0x10})
                result = runtime.step(0, False, **words)
                self.assertEqual(result['snapshot']['phase'], 3)
                self.assertTrue(result['snapshot']['skip_latched'])
                self.assertEqual(result['calls'], [])
                after = runtime.step(0, False)
                self.assertEqual(after['snapshot']['phase'], 4)
                self.assertEqual(after['calls'], [])

    def test_cycle_0_to_1_to_2_and_finish(self):
        runtime = c_logo_runtime()
        for expected_logo in (0, 1, 2):
            runtime.step(0, False)
            self.assertEqual(runtime.snapshot()['current_logo'], expected_logo)
            self.assertEqual(runtime.snapshot()['phase'], 2)
            # Time expiry is not a button skip.
            result = runtime.step(2, False)
            self.assertEqual(result['snapshot']['phase'], 3)
            self.assertEqual(result['calls'], [])
            self.assertFalse(result['snapshot']['skip_latched'])
            result = runtime.step(0, False)
            if expected_logo == 2:
                self.assertEqual(result['snapshot']['phase'], 10)
                self.assertEqual(result['calls'][0]['arguments'], [0])
                self.assertFalse(result['finished'])
                self.assertFalse(runtime.step(0, True)['finished'])
                self.assertTrue(runtime.step(0, False)['finished'])
            else:
                self.assertEqual(result['snapshot']['phase'], 4)
                self.assertEqual(runtime.step(0, False)['snapshot']['phase'], 5)
                self.assertEqual(runtime.step(LOOP_PAUSE / 2, False)['snapshot']['phase'], 5)
                done = runtime.step(LOOP_PAUSE, False)
                self.assertEqual(done['snapshot']['phase'], 0)
                self.assertEqual(done['calls'][0]['arguments'], [1])
        with self.assertRaises(ValueError):
            runtime.step(0, False)

    def test_final_logo_skip_triggers_additional_callback(self):
        runtime = c_logo_runtime()
        for _ in range(2):
            runtime.step(0, False)
            runtime.step(2, False)
            runtime.step(0, False)
            runtime.step(0, False)
            runtime.step(LOOP_PAUSE, False)
        runtime.step(0, False)
        self.assertEqual(runtime.snapshot()['current_logo'], 2)
        result = runtime.step(0, False, controller0=0x10)
        self.assertEqual(result['snapshot']['phase'], 3)
        self.assertTrue(result['snapshot']['skip_latched'])
        self.assertEqual(result['calls'], [])
        result = runtime.step(0, False)
        self.assertEqual(result['snapshot']['phase'], 10)
        self.assertEqual([x['address'] for x in result['calls']],
                         ['0x2c0c90', '0x2c08a0', '0x3e0b00'])

    def test_float32_and_phase_five_threshold(self):
        runtime = c_logo_runtime()
        runtime.step(0, False)
        runtime.step(2, False)
        runtime.step(0, False)
        runtime.step(0, False)
        self.assertEqual(runtime.snapshot()['phase'], 5)
        runtime.step(LOOP_PAUSE, False)
        self.assertEqual(runtime.snapshot()['phase'], 0)
        runtime.step(0, False)
        runtime.step(0.1, False)
        self.assertEqual(runtime.snapshot()['age_bits'],
                         struct.unpack('<I', struct.pack('<f', 0.1))[0])

    def test_validation_of_inputs(self):
        for delta in (-1, float('nan'), float('inf'), True, '0.1'):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                c_logo_runtime().step(delta, False)
        for busy in (0, 1, 'false', None):
            with self.subTest(busy=busy), self.assertRaises(ValueError):
                c_logo_runtime().step(0, busy)
        for value in (-1, 65536, True, '16'):
            with self.subTest(word=value), self.assertRaises(ValueError):
                c_logo_runtime().step(0, False, controller1=value)
        with self.assertRaises(ValueError):
            verify_logo_elf(b'not a game elf')

    def test_elf_oracle_if_user_elf_available(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if path is None:
            self.skipTest('set SDBZ_EU_BETA_ELF to a local, exact EU-beta ELF')
        self.assertTrue(verify_logo_elf(Path(path).read_bytes()))

    def test_cli_trace(self):
        samples = [
            {'delta_seconds': 0, 'audio_busy': False},
            {'delta_seconds': 2, 'audio_busy': False},
            {'delta_seconds': 0, 'audio_busy': False},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace-input.json'
            path.write_text(json.dumps(samples), encoding='utf-8')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('arika_logo_runtime.py')), str(path)],
                text=True, capture_output=True, check=True)
            output = json.loads(result.stdout)
            self.assertEqual(output['format'], 'ARIKA_EU_BETA_LOGO_TRACE')
            self.assertEqual([sample['snapshot']['phase'] for sample in output['steps']],
                             [2, 3, 4])


if __name__ == '__main__':
    unittest.main()
