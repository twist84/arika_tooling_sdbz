"""Deterministic tests for the evidence-bounded EU-beta kind-6 model."""

import copy
import json
from pathlib import Path
import unittest

from arika_native_stage_state_runtime import c_native_stage_state_runtime
from arika_stages import parse_stg
from test_arika_native_stage_controls import (
    controlled_stage_fixture, gltf_stage_nodes,
)


def independent_controls_scene():
    scene = parse_stg(controlled_stage_fixture())
    source = scene['nodes']
    second = copy.deepcopy(source[2])
    first_target = copy.deepcopy(source[3])
    second_target = copy.deepcopy(source[4])
    second.update(index=5, name='SWITCH_2', offset=0x150, children=[6, 7])
    second['state_control'].update(
        primary_name='LIVE_2', primary_node=6,
        secondary_name='SWAPPED_2', secondary_node=7,
    )
    first_target.update(index=6, name='LIVE_2', offset=0x180, children=[])
    second_target.update(index=7, name='SWAPPED_2', offset=0x1B0, children=[])
    scene['nodes'][1]['children'].append(5)
    scene['nodes'].extend((second, first_target, second_target))
    return scene


class NativeStageRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scene = parse_stg(controlled_stage_fixture())
        self.document = gltf_stage_nodes(self.scene)

    def test_constructor_and_loader_masks_use_original_target_roles(self):
        runtime = c_native_stage_state_runtime(self.scene)
        state = runtime.snapshot()
        self.assertEqual(state['controllers'][2]['phase'], 0)
        self.assertIsNone(state['controllers'][2]['countdown'])
        self.assertIsNone(state['controllers'][2]['countdown_source'])
        self.assertEqual(state['target_flags'], {3: 0, 4: 0x300})
        self.assertFalse(state['original_runtime_executed'])
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [4])

    def test_phase_gate_and_one_shot_callback_are_deterministic(self):
        runtime = c_native_stage_state_runtime(self.scene)
        self.assertFalse(runtime.switch(2)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 0)
        self.assertFalse(runtime.observe_timer_ready(2)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 0)
        self.assertTrue(runtime.observe_timer_ready(2, diagnostic=True)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 1)
        self.assertTrue(runtime.switch(2)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 2)
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0x300, 4: 0})
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [3])
        self.assertFalse(runtime.switch(2)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 2)

    def test_restore_is_separate_from_gate_and_reset_is_editor_only(self):
        runtime = c_native_stage_state_runtime(self.scene)
        runtime.observe_timer_ready(2, diagnostic=True)
        runtime.switch(2)
        self.assertTrue(runtime.restore(2)['applied'])
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0, 4: 0x300})
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 2)
        state = runtime.reset_to_initial()
        self.assertEqual(state['controllers'][2]['phase'], 0)
        self.assertEqual(state['event_count'], 0)
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [4])

    def test_no_invented_frames_or_countdown_decrement(self):
        runtime = c_native_stage_state_runtime(
            self.scene, countdown_sources={2: 14})
        before = runtime.snapshot()
        self.assertFalse(runtime.advance(100)['applied'])
        self.assertEqual(runtime.snapshot(), before)
        self.assertFalse(runtime.reset_countdown_callback(2)['applied'])
        self.assertTrue(runtime.reset_countdown_callback(
            2, diagnostic=True)['applied'])
        self.assertEqual(runtime.snapshot()['controllers'][2]['countdown'], 14)
        self.assertEqual(runtime.snapshot()['controllers'][2]['phase'], 0)
        self.assertEqual(runtime.advance(3)['original_clock_emulated'], False)
        self.assertEqual(runtime.snapshot()['controllers'][2]['countdown'], 14)
        with self.assertRaises(ValueError):
            runtime.advance(0)

    def test_event_reset_mask_and_unresolved_helper_are_distinct(self):
        runtime = c_native_stage_state_runtime(self.scene)
        runtime.observe_timer_ready(2, diagnostic=True)
        runtime.switch(2)
        self.assertFalse(runtime.callback(2, 0x20, True)['applied'])
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0x300, 4: 0})
        self.assertTrue(runtime.callback(2, 0x08000020)['applied'])
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0, 4: 0x300})
        self.assertFalse(runtime.callback(2, 0)['applied'])

    def test_independent_controller_phases_and_flags(self):
        scene = independent_controls_scene()
        document = gltf_stage_nodes(scene)
        runtime = c_native_stage_state_runtime(scene)
        self.assertEqual(set(runtime.snapshot()['controllers']), {2, 5})
        self.assertEqual(runtime.preview(document)['hidden_gltf_nodes'], [4, 7])
        runtime.observe_timer_ready(5, diagnostic=True)
        runtime.switch(5)
        state = runtime.snapshot()
        self.assertEqual(state['controllers'][2]['phase'], 0)
        self.assertEqual(state['controllers'][5]['phase'], 2)
        self.assertEqual(state['target_flags'], {
            3: 0, 4: 0x300, 6: 0x300, 7: 0})
        self.assertEqual(runtime.preview(document)['hidden_gltf_nodes'], [4, 6])

    def test_unresolved_targets_do_not_crash_or_hide_other_geometry(self):
        scene = copy.deepcopy(self.scene)
        scene['nodes'][2]['state_control'].update(
            secondary_node=None, secondary_name='NOT_FOUND')
        runtime = c_native_stage_state_runtime(scene)
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0})
        runtime.observe_timer_ready(2, diagnostic=True)
        runtime.switch(2)
        self.assertEqual(runtime.snapshot()['target_flags'], {3: 0x300})
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [3])
        self.assertTrue(runtime.snapshot()['unresolved'])

    def test_shared_target_conflicts_never_hide_ambiguous_geometry(self):
        scene = copy.deepcopy(self.scene)
        scene['nodes'][2]['state_control']['secondary_node'] = 3
        runtime = c_native_stage_state_runtime(scene)
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [])
        runtime.observe_timer_ready(2, diagnostic=True)
        runtime.switch(2)
        self.assertEqual(runtime.preview(self.document)['hidden_gltf_nodes'], [])

    def test_flag_preservation_and_document_immutability(self):
        source_before = copy.deepcopy(self.scene)
        doc_before = copy.deepcopy(self.document)
        runtime = c_native_stage_state_runtime(
            self.scene, initial_target_flags={
                3: 0xA0000123, 4: 0x4000020A,
            })
        self.assertEqual(runtime.snapshot()['target_flags'][3], 0xA0000023)
        self.assertEqual(runtime.snapshot()['target_flags'][4], 0x4000030A)
        runtime.observe_timer_ready(2, diagnostic=True)
        runtime.switch(2)
        self.assertEqual(runtime.snapshot()['target_flags'][3], 0xA0000323)
        self.assertEqual(runtime.snapshot()['target_flags'][4], 0x4000000A)
        runtime.preview(self.document)
        self.assertEqual(self.scene, source_before)
        self.assertEqual(self.document, doc_before)

    def test_source_offset_mapping_rejects_duplicates_and_collision_clones(self):
        runtime = c_native_stage_state_runtime(self.scene)
        changed = copy.deepcopy(self.document)
        changed['nodes'].append(copy.deepcopy(changed['nodes'][4]))
        result = runtime.preview(changed)
        self.assertEqual(result['hidden_gltf_nodes'], [])
        self.assertEqual(len(result['skipped_mappings']), 1)
        changed['nodes'][5]['name'] = 'collision:SWAPPED'
        result = runtime.preview(changed)
        self.assertEqual(result['hidden_gltf_nodes'], [4])

    def test_reject_malformed_input_and_controller_keys(self):
        with self.assertRaises(ValueError):
            c_native_stage_state_runtime(self.scene, countdown_sources={2: -1})
        with self.assertRaises(ValueError):
            c_native_stage_state_runtime(self.scene, initial_target_flags={999: 0})
        runtime = c_native_stage_state_runtime(self.scene)
        for func in (runtime.switch, runtime.restore):
            with self.assertRaises(ValueError):
                func(999)
        with self.assertRaises(ValueError):
            runtime.callback(2, -1)

    def test_machine_readable_graph_has_provenance_and_unknowns(self):
        graph = json.loads((Path(__file__).parent /
                            'research/native_stage_kind6_transitions.json').read_text())
        self.assertEqual(graph['target']['region'], 'EU beta')
        self.assertFalse(graph['provenance']['live_ee_trace'])
        by_id = {node['id']: node for node in graph['transitions']}
        self.assertEqual(by_id['phase_gated_switch']['predicate'],
                         'controller+0x54 == 1')
        self.assertEqual(by_id['timer_ready']['confidence'], 'effect-only')
        self.assertTrue(graph['unresolved'])


if __name__ == '__main__':
    unittest.main()
