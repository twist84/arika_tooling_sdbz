"""Synthetic, original-instruction-gated tests of EU-beta CAppWarning."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arika_warning_runtime import (
    WARNING_RESOURCE, WARNING_OPTIONS, WARNING_LABEL_ADDRESSES,
    WARNING_SOURCE_RECT, WARNING_DEST_RECT,
    PHASE_SELECTION, PHASE_VIDEO_MODE, PHASE_EXIT_WAIT,
    PHASE_TEST_FADE_OUT, PHASE_TEST_WAIT_OUT, PHASE_TEST_WAIT_IN,
    PHASE_TEST_DISPLAY, PHASE_TEST_FADE_BACK,
    PAD_NEXT, PAD_PREVIOUS, PAD_CONFIRM,
    c_warning_runtime, recover_warning_elf,
)


class WarningRuntimeTests(unittest.TestCase):
    def test_embedded_native_labels_are_preserved(self):
        self.assertEqual(WARNING_RESOURCE, 'dis/d03/d03t0801')
        self.assertEqual(WARNING_OPTIONS,
                         (' 50Hz', ' 60Hz', ' TEST', 'To Game'))
        self.assertEqual(WARNING_LABEL_ADDRESSES,
                         (0x4d9248, 0x4d9250, 0x4d9258, 0x4d9260))
        self.assertEqual(WARNING_SOURCE_RECT, (0, 0, 512, 448))
        self.assertEqual(WARNING_DEST_RECT, (0, 0, 512, 448))
        self.assertEqual((PAD_NEXT, PAD_PREVIOUS, PAD_CONFIRM),
                         (2, 1, 128))

    def test_initial_state_begin_and_same_update_gate(self):
        runtime = c_warning_runtime()
        self.assertEqual(runtime.snapshot(), {
            'phase': 0, 'selection': 0, 'choice_text': ' 50Hz',
            'image_visible': False, 'countdown_seconds': 0.0,
            'countdown_bits': 0, 'finished': False, 'updates': 0,
        })
        self.assertEqual(runtime.begin()[1]['arguments'],
                         [1, 15, 0.0, -1.0])
        self.assertEqual(runtime.step(1.0, True)['snapshot']['phase'], 1)
        self.assertEqual(runtime.step(0, True)['snapshot']['phase'], 1)
        self.assertEqual(runtime.step(0, False)['snapshot']['phase'], 2)

    def test_option_move_wrap_and_native_input_priority(self):
        runtime = c_warning_runtime()
        runtime.step(0, False)
        self.assertEqual(runtime.step(0, False, PAD_PREVIOUS)
                         ['snapshot']['selection'], 3)
        self.assertEqual(runtime.step(0, False, PAD_NEXT)
                         ['snapshot']['selection'], 0)
        # 0x2 wins against 0x1 and 0x80; no confirm on this update.
        result = runtime.step(0, False, PAD_NEXT | PAD_PREVIOUS | PAD_CONFIRM)
        self.assertEqual((result['snapshot']['phase'],
                          result['snapshot']['selection']), (2, 1))

    def test_50_and_60_hz_record_side_effects_without_host_changes(self):
        for index, hz, height, mode in ((0, 50.0, 512, 0x36),
                                        (1, 60.0, 448, 0x35)):
            with self.subTest(mode=hz):
                runtime = c_warning_runtime()
                runtime.step(0, False)
                if index:
                    runtime.step(0, False, PAD_NEXT)
                self.assertEqual(runtime.step(0, False, PAD_CONFIRM)
                                 ['snapshot']['phase'], PHASE_VIDEO_MODE)
                result = runtime.step(0, False)
                self.assertEqual(result['snapshot']['phase'], PHASE_SELECTION)
                self.assertEqual(result['events'][0]['address'], '0x1bf560')
                self.assertEqual(result['events'][0]['arguments'], [hz])
                self.assertEqual(result['events'][1]['address'], '0x1998a0')
                self.assertEqual(result['events'][1]['observed'], {
                    'width': 512, 'height': height, 'mode_selector': mode,
                })
                self.assertFalse(result['finished'])

    def _start_test_mode(self):
        runtime = c_warning_runtime()
        runtime.step(0, False)
        runtime.step(0, False, PAD_NEXT)
        runtime.step(0, False, PAD_NEXT)
        self.assertEqual(runtime.snapshot()['selection'], 2)
        runtime.step(0, False, PAD_CONFIRM)
        self.assertEqual(runtime.snapshot()['phase'], PHASE_TEST_FADE_OUT)
        return runtime

    def test_test_screen_fades_and_waits_for_external_gate(self):
        runtime = self._start_test_mode()
        self.assertEqual(runtime.step(0, False)['snapshot']['phase'],
                         PHASE_TEST_WAIT_OUT)
        self.assertEqual(runtime.step(0, True)['snapshot']['phase'],
                         PHASE_TEST_WAIT_OUT)
        shown = runtime.step(0, False)
        self.assertEqual(shown['snapshot']['phase'], PHASE_TEST_WAIT_IN)
        self.assertTrue(shown['snapshot']['image_visible'])
        self.assertEqual(runtime.step(0, True)['snapshot']['phase'],
                         PHASE_TEST_WAIT_IN)
        ready = runtime.step(0, False)
        self.assertEqual(ready['snapshot']['phase'], PHASE_TEST_DISPLAY)
        self.assertEqual(ready['snapshot']['countdown_seconds'], 5.0)

    def test_test_screen_has_strict_negative_five_second_gate(self):
        runtime = self._start_test_mode()
        for _ in range(3):
            runtime.step(0, False)
        self.assertEqual(runtime.snapshot()['phase'], PHASE_TEST_DISPLAY)
        elapsed = runtime.step(5.0, False)
        self.assertEqual(elapsed['snapshot']['phase'], PHASE_TEST_DISPLAY)
        self.assertEqual(elapsed['snapshot']['countdown_seconds'], 0.0)
        finished = runtime.step(1.0 / 60.0, False)
        self.assertEqual(finished['snapshot']['phase'], PHASE_TEST_FADE_BACK)
        self.assertEqual(finished['events'][1]['arguments'],
                         [2, 30, 0.0, -1.0])
        self.assertEqual(runtime.step(0, True)['snapshot']['phase'],
                         PHASE_TEST_FADE_BACK)
        return_to_select = runtime.step(0, False)
        self.assertEqual(return_to_select['snapshot']['phase'], 1)
        self.assertFalse(return_to_select['snapshot']['image_visible'])
        self.assertEqual(runtime.step(0, False)['snapshot']['phase'],
                         PHASE_SELECTION)

    def test_to_game_waits_for_external_completion_signal(self):
        runtime = c_warning_runtime()
        runtime.step(0, False)
        runtime.step(0, False, PAD_PREVIOUS)
        self.assertEqual(runtime.snapshot()['selection'], 3)
        runtime.step(0, False, PAD_CONFIRM)
        self.assertEqual(runtime.snapshot()['phase'], 3)
        start = runtime.step(0, False)
        self.assertEqual(start['snapshot']['phase'], PHASE_EXIT_WAIT)
        self.assertEqual(start['events'][1]['arguments'],
                         [2, 60, -1.0, -1.0])
        self.assertFalse(runtime.step(0, True)['finished'])
        exit_step = runtime.step(0, False)
        self.assertTrue(exit_step['finished'])
        self.assertEqual(exit_step['events'][0]['address'], '0x3dfb00')
        with self.assertRaises(ValueError):
            runtime.step(0, False)

    def test_buttons_outside_selection_do_not_shortcut_waits(self):
        runtime = c_warning_runtime()
        runtime.step(0, True, PAD_CONFIRM)
        self.assertEqual(runtime.snapshot()['phase'], 1)
        runtime.step(0, False)
        runtime.step(0, False, PAD_CONFIRM)
        self.assertEqual(runtime.snapshot()['phase'], PHASE_VIDEO_MODE)
        runtime.step(0, False, PAD_PREVIOUS | PAD_CONFIRM)
        self.assertEqual(runtime.snapshot()['phase'], PHASE_SELECTION)
        self.assertEqual(runtime.snapshot()['selection'], 0)

    def test_inputs_and_wrong_elf_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact EU beta'):
            recover_warning_elf(b'wrong ELF')
        for dt in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(delta=dt), self.assertRaises(ValueError):
                c_warning_runtime().step(dt, False)
        for busy in (0, 1, None, 'false'):
            with self.subTest(busy=busy), self.assertRaises(ValueError):
                c_warning_runtime().step(0, busy)
        for control in (-1, 65536, True, '128'):
            with self.subTest(controller=control), self.assertRaises(ValueError):
                c_warning_runtime().step(0, False, control)

    def test_exact_original_elf_if_provided(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact EU beta ELF supplied only by user')
        report = recover_warning_elf(Path(path).read_bytes())
        self.assertEqual(report['resource']['name'], WARNING_RESOURCE)
        self.assertEqual([item['text'] for item in report['choice_table']],
                         list(WARNING_OPTIONS))

    def test_json_cli_with_original_elf_if_provided(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact EU beta ELF supplied only by user')
        with tempfile.TemporaryDirectory() as directory:
            samples = Path(directory) / 'samples.json'
            samples.write_text(json.dumps([
                {'delta_seconds': 0, 'busy': False},
                {'delta_seconds': 0, 'busy': False, 'controller0': PAD_NEXT},
            ]))
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name('arika_warning_runtime.py')),
                path, '--steps', str(samples),
            ], text=True, capture_output=True, check=True)
            report = json.loads(result.stdout)
            self.assertEqual(report['format'], 'ARIKA_EU_BETA_WARNING_SCREEN')
            self.assertEqual(report['steps'][1]['snapshot']['selection'], 1)


if __name__ == '__main__':
    unittest.main()
