"""Synthetic native Press Start clock tests and optional exact ELF oracle."""
import os
from pathlib import Path
import unittest

from arika_press_start_animation import (
    PRESS_START_CYCLE_END, PRESS_START_VISIBLE_AFTER,
    PRESS_START_ANIMATION_WORDS, c_press_start_prompt_clock,
    verify_press_start_animation_elf,
)


class PressStartNativeAnimationTests(unittest.TestCase):
    def test_exact_gate_and_three_second_wrap(self):
        self.assertEqual(PRESS_START_CYCLE_END, 3.0)
        self.assertEqual(PRESS_START_VISIBLE_AFTER, 1.0)
        clock = c_press_start_prompt_clock()
        self.assertFalse(clock.visible)
        self.assertFalse(clock.advance(1.0))
        self.assertEqual(clock.phase, 1.0)
        self.assertTrue(clock.advance(0.125))
        self.assertTrue(clock.advance(1.875))
        self.assertEqual(clock.phase, 3.0)
        self.assertFalse(clock.advance(0.01))
        self.assertEqual(clock.phase, 0.0)
        self.assertFalse(clock.visible)
        self.assertEqual(clock.m_ticks, 4)

    def test_large_step_discards_overshoot_instead_of_modulo(self):
        clock = c_press_start_prompt_clock(2.9)
        self.assertTrue(clock.visible)
        self.assertFalse(clock.advance(0.2))
        self.assertEqual(clock.phase, 0.0)
        self.assertFalse(clock.advance(60.0))
        self.assertEqual(clock.phase, 0.0)

    def test_external_global_scheduler_gate_and_float32_phase(self):
        clock = c_press_start_prompt_clock(1.25)
        self.assertTrue(clock.advance(50.0, update_enabled=False))
        self.assertEqual(clock.phase, 1.25)
        self.assertEqual(clock.m_ticks, 0)
        self.assertTrue(clock.advance(0.25))
        self.assertEqual(clock.phase, 1.5)
        self.assertEqual(clock.m_ticks, 1)

    def test_unverified_clock_inputs_fail_closed(self):
        for value in (float('inf'), float('nan'), -1, 4, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                c_press_start_prompt_clock(value)
        for value in (float('inf'), float('nan'), -0.01, True, '1', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                c_press_start_prompt_clock().advance(value)
        with self.assertRaises(ValueError):
            c_press_start_prompt_clock().advance(1, update_enabled=1)

    def test_original_elf_clock_oracle(self):
        self.assertGreaterEqual(len(PRESS_START_ANIMATION_WORDS), 15)
        with self.assertRaisesRegex(ValueError, 'EU-beta ELF'):
            verify_press_start_animation_elf(b'wrong executable')
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('original exact ELF supplied locally, never on CI')
        result = verify_press_start_animation_elf(Path(path).read_bytes())
        self.assertEqual(result['visible_after'], 1.0)
        self.assertEqual(result['reset_above'], 3.0)


if __name__ == '__main__':
    unittest.main()
