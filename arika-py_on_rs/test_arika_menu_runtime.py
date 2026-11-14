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


if __name__ == '__main__':
    unittest.main()
