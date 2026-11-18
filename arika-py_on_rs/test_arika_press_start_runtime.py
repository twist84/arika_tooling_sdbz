"""EU-beta native Press Start (app ID 3) lifecycle and ELF provenance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arika_press_start_runtime import (
    PRESS_START_APP_ID, PRESS_START_CONSTRUCTOR, PRESS_START_UPDATE,
    PRESS_START_DRAW, PRESS_START_IDLE_SECONDS, PRESS_START_ONE_SHOT_SECONDS,
    PRESS_START_BUTTON_BIT, PRESS_START_ACCEPT_APP_ID,
    PRESS_START_ATTRACT_APP_ID, PRESS_START_RESOURCE_GROUPS,
    PRESS_START_WORDS, PHASE_WAIT_FOR_START, PHASE_START_TRANSITION,
    PHASE_START_WAIT, PHASE_ATTRACT_WAIT, c_press_start_runtime,
    verify_press_start_elf,
)
from arika_app_registry import resolve_app


class PressStartNativeTests(unittest.TestCase):
    def test_separate_title_application_has_original_vtable(self):
        self.assertEqual(PRESS_START_APP_ID, 3)
        self.assertEqual(PRESS_START_CONSTRUCTOR, 0x3f7150)
        self.assertEqual(PRESS_START_UPDATE, 0x3f76a0)
        self.assertEqual(PRESS_START_DRAW, 0x3f7aa0)
        self.assertEqual(PRESS_START_BUTTON_BIT, 0x10)
        self.assertEqual(PRESS_START_IDLE_SECONDS, 20.0)
        self.assertEqual(PRESS_START_ONE_SHOT_SECONDS, 1.0)
        self.assertEqual(PRESS_START_ACCEPT_APP_ID, 42)
        self.assertEqual(PRESS_START_ATTRACT_APP_ID, 6)
        self.assertEqual(resolve_app(3)['class_name'], 'CAppTitleMain')
        self.assertNotEqual(resolve_app(2)['constructor'],
                            resolve_app(3)['constructor'])
        self.assertNotEqual(resolve_app(2)['factory'],
                            resolve_app(3)['factory'])

    def test_begin_and_initial_reset(self):
        native = c_press_start_runtime()
        self.assertEqual(native.begin(), [
            {'address': '0x3eb860', 'arguments': [0], 'executed': False},
        ])
        initial = native.snapshot()
        self.assertEqual(initial['phase'], PHASE_WAIT_FOR_START)
        self.assertEqual(initial['elapsed_seconds'], 0.0)
        self.assertFalse(initial['one_shot'])
        self.assertEqual(initial['destination_id'], None)
        self.assertFalse(initial['finished'])

    def test_start_controller_zero_then_native_two_step_fade(self):
        native = c_press_start_runtime()
        input_result = native.step(0.1, controller0=0x10)
        self.assertEqual(input_result['snapshot']['phase'],
                         PHASE_START_TRANSITION)
        self.assertFalse(input_result['finished'])
        self.assertEqual(input_result['calls'][1]['address'], '0x3eb040')
        self.assertEqual(input_result['calls'][1]['arguments'], [0, 1])
        self.assertNotIn('0x3dfb00', [c['address'] for c in input_result['calls']])
        fade = native.step(0.0)
        self.assertEqual(fade['snapshot']['phase'], PHASE_START_WAIT)
        self.assertEqual(
            [call['address'] for call in fade['calls']][-3:],
            ['0x2c0c90', '0x2c08a0', '0x2c08a0'])
        self.assertEqual(fade['calls'][-1]['arguments'], [2, 3, 0.0, -1.0])
        self.assertFalse(native.step(0, transition_busy=True)['finished'])
        final = native.step(0, transition_busy=False)
        self.assertTrue(final['finished'])
        self.assertEqual(final['snapshot']['destination_id'], 42)
        self.assertEqual(final['calls'][-1]['address'], '0x3dfb00')
        self.assertEqual(final['calls'][-1]['arguments'], [42])
        with self.assertRaisesRegex(ValueError, 'already completed'):
            native.step(0)

    def test_start_controller_one_requires_independent_eligibility(self):
        native = c_press_start_runtime()
        rejected = native.step(0.1, controller0=0x10, controller0_ready=False,
                               controller1=0x10, controller1_ready=False)
        self.assertEqual(rejected['snapshot']['phase'], PHASE_WAIT_FOR_START)
        accepted = native.step(0, controller0=0x10, controller0_ready=False,
                               controller1=0x10, controller1_ready=True)
        self.assertEqual(accepted['snapshot']['phase'],
                         PHASE_START_TRANSITION)
        self.assertEqual(next(c for c in accepted['calls']
                              if c['address']=='0x3eb040')['arguments'],
                         [1, 1])

    def test_controller_zero_precedes_second_controller(self):
        native = c_press_start_runtime()
        event = native.step(0, controller0=0x10, controller1=0x10)
        self.assertEqual(event['snapshot']['phase'], PHASE_START_TRANSITION)
        self.assertEqual(next(c for c in event['calls']
                              if c['address']=='0x3eb040')['arguments'],
                         [0, 1])

    def test_one_shot_callback_runs_once_after_one_second(self):
        native = c_press_start_runtime()
        first = native.step(0.9)
        self.assertFalse(first['snapshot']['one_shot'])
        self.assertNotIn('0x2fc840', [c['address'] for c in first['calls']])
        one = native.step(0.1)
        self.assertTrue(one['snapshot']['one_shot'])
        self.assertEqual(one['snapshot']['elapsed_seconds'], 1.0)
        self.assertEqual([c['address'] for c in one['calls']].count('0x2fc840'),
                         1)
        another = native.step(5)
        self.assertNotIn('0x2fc840', [c['address'] for c in another['calls']])

    def test_attract_timeout_is_twenty_not_four_seconds(self):
        native = c_press_start_runtime()
        before = native.step(19.999)
        self.assertEqual(before['snapshot']['phase'], PHASE_WAIT_FOR_START)
        at = native.step(0.001)
        self.assertEqual(at['snapshot']['phase'], PHASE_ATTRACT_WAIT)
        self.assertFalse(at['finished'])
        self.assertEqual(at['calls'][-1]['arguments'], [2, 15, -1.0, -1.0])
        blocked = native.step(0, transition_busy=True)
        self.assertFalse(blocked['finished'])
        after = native.step(0, transition_busy=False)
        self.assertTrue(after['finished'])
        self.assertEqual(after['snapshot']['destination_id'], 6)
        self.assertEqual([x['address'] for x in after['calls']][-2:],
                         ['0x3e0b10', '0x3dfb00'])
        self.assertEqual(after['calls'][-1]['arguments'], [6])

    def test_idle_helper_resets_timer_and_prevents_attract_handoff(self):
        native = c_press_start_runtime()
        reset = native.step(20, idle_reset=True)
        self.assertEqual(reset['snapshot']['elapsed_seconds'], 0)
        self.assertEqual(reset['snapshot']['phase'], 0)
        after = native.step(19)
        self.assertEqual(after['snapshot']['phase'], 0)
        self.assertEqual(after['snapshot']['elapsed_seconds'], 19)

    def test_start_has_priority_over_eligible_idle_timeout(self):
        native = c_press_start_runtime()
        result = native.step(25, controller1=0x10, idle_reset=False)
        self.assertEqual(result['snapshot']['phase'], PHASE_START_TRANSITION)
        self.assertEqual(result['snapshot']['elapsed_seconds'], 25.0)
        self.assertNotIn('0x2afd30', [c['address'] for c in result['calls']])

    def test_loader_tracks_native_groups_and_all_four_wait_stages(self):
        native = c_press_start_runtime()
        self.assertEqual(PRESS_START_RESOURCE_GROUPS,
                         (2, 3, 4, 5, 7, 8, 10, 11, 15))
        zero = native.load_step()
        self.assertEqual(zero['snapshot']['loader_phase'], 1)
        self.assertFalse(zero['ready'])
        self.assertEqual([c['arguments'][0] for c in zero['calls'][2:]],
                         list(PRESS_START_RESOURCE_GROUPS))
        self.assertEqual(native.load_step(False)['snapshot']['loader_phase'], 1)
        self.assertEqual(native.load_step(True)['snapshot']['loader_phase'], 2)
        self.assertEqual(native.load_step(stage_ready=False)
                         ['snapshot']['loader_phase'], 2)
        self.assertEqual(native.load_step(stage_ready=True)
                         ['snapshot']['loader_phase'], 3)
        self.assertEqual(native.load_step(sprite_ready=False)
                         ['snapshot']['loader_phase'], 3)
        prep = native.load_step(sprite_ready=True)
        self.assertEqual(prep['snapshot']['loader_phase'], 4)
        self.assertFalse(prep['ready'])
        ready = native.load_step()
        self.assertTrue(ready['ready'])
        self.assertEqual(ready['snapshot']['loader_phase'], 0)
        self.assertEqual(ready['calls'][0]['address'], '0x2c08a0')

    def test_wrong_or_untrusted_observations_are_rejected(self):
        native = c_press_start_runtime()
        for dt in (-1, True, None, '1', float('nan'), float('inf')):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                native.step(dt)
        for word in (True, -1, 65536, '16'):
            with self.subTest(word=word), self.assertRaises(ValueError):
                native.step(0, controller0=word)
        for value in (0, 1, None, 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                native.step(0, transition_busy=value)
        with self.assertRaises(ValueError):
            native.load_step(group_ready=1)
        self.assertEqual(native.snapshot()['updates'], 0)

    def test_exact_eu_beta_elf_and_optional_json_cli(self):
        self.assertGreater(len(PRESS_START_WORDS), 35)
        with self.assertRaisesRegex(ValueError, 'exact'):
            verify_press_start_elf(b'wrong region')
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('original EU-beta executable not bundled with CI')
        report = verify_press_start_elf(Path(path).read_bytes())
        self.assertEqual(report['app_id'], 3)
        self.assertEqual(report['callbacks']['update'], '0x3f76a0')
        with tempfile.TemporaryDirectory() as directory:
            steps = Path(directory) / 'steps.json'
            steps.write_text(json.dumps([
                {'delta_seconds': 0},
                {'delta_seconds': 20.0},
                {'delta_seconds': 0, 'transition_busy': False},
            ]), encoding='utf-8')
            completed = subprocess.run([
                sys.executable,
                str(Path(__file__).with_name('arika_press_start_runtime.py')),
                path, '--steps', str(steps),
            ], capture_output=True, text=True, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result['steps'][-1]['snapshot']['destination_id'], 6)


if __name__ == '__main__':
    unittest.main()
