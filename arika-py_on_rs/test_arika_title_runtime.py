"""Reconstructed title application state and original-ELF tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arika_title_runtime import (
    TITLE_CLASS_NAME, TITLE_RESOURCE, TITLE_CLASS_ADDRESS,
    TITLE_RESOURCE_ADDRESS, TITLE_PHASE_VTABLE, TITLE_SOURCE_RECT,
    TITLE_DEST_RECT, TITLE_DURATION, TITLE_DESTINATION_APP,
    c_title_runtime, verify_title_elf,
)


class TitleRuntimeTests(unittest.TestCase):
    def test_native_identifiers_and_sprite_bounds(self):
        self.assertEqual(TITLE_CLASS_NAME, 'CAppTitleMain')
        self.assertEqual(TITLE_CLASS_ADDRESS, 0x4d7f90)
        self.assertEqual(TITLE_RESOURCE, 'dis/d03/d03t0202')
        self.assertEqual(TITLE_RESOURCE_ADDRESS, 0x4d7fb0)
        self.assertEqual(TITLE_PHASE_VTABLE, 0x4f66f8)
        self.assertEqual(TITLE_SOURCE_RECT, (0, 0, 512, 448))
        self.assertEqual(TITLE_DEST_RECT, (0, 0, 512, 448))
        self.assertEqual(TITLE_DURATION, 4.0)
        self.assertEqual(TITLE_DESTINATION_APP, 6)

    def test_phase_zero_requires_transition_ready(self):
        runtime = c_title_runtime()
        self.assertEqual(runtime.snapshot()['phase'], 0)
        self.assertEqual(runtime.begin(), [
            {'address': '0x2c08a0', 'arguments': [1, 15, -1.0, -1.0]},
        ])
        self.assertEqual(runtime.step(3, True)['snapshot']['phase'], 0)
        self.assertEqual(runtime.step(0, False)['snapshot']['phase'], 1)
        self.assertEqual(runtime.snapshot()['elapsed_seconds'], 3.0)

    def test_phase_one_begins_on_following_update_only(self):
        runtime = c_title_runtime()
        first = runtime.step(5, False)
        self.assertEqual(first['snapshot']['phase'], 1)
        self.assertEqual(first['calls'], [])
        second = runtime.step(0, False)
        self.assertEqual(second['snapshot']['phase'], 2)
        self.assertEqual([item['address'] for item in second['calls']],
                         ['0x2c0c90', '0x2c08a0'])
        self.assertEqual(second['calls'][1]['arguments'],
                         [2, 15, -1.0, -1.0])

    def test_title_threshold_is_strictly_greater_than_four(self):
        runtime = c_title_runtime()
        runtime.step(0, False)
        exact = runtime.step(4.0, False)
        self.assertEqual(exact['snapshot']['elapsed_seconds'], 4.0)
        self.assertEqual(exact['snapshot']['phase'], 1)
        after = runtime.step(1 / 60, False)
        self.assertEqual(after['snapshot']['phase'], 2)
        self.assertGreater(after['snapshot']['elapsed_seconds'], 4.0)

    def test_fade_wait_and_application_six(self):
        runtime = c_title_runtime()
        runtime.step(0, False)
        runtime.step(4.5, False)
        self.assertEqual(runtime.step(0, True)['snapshot']['phase'], 2)
        result = runtime.step(0, False)
        self.assertTrue(result['finished'])
        self.assertEqual(result['calls'], [
            {'address': '0x3dfb00', 'arguments': [6]},
        ])
        with self.assertRaisesRegex(ValueError, 'completion'):
            runtime.step(0, False)

    def test_float32_accumulation_and_single_update_counter(self):
        runtime = c_title_runtime()
        runtime.step(0.1, True)
        runtime.step(0.1, True)
        self.assertEqual(runtime.snapshot()['updates'], 2)
        self.assertNotEqual(runtime.snapshot()['elapsed_seconds'], 0.2)
        self.assertEqual(runtime.snapshot()['elapsed_bits'], 0x3e4ccccd)

    def test_loader_allocation_wait_and_one_sprite(self):
        runtime = c_title_runtime()
        first = runtime.load_step()
        self.assertEqual(first['loader_phase'], 1)
        self.assertFalse(first['ready'])
        self.assertEqual(first['calls'][2]['arguments'], [TITLE_RESOURCE])
        self.assertFalse(runtime.load_step()['ready'])
        self.assertFalse(runtime.load_step(False)['ready'])
        ready = runtime.load_step(True)
        self.assertFalse(ready['ready'])
        self.assertEqual(ready['loader_phase'], 10)
        self.assertEqual(ready['calls'][-2]['arguments'],
                         list(TITLE_SOURCE_RECT))
        self.assertEqual(ready['calls'][-1]['arguments'],
                         list(TITLE_DEST_RECT))
        self.assertTrue(runtime.load_step()['ready'])
        self.assertEqual(runtime.load_step()['calls'], [])

    def test_invalid_input_does_not_advance_state(self):
        runtime = c_title_runtime()
        for dt in (-1, True, float('nan'), float('inf'), '1'):
            with self.subTest(delta=dt), self.assertRaises(ValueError):
                runtime.step(dt, False)
        for busy in (None, 0, 1, 'false'):
            with self.subTest(busy=busy), self.assertRaises(ValueError):
                runtime.step(0, busy)
        self.assertEqual(runtime.snapshot()['updates'], 0)
        with self.assertRaises(ValueError):
            runtime.load_step(1)

    def test_wrong_elf_does_not_claim_provenance(self):
        with self.assertRaisesRegex(ValueError, 'exact EU-beta'):
            verify_title_elf(b'unverified')

    def test_original_elf_oracle_if_supplied(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('user-owned EU-beta ELF is not part of CI')
        report = verify_title_elf(Path(path).read_bytes())
        self.assertEqual(report['resource']['name'], TITLE_RESOURCE)
        self.assertEqual(report['update']['next_application_id'], 6)
        self.assertEqual(report['callbacks']['update'], '0x3f8900')

    def test_original_elf_json_cli_if_supplied(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('user-owned EU-beta ELF is not part of CI')
        with tempfile.TemporaryDirectory() as directory:
            steps = Path(directory) / 'samples.json'
            steps.write_text(json.dumps([
                {'delta_seconds': 0, 'transition_busy': False},
                {'delta_seconds': 4.1, 'transition_busy': False},
                {'delta_seconds': 0, 'transition_busy': True},
                {'delta_seconds': 0, 'transition_busy': False},
            ]), encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name('arika_title_runtime.py')),
                path, '--steps', str(steps),
            ], check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report['format'], 'ARIKA_EU_BETA_TITLE_APPLICATION')
            self.assertTrue(report['steps'][-1]['finished'])


if __name__ == '__main__':
    unittest.main()
