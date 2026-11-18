"""Regression tests for non-executing, original-ELF lifecycle semantics."""
import unittest

from arika_app_registry import APP_ENTRIES, APP_NATIVE_REGISTRY
from arika_native_app_lifecycle import (
    describe_native_root_factory, inspect_native_phase_five_root_handoff,
    inspect_fight_demo_end_timeout, inspect_fight_play_single_finish,
    inspect_native_child_forward, inspect_fight_result_child,
    NATIVE_SENTINEL_ID, describe_native_phase, inspect_demo_main_exit,
    inspect_native_child_successor,
    inspect_native_phase_gate, inspect_native_transition_request,
)


class NativeLifecycleTests(unittest.TestCase):
    def test_all_47_phase_callbacks_match_base_vtables(self):
        self.assertEqual(NATIVE_SENTINEL_ID, 48)
        self.assertEqual(len(APP_ENTRIES), 47)
        for app_id, app in APP_ENTRIES.items():
            for phase, offset in ((2, 0x38), (3, 0x3C),
                                  (4, 0x40), (5, 0x44)):
                with self.subTest(app_id=app_id, phase=phase):
                    callback = describe_native_phase(app_id, phase)
                    self.assertEqual(callback['virtual_offset'], offset)
                    self.assertEqual(callback['callback_address'],
                                     app['base_slots']['0x%02x' % offset])
                    self.assertFalse(callback['callback_executed'])
                    self.assertEqual(callback['vtable_address'],
                                     app['base_vtable'])
            self.assertIsNone(describe_native_phase(app_id, 0))
            self.assertIsNone(describe_native_phase(app_id, 1))
            self.assertIsNone(describe_native_phase(app_id, 6))
        self.assertEqual(describe_native_phase(1, 2)['callback_address'],
                         0x3FAAB0)
        self.assertEqual(describe_native_phase(42, 4)['callback_address'],
                         0x3FE020)

    def test_phase_gate_requires_explicit_callback_and_unblocked_flags(self):
        for phase in (2, 3, 4):
            with self.subTest(phase=phase):
                ready = inspect_native_phase_gate(42, phase, True, 0, 0)
                self.assertTrue(ready['would_advance'])
                self.assertEqual(ready['next_phase'], phase + 1)
                self.assertTrue(ready['simulated_from_explicit_observations'])
                for result, flags, status, reason in (
                        (False, 0, 0, 'callback_blocked'),
                        (True, 2, 0, 'transition_flag'),
                        (True, 0, 0x80000000, 'status_busy')):
                    blocked = inspect_native_phase_gate(
                        42, phase, result, flags, status)
                    self.assertEqual(blocked['next_phase'], phase)
                    self.assertEqual(blocked['reason'], reason)
                    self.assertFalse(blocked['factory_executed'])

    def test_transition_request_phase_switch_and_nested_sentinel(self):
        for phase in (0, 5, 6):
            with self.subTest(phase=phase):
                request = inspect_native_transition_request(
                    3, phase, 4, 42, child_id=6)
                self.assertTrue(request['accepted'])
                self.assertEqual(request['phase'], phase)
                self.assertEqual(request['flags'], 0)
                self.assertEqual(request['pending_id'], 42)
                self.assertFalse(request['recursive_cancel_possible'])
                self.assertFalse(request['factory_executed'])
        for phase in (1, 2, 3, 4):
            with self.subTest(phase=phase):
                request = inspect_native_transition_request(
                    3, phase, 4, 42, child_id=6)
                self.assertEqual(request['phase'], 5)
                self.assertEqual(request['flags'], 2)
                self.assertTrue(request['recursive_cancel_possible'])
                self.assertEqual(request['recursive_cancel_value'], 48)
                self.assertFalse(request['factory_executed'])
        no_child = inspect_native_transition_request(3, 3, 0, 6)
        self.assertFalse(no_child['recursive_cancel_possible'])
        rejected = inspect_native_transition_request(3, 3, 1, 42)
        self.assertFalse(rejected['accepted'])
        self.assertIsNone(rejected['pending_id'])
        self.assertEqual(rejected['phase'], 3)

    def test_parent_child_successor_only_after_phase_six(self):
        waiting = inspect_native_child_successor(6, 4, 5, 7)
        self.assertEqual(waiting['outcome'], 'child_not_complete')
        self.assertEqual(waiting['next_child_id'], 4)
        self.assertFalse(waiting['invoke_child_teardown'])
        done = inspect_native_child_successor(6, 4, 6, 7)
        self.assertEqual(done['outcome'], 'child_successor_selected')
        self.assertEqual(done['next_child_id'], 7)
        self.assertEqual(done['parent_id'], 6)
        self.assertTrue(done['invoke_child_teardown'])
        self.assertEqual(done['teardown_instruction_site'], 0x3DFFB4)
        self.assertEqual(done['parent_child_id_store_site'], 0x3DFFAC)
        self.assertTrue(done['next_child_registered'])
        self.assertFalse(done['successor_factory_executed'])

        parent_suspended = inspect_native_child_successor(6, 4, 6, 7, 4)
        self.assertEqual(parent_suspended['next_child_id'], 4)
        self.assertFalse(parent_suspended['invoke_child_teardown'])
        self.assertEqual(parent_suspended['outcome'],
                         'parent_child_processing_suspended')
        no_child = inspect_native_child_successor(6, 48, 0, 48)
        self.assertEqual(no_child['outcome'], 'no_active_child')
        end = inspect_native_child_successor(6, 4, 6, 48)
        self.assertEqual(end['next_child_id'], 48)
        self.assertFalse(end['next_child_registered'])
        self.assertFalse(end['successor_factory_executed'])

    def test_demo_main_choice_exit_is_conditional_not_parent_return(self):
        movie = inspect_demo_main_exit(1, child_is_active=False)
        self.assertEqual(movie['native_request_id'], 3)
        self.assertEqual(movie['native_callsite'], 0x3E09E0)
        self.assertEqual(movie['exit_target_field'], 0x2A)
        self.assertFalse(movie['factory_executed'])
        game = inspect_demo_main_exit(3, child_is_active=False)
        self.assertEqual(game['native_request_id'], 6)
        self.assertEqual(game['next_target_id'], 6)
        self.assertTrue(game['pending_global_exit_flag'])
        for choice in (0, 2):
            with self.subTest(choice=choice):
                no_return = inspect_demo_main_exit(choice)
                self.assertIsNone(no_return['native_request_id'])
        ongoing = inspect_demo_main_exit(1, child_is_active=True)
        self.assertIsNone(ongoing['native_request_id'])
        self.assertEqual(ongoing['next_target_id'], 3)
        already_flagged = inspect_demo_main_exit(
            2, current_exit_target=6, prior_exit_flag=True)
        self.assertEqual(already_flagged['native_request_id'], 6)
        self.assertFalse(already_flagged['factory_executed'])
        for fn in (
                lambda: inspect_demo_main_exit(4),
                lambda: inspect_demo_main_exit(True),
                lambda: inspect_demo_main_exit(1, current_exit_target=42),
                lambda: inspect_demo_main_exit(1, child_is_active=1),
                lambda: inspect_demo_main_exit(1, prior_exit_flag=0)):
            with self.assertRaises(ValueError):
                fn()

    def test_fight_result_child_choice_and_sentinel(self):
        self.assertEqual(inspect_fight_result_child(1)['candidate_child_ids'],
                         (29, 30))
        self.assertTrue(inspect_fight_result_child(1)
                        ['needs_external_subcondition'])
        self.assertIsNone(inspect_fight_result_child(1)['native_request_id'])
        for predicate, expected in ((False, 29), (True, 30)):
            choice = inspect_fight_result_child(
                1, condition_for_single=predicate)
            self.assertEqual(choice['native_request_id'], expected)
            self.assertFalse(choice['factory_executed'])
        self.assertEqual(inspect_fight_result_child(2)['native_request_id'], 34)
        self.assertEqual(inspect_fight_result_child(3)['native_request_id'], 38)
        for selector in (-1, 0, 4, 255, -(1 << 31), (1 << 31) - 1):
            with self.subTest(selector=selector):
                other = inspect_fight_result_child(selector)
                self.assertEqual(other['native_request_id'], 48)
                self.assertEqual(other['candidate_child_ids'], ())
                self.assertFalse(other['factory_executed'])
        for fn in (
                lambda: inspect_fight_result_child(True),
                lambda: inspect_fight_result_child(-(1 << 31) - 1),
                lambda: inspect_fight_result_child(1 << 31),
                lambda: inspect_fight_result_child('2'),
                lambda: inspect_fight_result_child(1, condition_for_single=1),
        ):
            with self.assertRaises(ValueError):
                fn()

    def test_forward_child_helper_uses_observed_existing_child(self):
        forwarded = inspect_native_child_forward(
            6, parent_flags=4, child_id=4, requested_id=7,
            existing_child_resolved=True)
        self.assertEqual(forwarded['action'], 'forward_to_existing_child')
        self.assertEqual(forwarded['forwarded_request_id'], 7)
        self.assertEqual(forwarded['forward_callsite'], 0x3DFC1C)
        self.assertEqual(forwarded['parent_flags_after_branch'], 0)
        self.assertIsNone(forwarded['parent_child_id_to_store'])
        self.assertFalse(forwarded['factory_executed'])

        pending = inspect_native_child_forward(
            6, parent_flags=0, child_id=48, requested_id=7,
            existing_child_resolved=False)
        self.assertEqual(pending['action'],
                         'store_new_child_id_and_attempt_lookup')
        self.assertEqual(pending['parent_child_id_to_store'], 7)
        self.assertEqual(pending['child_store_site'], 0x3DFC30)
        self.assertIsNone(pending['forward_callsite'])
        self.assertFalse(pending['factory_executed'])

        blocked = inspect_native_child_forward(
            6, parent_flags=2, child_id=4, requested_id=7,
            existing_child_resolved=True)
        self.assertEqual(blocked['action'], 'parent_transition_busy')
        self.assertIsNone(blocked['forwarded_request_id'])
        self.assertIsNone(blocked['parent_child_id_to_store'])
        self.assertEqual(blocked['parent_flags_after_branch'], 2)
        cancelled = inspect_native_child_forward(
            6, parent_flags=0, child_id=4, requested_id=48,
            existing_child_resolved=True)
        self.assertEqual(cancelled['forwarded_request_id'], 48)
        self.assertFalse(cancelled['factory_executed'])

        for fn in (
                lambda: inspect_native_child_forward(48, 0, 4, 7, True),
                lambda: inspect_native_child_forward(6, -1, 4, 7, True),
                lambda: inspect_native_child_forward(6, 0, 48, 7, True),
                lambda: inspect_native_child_forward(6, 0, 4, 7, 1),
                lambda: inspect_native_child_forward(6, 0, 4, 49, False),
        ):
            with self.assertRaises(ValueError):
                fn()

    def test_fight_demo_end_timer_compares_float32_not_rounded_decimal(self):
        from struct import pack, unpack
        threshold = unpack('<f', pack('<I', 0x3CA3D70A))[0]
        before = inspect_fight_demo_end_timeout(threshold)
        self.assertIsNone(before['native_request_id'])
        self.assertEqual(before['threshold_float32'], threshold)
        self.assertFalse(before['comparison_unordered'])
        done = inspect_fight_demo_end_timeout(0.02)
        self.assertEqual(done['native_request_id'], 48)
        self.assertEqual(done['native_callsite'], 0x3E4C54)
        self.assertFalse(done['request_executed'])
        unordered = inspect_fight_demo_end_timeout(float('nan'))
        self.assertTrue(unordered['comparison_unordered'])
        self.assertEqual(unordered['native_request_id'], 48)
        self.assertIsNone(
            inspect_fight_demo_end_timeout(-1.0)['native_request_id'])
        for value in (True, None, '0.02'):
            with self.assertRaises(ValueError):
                inspect_fight_demo_end_timeout(value)

    def test_fight_play_single_case_nine_completion_requests_sentinel(self):
        for state in (-1, 0, 8, 10, 127):
            with self.subTest(state=state):
                not_final = inspect_fight_play_single_finish(state)
                self.assertIsNone(not_final['native_request_id'])
                self.assertFalse(not_final['needs_predicate_observation'])
        waiting = inspect_fight_play_single_finish(9)
        self.assertTrue(waiting['needs_predicate_observation'])
        self.assertIsNone(waiting['native_request_id'])
        incomplete = inspect_fight_play_single_finish(9, True)
        self.assertIsNone(incomplete['native_request_id'])
        complete = inspect_fight_play_single_finish(9, False)
        self.assertEqual(complete['native_request_id'], 48)
        self.assertEqual(complete['native_callsite'], 0x3E920C)
        self.assertEqual(complete['predicate_callsite'], 0x3E91D4)
        self.assertFalse(complete['factory_executed'])
        for fn in (
                lambda: inspect_fight_play_single_finish(True),
                lambda: inspect_fight_play_single_finish(128),
                lambda: inspect_fight_play_single_finish(-129),
                lambda: inspect_fight_play_single_finish(9, 0),
        ):
            with self.assertRaises(ValueError):
                fn()

    def test_root_factory_dispatch_for_all_47_ids_no_execution(self):
        for app_id, app in APP_ENTRIES.items():
            with self.subTest(app_id=app_id):
                target = describe_native_root_factory(app_id)
                self.assertTrue(target['registered_target'])
                self.assertEqual(target['factory_address'], app['factory'])
                self.assertEqual(target['class_name'], app['class_name'])
                self.assertEqual(target['factory_table_entry'],
                                 0x6217E0 + 4 * app_id)
                self.assertEqual(target['native_root_handoff_function'],
                                 0x3F1BA0)
                self.assertEqual(target['native_indirect_factory_callsite'],
                                 0x3F1BE0)
                self.assertEqual(target['active_root_pointer_slot'],
                                 0x63BE38)
                self.assertEqual(target['fallback_pointer'], 0x4FCAD4)
                self.assertTrue(
                    target['would_attempt_factory_if_native_path_runs'])
                self.assertFalse(target['factory_executed'])
                self.assertFalse(target['active_root_pointer_written'])
        for app_id in (0, 48, 255):
            with self.subTest(invalid_id=app_id):
                fallback = describe_native_root_factory(app_id)
                self.assertFalse(fallback['registered_target'])
                self.assertFalse(
                    fallback['would_attempt_factory_if_native_path_runs'])
                self.assertIsNone(fallback['factory_table_entry'])
                self.assertIsNone(fallback['native_indirect_factory_callsite'])
                self.assertEqual(fallback['fallback_pointer'], 0x5E1AC0)
        for invalid_id in (-1, 256, True, '3'):
            with self.assertRaises(ValueError):
                describe_native_root_factory(invalid_id)

    def test_phase_five_root_handoff_is_state_and_parent_gated(self):
        accepted = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=48, pending_id=3,
            flags=0, callback_result=True, status_word=0)
        self.assertTrue(accepted['callback_eligible'])
        self.assertTrue(accepted['native_root_handoff_eligible'])
        self.assertEqual(accepted['native_root_handoff_callsite'], 0x3DFF34)
        self.assertEqual(accepted['root_factory']['factory_address'],
                         APP_ENTRIES[3]['factory'])
        self.assertEqual(accepted['next_phase'], 5)
        self.assertFalse(accepted['factory_executed'])
        self.assertFalse(accepted['callback_executed'])

        nested = inspect_native_phase_five_root_handoff(
            6, parent_id=3, child_id=48, pending_id=7,
            flags=0, callback_result=True, status_word=0)
        self.assertEqual(nested['next_phase'], 6)
        self.assertFalse(nested['native_root_handoff_eligible'])
        self.assertIsNone(nested['root_factory'])

        child_active = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=4, pending_id=3,
            flags=0, callback_result=True)
        self.assertFalse(child_active['callback_eligible'])
        self.assertFalse(child_active['native_root_handoff_eligible'])
        self.assertIsNone(child_active['callback_callsite'])

        suppressed = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=4, pending_id=3,
            flags=4, callback_result=True)
        self.assertTrue(suppressed['callback_eligible'])
        self.assertTrue(suppressed['native_root_handoff_eligible'])

        busy = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=48, pending_id=3,
            flags=0, callback_result=True, status_word=0x80000000)
        self.assertFalse(busy['native_root_handoff_eligible'])
        failed = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=48, pending_id=3,
            flags=0, callback_result=False)
        self.assertFalse(failed['native_root_handoff_eligible'])
        unknown = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=48, pending_id=3, flags=0)
        self.assertTrue(unknown['needs_callback_observation'])
        self.assertIsNone(unknown['root_factory'])
        invalid = inspect_native_phase_five_root_handoff(
            6, parent_id=48, child_id=48, pending_id=48,
            flags=0, callback_result=True)
        self.assertTrue(invalid['native_root_handoff_eligible'])
        self.assertFalse(invalid['root_factory']['registered_target'])
        self.assertFalse(invalid['root_factory']['factory_executed'])

        for call in (
                lambda: inspect_native_phase_five_root_handoff(
                    48, 48, 48, 3, 0, True),
                lambda: inspect_native_phase_five_root_handoff(
                    6, 49, 48, 3, 0, True),
                lambda: inspect_native_phase_five_root_handoff(
                    6, 48, 48, -1, 0, True),
                lambda: inspect_native_phase_five_root_handoff(
                    6, 48, 48, 3, 0, 1),
                lambda: inspect_native_phase_five_root_handoff(
                    6, 48, 48, 3, 0, True, -1),
        ):
            with self.assertRaises(ValueError):
                call()

    def test_evidence_is_unambiguous_and_unknown_ids_rejected(self):
        lifecycle = APP_NATIVE_REGISTRY['native_lifecycle']
        self.assertEqual(len(lifecycle['phase_virtual_dispatch']), 4)
        self.assertEqual(len(lifecycle['transition_phase_switch']['targets']), 7)
        self.assertGreaterEqual(len(lifecycle['instruction_signatures']), 56)
        for app_id in (0, 48, -1, True, '3'):
            with self.subTest(app_id=app_id):
                with self.assertRaises(ValueError):
                    describe_native_phase(app_id, 2)
        for call in (
                lambda: describe_native_phase(3, 7),
                lambda: inspect_native_phase_gate(3, 5, True, 0, 0),
                lambda: inspect_native_phase_gate(3, 2, 1, 0, 0),
                lambda: inspect_native_phase_gate(3, 2, True, 0, -1),
                lambda: inspect_native_transition_request(3, 3, 256, 6),
                lambda: inspect_native_transition_request(3, 3, 0, 0),
                lambda: inspect_native_child_successor(6, 4, 8, 7),
                lambda: inspect_native_child_successor(6, 4, 6, 49),
        ):
            with self.assertRaises(ValueError):
                call()


if __name__ == '__main__':
    unittest.main()
