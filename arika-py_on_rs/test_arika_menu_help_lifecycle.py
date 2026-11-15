"""Synthetic help-owner lifecycle, integration and optional ELF data oracle.

The suite does not use copyrighted game assets or a diagnostic frame clock.
"""
import hashlib
import os
import struct
import unittest
from pathlib import Path

from arika_menu_help_lifecycle import (
    HELP_BOUNCE_OFFSETS, HELP_BOUNCE_TIMES,
    HELP_ENTRY_COMPLETE, HELP_ENTRY_OFFSETS, HELP_ENTRY_TIMES,
    HELP_EXIT_COMPLETE, HELP_EXIT_OFFSETS, HELP_EXIT_TIMES,
    exit_help, help_draw_state, initialize_help, start_help, step_help,
)


class HelpOwnerStateTests(unittest.TestCase):
    def test_entry_has_native_linear_approach_bounce_and_27_tick_completion(self):
        state = initialize_help()
        self.assertFalse(help_draw_state(state)['visible'])
        start_help(state)
        self.assertEqual((state['phase'], state['age'], state['y']),
                         (1, 0.0, -448.0))
        self.assertTrue(help_draw_state(state)['visible'])
        self.assertFalse(help_draw_state(state)['draw_text'])

        samples = {}
        for tick in range(1, 28):
            step_help(state)
            samples[tick] = (state['phase'], state['age'],
                             state['x'], state['y'])
        for tick in (1, 9, 10):
            self.assertEqual(samples[tick], (1, float(tick), 24.0, 496.0))
        self.assertEqual(samples[15], (1, 15.0, 24.0, 272.0))
        self.assertEqual(samples[16], (1, 16.0, 24.0, 275.0))
        self.assertEqual(samples[17], (1, 17.0, 24.0, 278.0))
        self.assertEqual(samples[19], (1, 19.0, 24.0, 272.0))
        self.assertEqual(samples[21], (1, 21.0, 24.0, 276.0))
        self.assertEqual(samples[23], (1, 23.0, 24.0, 272.0))
        self.assertEqual(samples[25], (1, 25.0, 24.0, 274.0))
        self.assertEqual(samples[26], (1, 26.0, 24.0, 273.0))
        self.assertEqual(samples[27], (2, 0.0, 24.0, 272.0))
        self.assertTrue(help_draw_state(state)['draw_text'])
        step_help(state)
        self.assertEqual((state['phase'], state['age']), (2, 0.0))

    def test_exit_shifts_down_in_five_ticks_and_disables_glyphs_at_start(self):
        state = initialize_help()
        start_help(state)
        for _ in range(27):
            step_help(state)
        exit_help(state)
        self.assertEqual((state['phase'], state['age']), (3, 0.0))
        self.assertTrue(help_draw_state(state)['visible'])
        self.assertFalse(help_draw_state(state)['draw_text'])
        # These values include the EE's float32 DIV.S, MUL.S, ADD.S
        # rounding. Double-precision 272+224*t/5 is not a valid oracle.
        expected_y = (
            316.79998779296875, 361.6000061035156,
            406.4000244140625, 451.20001220703125, 496.0,
        )
        for tick in range(1, 6):
            step_help(state)
            self.assertEqual(state['y'], expected_y[tick - 1])
            if tick < 5:
                self.assertEqual((state['phase'], state['age']),
                                 (3, float(tick)))
        self.assertEqual((state['phase'], state['age'],
                          state['x'], state['y']), (0, 0.0, 24.0, 496.0))
        self.assertFalse(help_draw_state(state)['visible'])

    def test_entry_interruption_and_complete_reentry_reset(self):
        state = initialize_help()
        start_help(state)
        for _ in range(20):
            step_help(state)
        self.assertEqual((state['phase'], state['age']), (1, 20.0))
        exit_help(state)
        self.assertEqual((state['phase'], state['age']), (3, 0.0))
        step_help(state)
        self.assertEqual(state['age'], 1.0)
        start_help(state)
        self.assertEqual((state['phase'], state['age'], state['y']),
                         (1, 0.0, -448.0))
        for _ in range(27):
            step_help(state)
        self.assertEqual(help_draw_state(state)['position'], (24.0, 272.0))

    def test_parent_runtime_starts_help_after_entry_and_updates_it_first(self):
        from arika_menu_runtime import c_menu_runtime
        from test_arika_menu_runtime import fixture, ready
        runtime = c_menu_runtime(fixture())
        self.assertEqual(runtime.snapshot()['help']['phase'], 0)
        ready(runtime)
        start = runtime.snapshot()
        self.assertEqual(start['help']['phase'], 1)
        self.assertEqual(start['help']['age'], 0.0)
        self.assertFalse(start['help']['draw_text'])
        for tick in range(1, 28):
            frame = runtime.step()
            self.assertEqual(frame['help']['phase'], 1 if tick < 27 else 2)
            # The help component must advance before the input callback.
            events = [e['event'] for e in frame['calls']]
            self.assertLess(events.index('inner_update'),
                            events.index('input_poll'))
        self.assertTrue(frame['help']['draw_text'])
        frame = runtime.step(input_mask=2)
        self.assertEqual((frame['selected'], frame['help']['phase'],
                          frame['help']['position']), (1, 2, (24.0, 272.0)))
        self.assertEqual(frame['help']['age'], 0.0,
                         'selecting another item does not reset help clock')

        frame = runtime.step(confirm_mask=0x40)
        self.assertEqual((frame['outer_phase'], frame['help']['phase'],
                          frame['help']['age']), (3, 3, 0.0))
        self.assertFalse(frame['help']['draw_text'])
        frame = runtime.step(fade_busy=True)
        self.assertEqual((frame['help']['phase'], frame['help']['age']), (3, 1.0))
        self.assertEqual(runtime.snapshot()['help'], frame['help'],
                         'reading snapshots cannot advance native clocks')

    def test_both_cancel_and_confirm_exits_request_help_phase_three(self):
        from arika_menu_runtime import c_menu_runtime
        from test_arika_menu_runtime import fixture, ready
        for action in ('confirm', 'cancel'):
            with self.subTest(action=action):
                runtime = c_menu_runtime(fixture())
                ready(runtime)
                for _ in range(27):
                    runtime.step()
                kwargs = ({'confirm_mask': 0x40} if action == 'confirm'
                          else {'controller_qualified': False})
                state = runtime.step(**kwargs)
                self.assertEqual((state['help']['phase'],
                                  state['help']['age']), (3, 0.0))
                self.assertFalse(state['help']['draw_text'])
                for _ in range(5):
                    state = runtime.step(fade_busy=True)
                self.assertEqual(state['help']['phase'], 0)


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'set SDBZ_EU_BETA_ELF for exact original-file checks')
class HelpOwnerElfTablesTests(unittest.TestCase):
    def test_original_state_dispatch_and_curve_arrays(self):
        binary = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(binary).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')

        def word(va):
            return struct.unpack_from('<I', binary, va - 0x100000 + 0x80)[0]

        def real(va):
            return struct.unpack_from('<f', binary, va - 0x100000 + 0x80)[0]

        vtable = 0x4F1F30
        for offset, target in {
            0x08: 0x35F7C0,
            0x10: 0x35F800,
            0x14: 0x35F820,
            0x1C: 0x3369F0,
            0x20: 0x336980,
            0x34: 0x37C020,
            0x3C: 0x37C0F0,
            0x40: 0x37C160,
            0x4C: 0x37BF60,
        }.items():
            with self.subTest(offset=offset):
                self.assertEqual(word(vtable + offset), target)

        for address, values in (
                (0x4FA778, HELP_ENTRY_TIMES),
                (0x4FA780, HELP_ENTRY_OFFSETS),
                (0x4FA788, HELP_EXIT_TIMES),
                (0x4FA790, HELP_EXIT_OFFSETS),
                (0x4AA130, HELP_BOUNCE_TIMES),
                (0x4AA170, HELP_BOUNCE_OFFSETS)):
            with self.subTest(address=hex(address)):
                self.assertEqual(tuple(real(address + i * 4)
                                       for i in range(len(values))), values)
        self.assertEqual(real(0x4AA160) + real(0x4FA77C),
                         HELP_ENTRY_COMPLETE)
        self.assertEqual(real(0x4FA78C), HELP_EXIT_COMPLETE)
        self.assertEqual(word(0x37C198), 0xAC83000C,
                         'phase-one Y=-448 is written in jump delay slot')
        self.assertEqual(word(0x37C060), 0xE48C0074,
                         'entry age is stored before its first curve call')
        self.assertEqual(word(0x37C118), 0xE48C0074,
                         'exit age is stored before its curve call')


if __name__ == '__main__':
    unittest.main()
