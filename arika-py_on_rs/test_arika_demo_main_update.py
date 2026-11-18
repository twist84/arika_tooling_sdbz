"""The EE 0x3E0830 DemoMain update: exact branch and external gating tests."""
import os
from pathlib import Path
import unittest

from arika_app_registry import (
    DEMO_MAIN_CHILD_CHOICES, resolve_app, verify_app_registry_elf,
)
from arika_demo_main_update import (
    UPDATE_WORDS, c_demo_main_update, verify_demo_main_update_elf,
)


class DemoMainUpdateTests(unittest.TestCase):
    def test_app_id_eight_and_nine_are_distinct_factories(self):
        self.assertEqual(resolve_app(8)['class_name'], 'CAppDemoMain')
        self.assertEqual(resolve_app(9)['class_name'], 'CAppDemoPlay')
        self.assertEqual(resolve_app(8)['factory'], 0x3f2b40)
        self.assertEqual(resolve_app(9)['factory'], 0x3f2ae0)
        self.assertEqual(resolve_app(8)['constructor'], 0x3e2160)
        self.assertEqual(resolve_app(9)['constructor'], 0x3e0df0)
        self.assertNotEqual(resolve_app(6)['factory'], resolve_app(8)['factory'])
        self.assertNotEqual(resolve_app(6)['name_address'],
                            resolve_app(8)['name_address'])
        self.assertEqual(DEMO_MAIN_CHILD_CHOICES, (4, 7, 8, 9))

    def test_four_way_dispatch_wrap_and_child_request_sites(self):
        native = c_demo_main_update()
        self.assertEqual(native.snapshot()['phase'], 0)
        self.assertEqual(native.snapshot()['return_app'], 3)
        self.assertEqual(native.snapshot()['next_choice'], 0)

        observed = []
        for choice, expected_id in enumerate(DEMO_MAIN_CHILD_CHOICES):
            # Supply a specific captured next-choice register value at
            # the native phase-0 boundary. No invented autoplay logic.
            native.set_captured_next_choice(choice)
            result = native.step(child_present=False, child_pending=True)
            chosen = result['snapshot']['last_child']
            self.assertEqual(chosen['choice'], choice)
            self.assertEqual(chosen['id'], expected_id)
            self.assertEqual(chosen['name'], resolve_app(expected_id)['class_name'])
            self.assertEqual(result['snapshot']['next_choice'], (choice + 1) & 3)
            self.assertEqual(result['snapshot']['phase'], 1)
            self.assertEqual([call['address'] for call in result['calls']],
                             ['0x3eb860', '0x3dfbd0', '0x3dfc60'])
            self.assertEqual(result['calls'][1]['arguments'], [expected_id])
            observed.append(chosen['request_site'])
            # ID 7 and ID 9 completion request a parent transition;
            # keep this test in phase 0 by resetting the diagnostic
            # model between independent captured sessions.
            native = c_demo_main_update()
        self.assertEqual(observed, [0x3e08b4, 0x3e08cc, 0x3e08e4, 0x3e08f4])

    def test_starting_at_zero_auto_advances_first_two_children(self):
        native = c_demo_main_update()
        first = native.step(False, True)
        self.assertEqual(first['snapshot']['next_choice'], 1)
        self.assertEqual(first['snapshot']['child_requests'], 1)
        self.assertEqual(native.step(False, True)['snapshot']['phase'], 1)
        finished_child = native.step(False, False)
        self.assertEqual(finished_child['snapshot']['phase'], 0)
        self.assertFalse(finished_child['finished'])
        second = native.step(False, True)
        self.assertEqual(second['snapshot']['last_child']['id'], 7)
        self.assertEqual(second['snapshot']['next_choice'], 2)
        self.assertEqual(second['snapshot']['phase'], 1)

    def test_child_presence_invokes_virtual_update_not_no_child_helper(self):
        native = c_demo_main_update()
        first = native.step(child_present=True, child_pending=True)
        self.assertEqual([call['address'] for call in first['calls']],
                         ['child_vtable+0x18', '0x3dfbd0', '0x3dfc60'])
        next_step = native.step(child_present=True, child_pending=True)
        self.assertEqual([call['address'] for call in next_step['calls']],
                         ['child_vtable+0x18', '0x3dfc60'])
        self.assertEqual(next_step['snapshot']['child_requests'], 1)
        self.assertEqual(next_step['snapshot']['phase'], 1)
        self.assertEqual(native.step(True, False)['snapshot']['phase'], 0)

    def test_id_seven_completion_requests_parent_application_three(self):
        native = c_demo_main_update()
        native.set_captured_next_choice(1)
        selected = native.step(False, True)
        self.assertEqual(selected['snapshot']['last_child']['id'], 7)
        completion = native.step(False, False)
        self.assertTrue(completion['finished'])
        self.assertEqual(completion['snapshot']['last_return'], 3)
        self.assertEqual(completion['snapshot']['phase'], 0)
        self.assertEqual(completion['snapshot']['exit_flag'], False)
        self.assertEqual(
            [call['address'] for call in completion['calls']],
            ['0x3dfc60', '0x3ef140', '0x3ef4d0',
             'child_flags_clear_bit0', '0x3dfb00'])
        self.assertEqual(completion['calls'][-1]['arguments'], [3])
        self.assertTrue(all(not call['executed'] for call in completion['calls']))
        with self.assertRaisesRegex(ValueError, 'already completed'):
            native.step(False, False)

    def test_id_nine_completion_requests_parent_application_six(self):
        native = c_demo_main_update()
        native.set_captured_next_choice(3)
        selected = native.step(False, True)
        self.assertEqual(selected['snapshot']['last_child']['id'], 9)
        done = native.step(False, False)
        self.assertTrue(done['finished'])
        self.assertEqual(done['snapshot']['return_app'], 6)
        self.assertEqual(done['snapshot']['last_return'], 6)
        self.assertEqual(done['calls'][-1]['arguments'], [6])
        self.assertEqual(done['snapshot']['next_choice'], 0)

    def test_non_exiting_id_eight_completion_cycles_to_nine(self):
        native = c_demo_main_update()
        native.set_captured_next_choice(2)
        first = native.step(False, True)
        self.assertEqual(first['snapshot']['last_child']['id'], 8)
        self.assertEqual(first['snapshot']['next_choice'], 3)
        finished_child = native.step(False, False)
        self.assertFalse(finished_child['finished'])
        self.assertEqual(finished_child['snapshot']['phase'], 0)
        later = native.step(False, True)
        self.assertEqual(later['snapshot']['last_child']['id'], 9)
        self.assertEqual(later['snapshot']['next_choice'], 0)

    def test_immediate_child_completion_branch_in_same_update(self):
        native = c_demo_main_update()
        native.set_captured_next_choice(1)
        done = native.step(child_present=False, child_pending=False)
        self.assertTrue(done['finished'])
        self.assertEqual(done['snapshot']['updates'], 1)
        self.assertEqual(done['snapshot']['last_return'], 3)
        self.assertEqual(done['calls'][1]['arguments'], [7])
        self.assertEqual(done['calls'][-1]['address'], '0x3dfb00')

    def test_external_exit_flag_can_override_pending_child(self):
        native = c_demo_main_update()
        result = native.step(child_present=False, child_pending=True,
                             external_exit=True)
        self.assertTrue(result['finished'])
        self.assertEqual(result['snapshot']['last_return'], 3)
        self.assertEqual(result['calls'][-1]['arguments'], [3])
        self.assertFalse(result['snapshot']['exit_flag'])

    def test_input_validation_and_captured_choice_gate(self):
        native = c_demo_main_update()
        for bad in (True, -1, 4, None, '1'):
            with self.subTest(choice=bad), self.assertRaises(ValueError):
                native.set_captured_next_choice(bad)
        for bad in (1, 0, None, 'False'):
            for param in ('child_present', 'child_pending', 'external_exit'):
                with self.subTest(param=param, bad=bad):
                    arguments = {
                        'child_present': False,
                        'child_pending': True,
                        'external_exit': False,
                    }
                    arguments[param] = bad
                    with self.assertRaises(ValueError):
                        native.step(**arguments)
        self.assertEqual(native.snapshot()['updates'], 0)
        native.step(False, True)
        with self.assertRaisesRegex(ValueError, 'phase 0'):
            native.set_captured_next_choice(2)

    def test_original_elf_hash_and_dispatch_oracle_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'exact EU-beta'):
            verify_demo_main_update_elf(b'wrong ELF')
        self.assertGreaterEqual(len(UPDATE_WORDS), 30)
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('original EU beta ELF not bundled with CI')
        binary = Path(path).read_bytes()
        result = verify_demo_main_update_elf(binary)
        registry = verify_app_registry_elf(binary)
        self.assertEqual(result['child_ids'], [4, 7, 8, 9])
        self.assertEqual(result['return_app_after_child'], {'1': 3, '3': 6})
        self.assertEqual(registry['registered'][-2]['id'], 8)
        self.assertEqual(registry['registered'][-1]['id'], 9)


if __name__ == '__main__':
    unittest.main()
