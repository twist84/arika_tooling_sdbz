"""Native-menu navigation and CUSTOMIZE re-entry use real logical input edges.

The outer scheduler and per-item callbacks are already recovered. This
integration test deliberately navigates via original 0x379C80 masks,
not direct forced state/diagnostic sample numbers.
"""
import unittest

from arika_menu_navigation import read_menu_report
from arika_menu_runtime import c_menu_runtime


class NativePhaseSixTransitionTests(unittest.TestCase):
    def test_customize_clock_resets_after_actual_input_navigation_reentry(self):
        runtime = c_menu_runtime(read_menu_report(), particle_seed=1)
        for _ in range(120):
            state = runtime.step()
            if state['outer_phase'] == 2:
                break
        else:
            self.fail('menu never completed its recovered outer entry')
        self.assertEqual(state['selected'], 0)

        # 0 RIGHT -> 3 DRAGON SUMMONING, 3 DOWN -> 5 CUSTOMIZE.
        self.assertEqual(runtime.step(input_mask=8)['selected'], 3)
        self.assertEqual(runtime.step(input_mask=2)['selected'], 5)
        for _ in range(40):
            state = runtime.step()
            if state['character_phases'][5] == 2:
                break
        else:
            self.fail('CUSTOMIZE did not enter native phase-2 idle')
        self.assertEqual((state['character_ages'][5],
                          runtime.m_character_states[5]['secondary_age']),
                         (0.0, 0.0))
        for _ in range(7):
            state = runtime.step()
        self.assertGreater(runtime.m_character_states[5][
            'secondary_age'], 0.0)

        # 5 UP -> 3, then 3 DOWN -> 5. We do not replace the
        # real transition with a synthetic direct .start_character().
        self.assertEqual(runtime.step(input_mask=1)['selected'], 3)
        self.assertEqual(runtime.step(input_mask=2)['selected'], 5)
        self.assertEqual(runtime.m_character_states[5]['phase'], 1)
        self.assertGreater(runtime.m_character_states[5]['secondary_age'], 0.0,
                           'entry-start does not clear secondary age')
        for _ in range(40):
            state = runtime.step()
            if state['character_phases'][5] == 2:
                break
        else:
            self.fail('CUSTOMIZE re-entry did not reach active phase')
        self.assertEqual(runtime.m_character_states[5]['secondary_age'], 0.0)
        self.assertEqual(state['character_ages'][5], 0.0)
        # The authored 140-sample diagnostic clock is never accessed.
        self.assertEqual(state['selected'], 5)
        self.assertEqual(state['previous'], 3)

    def test_dragon_idle_uses_item_clock_and_reentry_resets_age(self):
        runtime = c_menu_runtime(read_menu_report(), particle_seed=1)
        for _ in range(120):
            state = runtime.step()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(runtime.step(input_mask=8)['selected'], 3)
        for _ in range(40):
            state = runtime.step()
            if state['character_phases'][3] == 2:
                break
        self.assertEqual(state['character_phases'][3], 2)
        self.assertEqual(state['character_ages'][3], 0.0)
        for _ in range(9):
            state = runtime.step()
        self.assertEqual(state['character_ages'][3], 9.0)
        self.assertEqual(len(state['character_part_offsets'][3]), 8)

        self.assertEqual(runtime.step(input_mask=2)['selected'], 5)
        self.assertEqual(runtime.step(input_mask=1)['selected'], 3)
        for _ in range(40):
            state = runtime.step()
            if state['character_phases'][3] == 2:
                break
        self.assertEqual(state['character_ages'][3], 0.0)


if __name__ == '__main__':
    unittest.main()
