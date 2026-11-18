"""Test original EU-beta stage switch/reset instruction branches and previews."""
import copy
import importlib.util
import os
from pathlib import Path
import unittest

from arika_native_stage_state_switch import (
    ELF_SWITCH_WORDS, ELF_LIFECYCLE_WORDS, ELF_VTABLE_WORDS,
    EVENT_RESET_FLAG, EVENT_SECONDARY_FLAG, SCENARIO_NAMES,
    inspect_native_stage_event_callback, inspect_native_stage_scenario,
    native_stage_scenario_preview_hidden_nodes, verify_native_stage_switch_elf,
)
from arika_stages import parse_stg
from test_arika_native_stage_controls import (
    controlled_stage_fixture, gltf_stage_nodes,
)


class NativeStageSwitchTests(unittest.TestCase):
    def setUp(self):
        self.scene = parse_stg(controlled_stage_fixture())
        self.document = gltf_stage_nodes(self.scene)

    def test_original_initial_and_direct_restore_are_distinct_evidence(self):
        initial = inspect_native_stage_scenario(self.scene, 'initial')
        restored = inspect_native_stage_scenario(self.scene, 'restored')
        self.assertEqual(initial['native_callback'], 0x240290)
        self.assertEqual(restored['native_callback'], 0x240910)
        self.assertEqual(initial['preview_suppressed_root_nodes'], [4])
        self.assertEqual(restored['preview_suppressed_root_nodes'], [4])
        self.assertEqual(restored['preview_suppressed_stage_nodes'], [4])
        self.assertEqual([x['operation'] for x in restored['native_mask_actions']],
                         ['clear', 'set'])
        self.assertEqual([x['elf_instruction_site']
                          for x in restored['native_mask_actions']],
                         [0x240940, 0x240970])
        self.assertFalse(initial['runtime_transition_observed'])
        self.assertFalse(restored['runtime_transition_observed'])

    def test_phase_one_required_before_hypothetical_switched_state(self):
        for phase_word in (None, 0, 2):
            with self.subTest(phase_word=phase_word):
                blocked = inspect_native_stage_scenario(
                    self.scene, 'switched', phase_word)
                self.assertFalse(blocked['phase_gate_satisfied'])
                self.assertEqual(blocked['preview_suppressed_root_nodes'], [])
                self.assertEqual(blocked['native_mask_actions'], [])
                self.assertTrue(blocked['conflicts_or_unresolved'])
                self.assertFalse(blocked['runtime_transition_observed'])
        switch = inspect_native_stage_scenario(self.scene, 'switched', 1)
        self.assertEqual(switch['native_callback'], 0x240710)
        self.assertTrue(switch['phase_gate_satisfied'])
        self.assertTrue(switch['outcome_inferred_from_assumed_state'])
        self.assertEqual(switch['preview_suppressed_root_nodes'], [3])
        self.assertEqual(switch['preview_suppressed_stage_nodes'], [3])
        self.assertEqual([x['operation'] for x in switch['native_mask_actions']],
                         ['set', 'clear'])
        self.assertEqual([x['elf_instruction_site']
                          for x in switch['native_mask_actions']],
                         [0x240750, 0x240788])
        self.assertFalse(switch['native_render_visibility_proven'])
        self.assertFalse(switch['native_collision_suppression_proven'])

    def test_switch_preview_does_not_persist_into_source_document(self):
        before = copy.deepcopy(self.document)
        initial = native_stage_scenario_preview_hidden_nodes(
            self.scene, self.document, 'initial')
        switched = native_stage_scenario_preview_hidden_nodes(
            self.scene, self.document, 'switched', assumed_phase_word=1)
        restored = native_stage_scenario_preview_hidden_nodes(
            self.scene, self.document, 'restored')
        self.assertEqual(initial['hidden_gltf_nodes'], [4])
        self.assertEqual(switched['hidden_gltf_nodes'], [3])
        self.assertEqual(restored['hidden_gltf_nodes'], [4])
        self.assertEqual(self.document, before)
        for result in (initial, switched, restored):
            self.assertTrue(result['preview_only'])
            self.assertFalse(result['stage_state']['runtime_transition_observed'])
            self.assertFalse(result['source_document_mutated'])
        blocked = native_stage_scenario_preview_hidden_nodes(
            self.scene, self.document, 'switched')
        self.assertEqual(blocked['hidden_gltf_nodes'], [])

    def test_source_offsets_guard_switched_state_after_duplicate_or_delete(self):
        doc = copy.deepcopy(self.document)
        doc['nodes'].append(copy.deepcopy(doc['nodes'][3]))
        result = native_stage_scenario_preview_hidden_nodes(
            self.scene, doc, 'switched', assumed_phase_word=1)
        self.assertEqual(result['hidden_gltf_nodes'], [])
        self.assertEqual(len(result['skipped_mappings']), 1)
        doc['nodes'][3]['extras']['stg_offset'] = -1
        result = native_stage_scenario_preview_hidden_nodes(
            self.scene, doc, 'switched', assumed_phase_word=1)
        self.assertEqual(result['hidden_gltf_nodes'], [5])
        doc['nodes'][5]['extras']['stg_offset'] = -1
        result = native_stage_scenario_preview_hidden_nodes(
            self.scene, doc, 'switched', assumed_phase_word=1)
        self.assertEqual(result['hidden_gltf_nodes'], [])

    def test_conflicting_switched_target_never_hides_enabled_geometry(self):
        changed = copy.deepcopy(self.scene)
        changed['nodes'][2]['state_control']['secondary_node'] = 3
        switched = inspect_native_stage_scenario(changed, 'switched', 1)
        self.assertEqual(switched['preview_suppressed_root_nodes'], [])
        self.assertEqual(switched['preview_suppressed_stage_nodes'], [])
        self.assertTrue(any('overlaps enabled' in warning
                            for warning in switched['conflicts_or_unresolved']))

    def test_direct_event_handler_branch_is_not_assumed_runtime_event(self):
        no_action = inspect_native_stage_event_callback(0)
        self.assertFalse(no_action['reset_mask_path'])
        self.assertFalse(no_action['secondary_mask_helper_eligible'])
        self.assertFalse(no_action['native_event_executed'])
        reset = inspect_native_stage_event_callback(EVENT_RESET_FLAG)
        self.assertTrue(reset['reset_mask_path'])
        self.assertTrue(reset['initial_mask_assignment_eligible'])
        self.assertFalse(reset['secondary_mask_helper_eligible'])
        self.assertFalse(reset['render_or_collision_effect_proven'])
        alternate = inspect_native_stage_event_callback(
            EVENT_SECONDARY_FLAG, True)
        self.assertFalse(alternate['reset_mask_path'])
        self.assertEqual(alternate['secondary_mask_helper'], 0x1ABD30)
        self.assertEqual(alternate['helper_mask'], 0x10)
        alternate_false = inspect_native_stage_event_callback(
            EVENT_SECONDARY_FLAG, False)
        self.assertEqual(alternate_false['secondary_mask_helper'], 0x1ABD70)
        unknown = inspect_native_stage_event_callback(EVENT_SECONDARY_FLAG)
        self.assertIsNone(unknown['secondary_mask_helper'])
        # Reset flag wins even when unrelated 0x20 is present.
        both = inspect_native_stage_event_callback(
            EVENT_RESET_FLAG | EVENT_SECONDARY_FLAG, True)
        self.assertTrue(both['reset_mask_path'])
        self.assertIsNone(both['secondary_mask_helper'])

    def test_invalid_mode_and_input_are_rejected(self):
        self.assertEqual(SCENARIO_NAMES, ('initial', 'switched', 'restored'))
        with self.assertRaises(ValueError):
            inspect_native_stage_scenario(self.scene, 'destroyed', 1)
        for value in (-1, 0x100000000, True, '1'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    inspect_native_stage_scenario(self.scene, 'switched', value)
                with self.assertRaises(ValueError):
                    inspect_native_stage_event_callback(value)
        with self.assertRaises(ValueError):
            inspect_native_stage_event_callback(0, '1')

    def test_original_elf_guard_is_independent_of_render_preview(self):
        self.assertGreaterEqual(len(ELF_SWITCH_WORDS), 25)
        self.assertEqual(ELF_SWITCH_WORDS[0x240724], 0x10620003)
        self.assertEqual(ELF_SWITCH_WORDS[0x240754], 0xAC620028)
        self.assertEqual(ELF_SWITCH_WORDS[0x240A08], 0x1440000F)
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            verify_native_stage_switch_elf(b'incorrect ELF')

    def test_native_constructor_vtable_and_phase_ready_chain(self):
        self.assertEqual(len(ELF_LIFECYCLE_WORDS), 10)
        self.assertEqual(ELF_LIFECYCLE_WORDS[0x23CCF4], 0x0C0900A4)
        self.assertEqual(ELF_LIFECYCLE_WORDS[0x240C38], 0x24427110)
        self.assertEqual(ELF_LIFECYCLE_WORDS[0x240C78], 0xAC800054)
        self.assertEqual(ELF_LIFECYCLE_WORDS[0x2404B0], 0xAE020054)
        self.assertEqual(ELF_VTABLE_WORDS, {0x4E7128: 0x240710})
        self.assertEqual(
            inspect_native_stage_scenario(
                self.scene, 'switched', 1)['native_callback'], 0x240710)

    def test_optional_exact_eu_beta_opcode_oracle(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact original EU-beta ELF not distributed in CI')
        data = Path(path).read_bytes()
        result = verify_native_stage_switch_elf(data)
        self.assertEqual(result['verified_initial_words'], 18)
        self.assertEqual(result['verified_switch_words'], len(ELF_SWITCH_WORDS))
        self.assertEqual(result['verified_lifecycle_words'],
                         len(ELF_LIFECYCLE_WORDS))
        self.assertEqual(result['verified_vtable_slots'], 1)
        self.assertFalse(result['original_runtime_executed'])

    @unittest.skipUnless(
        all(importlib.util.find_spec(name) for name in
            ('PySide6', 'wgpu', 'rendercanvas')),
        'Qt/WebGPU scene-editor dependencies required')
    def test_editor_switch_and_restore_scenarios_are_nonpersistent(self):
        from types import SimpleNamespace
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6 import QtWidgets as W
        from arika_scene_editor import c_scene_editor

        app = W.QApplication.instance() or W.QApplication([])
        editor = c_scene_editor()
        doc = copy.deepcopy(self.document)
        project = SimpleNamespace(
            m_stage=SimpleNamespace(m_scene=self.scene),
            m_document=doc,
            m_background_preset=None,
            background_rgba=lambda: None,
        )
        try:
            editor.m_project = project
            editor.m_view.set_project(project)
            editor.m_object_view.set_project(project)
            previous = copy.deepcopy(doc)
            editor.m_native_stage_state_action.setChecked(True)
            self.assertEqual(editor.m_view.effective_hidden_nodes(), {4})
            editor.set_native_stage_scenario('switched')
            self.assertEqual(editor.m_view.effective_hidden_nodes(), {3})
            self.assertEqual(editor.m_object_view.effective_hidden_nodes(), {3})
            self.assertTrue(
                editor.m_native_state_actions['switched'].isChecked())
            self.assertIn('hypothetical phase', editor.statusBar().currentMessage())
            editor.set_native_stage_scenario('restored')
            self.assertEqual(editor.m_view.effective_hidden_nodes(), {4})
            editor.m_native_stage_state_action.setChecked(False)
            self.assertEqual(editor.m_view.effective_hidden_nodes(), set())
            self.assertEqual(doc, previous)
        finally:
            editor.m_project = None
            editor.close()
            app.processEvents()


if __name__ == '__main__':
    unittest.main()
