"""Native parent/exit lifecycle regressions with synthetic item completion."""
import unittest

from arika_menu_runtime import c_menu_runtime


def fixture():
    items = [
        {
            'index': i,
            'neighbors': [{'value': -1} for _ in range(4)],
            'route': {'mode_selector': i, 'next_app_id': i + 10},
        }
        for i in range(7)
    ]
    items[0]['neighbors'][3] = {'value': 1}
    items[1]['neighbors'][0] = {'value': 2}
    return {
        'menu': {'items': items, 'entry_count': 7},
        'shared_scheduler': {
            'overlay_target': 0.5,
            'overlay_rate': 0.1,
            'small_start_times': [10., 30., 40., 20., 25., 35., 15.],
            'entry_wait': 15.,
        },
    }


def ready(runtime):
    for _ in range(100):
        state = runtime.step()
        if state['outer_phase'] == 2:
            return state
    raise AssertionError('shared scheduler did not complete')


class MenuRuntimeTests(unittest.TestCase):
    def test_entry_order_and_selected_zero(self):
        runtime = c_menu_runtime(fixture())
        state = runtime.step()
        self.assertEqual(state['outer_phase'], 1)
        self.assertEqual(state['shared_phase'], 1)
        self.assertEqual([x['event'] for x in state['calls'][-2:]],
                         ['start_shared', 'entry_poll'])
        state = ready(runtime)
        self.assertEqual(state['selected'], 0)
        self.assertEqual(state['previous'], -1)
        self.assertEqual(state['shared_started_count'], 7)
        names = [x['event'] for x in state['calls']]
        self.assertLess(names.index('shared_update'), names.index('entry_poll'))
        self.assertLess(names.index('entry_poll'), names.index('input_poll'))
        self.assertEqual(state['item_phases'][0], 1)

    def test_navigation_pending_cleanup_and_independent_ages(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        state = runtime.step(input_mask=2)
        self.assertEqual((state['selected'], state['previous'], state['pending']),
                         (1, 0, 0))
        self.assertEqual((state['item_phases'][0], state['item_phases'][1]), (4, 1))
        self.assertNotEqual(state['item_ages'][0], state['item_ages'][1])
        # Pending old item cannot be retired until the native item phase is 0.
        for _ in range(12):
            self.assertEqual(runtime.step()['pending'], 0)
        runtime.set_item_phase(0, 0)
        state = runtime.step()
        self.assertEqual(state['pending'], -1)
        self.assertIn('shared_remove_item',
                      [x['event'] for x in state['calls']])

    def test_blocked_moves_preserve_history(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        before = runtime.snapshot()
        for _ in range(5):
            state = runtime.step(input_mask=8)
        self.assertEqual((state['selected'], state['previous'], state['pending']),
                         (before['selected'], before['previous'], before['pending']))

    def test_confirm_waits_for_fade_query_then_completes(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        state = runtime.step(confirm_mask=0x40)
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30))
        self.assertEqual(state['shared_phase'], 3)
        self.assertIn('fade_start', [x['event'] for x in state['calls']])
        state = runtime.step(fade_busy=True)
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30))
        state = runtime.step(fade_busy=False)
        self.assertEqual(state['outer_phase'], 4)
        self.assertEqual(state['completion']['next_app_id'], 10)
        self.assertEqual(runtime.step()['calls'], [])

    def test_cancel_has_exact_substate_ten_logical_step_wait(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        state = runtime.step(controller_qualified=False)
        self.assertEqual((state['outer_phase'], state['exit_phase'],
                          state['confirm']), (3, 0, 0))
        self.assertEqual(runtime.step(fade_busy=False)['exit_phase'], 1)
        self.assertEqual(runtime.step(fade_busy=True)['exit_phase'], 1)
        self.assertEqual(runtime.step(fade_busy=False)['exit_phase'], 2)
        for count in range(1, 11):
            state = runtime.step()
            self.assertEqual(state['exit_age'], float(count))
            self.assertEqual(state['exit_phase'], 2 if count < 10 else 3)
        self.assertEqual(runtime.step()['exit_phase'], 30)
        self.assertEqual(runtime.step(fade_busy=False)['outer_phase'], 4)
        self.assertEqual(runtime.snapshot()['completion'], {
            'mode_selector': None, 'next_app_id': 3, 'cancelled': True})

    def test_independent_item_age_wrap_and_inactive_gate(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        runtime.m_item_ages[0] = 99999.0
        self.assertEqual(runtime.step()['item_ages'][0], 1.0)
        runtime.set_item_phase(0, 0)
        self.assertEqual(runtime.step()['item_ages'][0], 1.0)

    def test_no_invented_fade_completion(self):
        runtime = c_menu_runtime(fixture())
        ready(runtime)
        runtime.step(confirm_mask=0x40)
        for _ in range(200):
            state = runtime.step()
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30))


class MenuRuntimeNativeLabelTests(unittest.TestCase):
    """Real ELF-derived label tables; no authored timeline indices."""

    def test_entry_selection_and_independent_label_ages(self):
        from arika_menu_navigation import read_menu_report
        runtime = c_menu_runtime(read_menu_report())
        state = ready(runtime)
        self.assertEqual((state['label_phases'][0], state['label_ages'][0]), (1, 0.0))
        self.assertIsNotNone(runtime.label_geometry(0))
        self.assertIsNone(runtime.label_geometry(1))
        for _ in range(32):
            state = runtime.step()
        self.assertEqual(state['label_phases'][0], 2)
        self.assertEqual(state['label_offsets'][0], (0.0, 0.0))
        state = runtime.step(input_mask=2)
        self.assertEqual((state['selected'], state['pending']), (1, 0))
        self.assertEqual((state['label_phases'][0], state['label_phases'][1]), (4, 1))
        self.assertEqual((state['label_ages'][0], state['label_ages'][1]), (0.0, 0.0))
        for _ in range(10):
            state = runtime.step()
        self.assertEqual(state['label_phases'][0], 0)
        self.assertIsNone(runtime.label_geometry(0))
        self.assertEqual(state['pending'], -1,
                         'all three ELF-backed exit callbacks have completed')
        self.assertEqual(state['item_phases'][0], 0)
        self.assertEqual(state['first_phases'][0], 0)
        self.assertEqual(state['character_phases'][0], 0)
        self.assertEqual(state['label_ages'][1], 10.0)

    def test_child_entry_ages_and_parent_readiness(self):
        from arika_menu_navigation import read_menu_report
        runtime = c_menu_runtime(read_menu_report())
        ready(runtime)
        start = runtime.snapshot()
        self.assertEqual(start['first_phases'][0], 1)
        self.assertEqual(start['character_phases'][0], 1)
        self.assertEqual(start['item_phases'][0], 1)
        self.assertEqual(start['character_ages'][0], 0.0)
        self.assertTrue(runtime.character_geometry(0))
        self.assertEqual(runtime.character_geometry(1), [])
        for _ in range(16):
            state = runtime.step()
        self.assertEqual((state['first_phases'][0],
                          state['item_phases'][0]), (1, 1))
        self.assertEqual(state['first_ages'][0], 16.0)
        state = runtime.step()
        self.assertEqual((state['first_phases'][0],
                          state['item_phases'][0]), (2, 2))
        self.assertEqual(state['first_ages'][0], 0.0)
        self.assertEqual(state['character_phases'][0], 1)
        for _ in range(5):
            state = runtime.step()
        self.assertEqual((state['character_phases'][0],
                          state['character_ages'][0]), (2, 0.0))
        initial_part_offsets = list(runtime.m_character_states[0].get(
            'part_offsets', []))
        for _ in range(40):
            state = runtime.step()
        self.assertEqual((state['character_phases'][0],
                          state['character_ages'][0]), (2, 40.0),
                         'item-zero phase-two callback advances +0x08')
        self.assertNotEqual(runtime.m_character_states[0]['part_offsets'],
                            initial_part_offsets)

    def test_all_seven_phase_two_clocks_use_recovered_periods(self):
        from arika_menu_navigation import read_menu_report
        runtime = c_menu_runtime(read_menu_report())
        idle = runtime.m_idle_components
        self.assertEqual(set(idle), set(range(7)))
        for item in range(7):
            character = runtime.m_character_states[item]
            runtime.m_item_phases[item] = 2
            character.update(phase=2, age=0.0)
            # For exact period, MIPS phase-two callbacks subtract once
            # rather than wrapping with an arbitrary wall-clock duration.
            period = idle[item]['curve']['times'][-1]
            character['age'] = period - 1.0
            runtime._update_item(item, 'test_child_update')
            self.assertEqual(character['age'], 0.0,
                             'item %d period %s' % (item, period))
            self.assertEqual(character['phase'], 2)
            if item not in (5,):
                self.assertEqual(
                    len(character['part_offsets']),
                    len(runtime.m_report['composite_layout']
                        ['composites'][item]['parts']))

    def test_old_selection_retires_exactly_after_child_exit(self):
        from arika_menu_navigation import read_menu_report
        runtime = c_menu_runtime(read_menu_report())
        ready(runtime)
        for _ in range(28):
            runtime.step()
        state = runtime.step(input_mask=2)
        self.assertEqual((state['selected'], state['pending']), (1, 0))
        self.assertEqual(state['first_phases'][0], 4)
        self.assertEqual(state['character_phases'][0], 4)
        self.assertEqual(state['label_phases'][0], 4)
        self.assertEqual(state['character_ages'][0], 0.0)
        initial_pose = runtime.character_geometry(0)
        for _ in range(9):
            state = runtime.step()
        self.assertEqual((state['pending'], state['item_phases'][0]), (0, 4))
        self.assertNotEqual(runtime.character_geometry(0), initial_pose)
        self.assertEqual((state['first_phases'][0],
                          state['character_phases'][0],
                          state['label_phases'][0]), (4, 4, 4))
        state = runtime.step()
        self.assertEqual((state['pending'], state['item_phases'][0]), (-1, 0))
        self.assertEqual((state['first_phases'][0],
                          state['character_phases'][0],
                          state['label_phases'][0]), (0, 0, 0))
        self.assertEqual(runtime.character_geometry(0), [])
        self.assertEqual(state['character_ages'][1], 10.0)
        self.assertEqual(state['character_phases'][1], 1,
                         'new character is still entering as old exits')

    def test_confirm_exit_and_cancel_emphasis_are_distinct(self):
        from arika_menu_navigation import read_menu_report
        runtime = c_menu_runtime(read_menu_report())
        ready(runtime)
        state = runtime.step(confirm_mask=0x40)
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30))
        self.assertEqual(state['label_phases'][0], 4)
        self.assertEqual(state['first_phases'][0], 4)
        self.assertEqual(state['character_phases'][0], 4)
        runtime = c_menu_runtime(read_menu_report())
        ready(runtime)
        state = runtime.step(controller_qualified=False)
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 0))
        self.assertEqual(state['label_phases'][0], 3)
        self.assertEqual(state['first_phases'][0], 3)
        self.assertEqual(state['character_phases'][0], 3)
        state = runtime.step(fade_busy=False)
        self.assertEqual((state['label_phases'][0], state['label_ages'][0]), (3, 1.0))




if __name__ == '__main__':
    unittest.main()
