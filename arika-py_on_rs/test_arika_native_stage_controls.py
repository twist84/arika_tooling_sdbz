"""Regression tests for native stage kind-6 initial state mask diagnostics."""
import copy
import importlib.util
import os
from pathlib import Path
import struct
import unittest

from arika_native_stage_controls import (
    ELF_INITIAL_WORDS, INITIAL_MASK,
    inspect_native_initial_stage_state, native_initial_preview_hidden_nodes,
    verify_native_stage_control_elf,
)
from arika_stages import parse_stg


def controlled_stage_fixture():
    names = ['EFFECT', 'STAGE', 'SWITCH', 'LIVE', 'SWAPPED']
    data = (b'\x00\x01\x00\x00STG ' +
            struct.pack('<2I', len(names), 0) +
            b''.join(name.encode().ljust(16, b'\x00') for name in names))
    def node(kind, index, links):
        return (struct.pack('<4BI', kind, 0, links, 0, index) +
                struct.pack('<9f', 0, 0, 0, 0, 0, 0, 1, 1, 1))
    def control():
        return (struct.pack('<4BI', 6, 0, 1, 0, 2) +
                bytes(36) + struct.pack('<4i', 3, 4, 0, 0))
    return (data + node(1, 0, 0) + node(1, 1, 1) +
            control() + node(2, 3, 2) + node(2, 4, 0))


def gltf_stage_nodes(scene):
    return {
        'nodes': [
            dict(name=node['name'], extras=dict(
                stg_offset=node['offset'], kind=node['kind']),
                children=list(node['children']))
            for node in scene['nodes']
        ],
        'scenes': [dict(nodes=[scene['stage_root']])],
        'scene': 0,
    }


class NativeStageInitialStateTests(unittest.TestCase):
    def test_real_parser_resolves_first_descendant_control_targets(self):
        scene = parse_stg(controlled_stage_fixture())
        self.assertEqual(scene['roots'], [0, 1])
        control = scene['nodes'][2]['state_control']
        self.assertEqual(control['primary_name'], 'LIVE')
        self.assertEqual(control['secondary_name'], 'SWAPPED')
        self.assertEqual(control['primary_node'], 3)
        self.assertEqual(control['secondary_node'], 4)
        result = inspect_native_initial_stage_state(scene)
        self.assertEqual(result['native_control_count'], 1)
        self.assertEqual(result['mask'], 0x300)
        self.assertEqual(result['runtime_flag_offset'], 0x28)
        self.assertEqual(result['preview_suppressed_root_nodes'], [4])
        self.assertEqual(result['preview_suppressed_stage_nodes'], [4])
        self.assertEqual(result['conflicts_or_unresolved'], [])
        self.assertEqual(result['native_mask_actions'], [
            dict(controller_node=2, target_node=3, target_name='LIVE',
                 role='primary', operation='clear', mask=768,
                 runtime_flag_offset=40, elf_instruction_site=0x2402C0,
                 original_target_lookup='first_depth_first'),
            dict(controller_node=2, target_node=4, target_name='SWAPPED',
                 role='secondary', operation='set', mask=768,
                 runtime_flag_offset=40, elf_instruction_site=0x2402F4,
                 original_target_lookup='first_depth_first'),
        ])
        self.assertTrue(result['preview_only'])
        self.assertFalse(result['native_render_visibility_proven'])
        self.assertFalse(result['native_collision_suppression_proven'])

    def test_preview_never_modifies_original_document_or_stage(self):
        scene = parse_stg(controlled_stage_fixture())
        doc = gltf_stage_nodes(scene)
        before = copy.deepcopy(doc)
        result = native_initial_preview_hidden_nodes(scene, doc)
        self.assertEqual(result['hidden_gltf_nodes'], [4])
        self.assertEqual(result['skipped_mappings'], [])
        self.assertEqual(doc, before)
        self.assertFalse(result['source_document_mutated'])
        self.assertTrue(result['preview_only'])
        self.assertEqual(INITIAL_MASK, 768)

    def test_collision_clones_are_left_unmodified_and_visible(self):
        scene = parse_stg(controlled_stage_fixture())
        doc = gltf_stage_nodes(scene)
        original = scene['nodes'][4]
        doc['nodes'].append({
            'name': 'collision:SWAPPED',
            'extras': {'stg_offset': original['offset'], 'kind': 2},
        })
        result = native_initial_preview_hidden_nodes(scene, doc)
        self.assertEqual(result['hidden_gltf_nodes'], [4])
        self.assertNotIn(5, result['hidden_gltf_nodes'])

    def test_duplicate_or_deleted_glTF_source_nodes_not_arbitrarily_hidden(self):
        scene = parse_stg(controlled_stage_fixture())
        doc = gltf_stage_nodes(scene)
        doc['nodes'].append(copy.deepcopy(doc['nodes'][4]))
        result = native_initial_preview_hidden_nodes(scene, doc)
        self.assertEqual(result['hidden_gltf_nodes'], [])
        self.assertEqual(len(result['skipped_mappings']), 1)
        doc['nodes'][4]['extras']['stg_offset'] = -1
        result = native_initial_preview_hidden_nodes(scene, doc)
        self.assertEqual(result['hidden_gltf_nodes'], [5])
        self.assertEqual(result['skipped_mappings'], [])
        doc['nodes'][5]['extras']['stg_offset'] = -1
        result = native_initial_preview_hidden_nodes(scene, doc)
        self.assertEqual(result['hidden_gltf_nodes'], [])
        self.assertEqual(len(result['skipped_mappings']), 1)

    def test_conflicting_primary_secondary_masks_do_not_hide_important_nodes(self):
        scene = parse_stg(controlled_stage_fixture())
        modified = copy.deepcopy(scene)
        modified['nodes'][2]['state_control']['primary_node'] = 4
        result = inspect_native_initial_stage_state(modified)
        self.assertEqual(result['preview_suppressed_root_nodes'], [])
        self.assertEqual(result['preview_suppressed_stage_nodes'], [])
        self.assertEqual(len(result['conflicts_or_unresolved']), 1)

    def test_templates_do_not_affect_live_stage_initial_state(self):
        scene = parse_stg(controlled_stage_fixture())
        scene['nodes'][2]['state_control']['primary_name'] = None
        scene['nodes'][2]['state_control']['primary_node'] = None
        scene['nodes'][2]['state_control']['secondary_name'] = None
        scene['nodes'][2]['state_control']['secondary_node'] = None
        result = inspect_native_initial_stage_state(scene)
        self.assertEqual(result['preview_suppressed_stage_nodes'], [])
        self.assertEqual(result['native_mask_actions'], [])

    def test_unresolved_and_invalid_target_are_separate(self):
        scene = parse_stg(controlled_stage_fixture())
        missing = copy.deepcopy(scene)
        missing['nodes'][2]['state_control']['secondary_node'] = None
        result = inspect_native_initial_stage_state(missing)
        self.assertEqual(result['preview_suppressed_stage_nodes'], [])
        self.assertEqual(len(result['conflicts_or_unresolved']), 1)
        foreign = copy.deepcopy(scene)
        foreign['nodes'][2]['state_control']['secondary_node'] = 0
        result = inspect_native_initial_stage_state(foreign)
        self.assertEqual(result['preview_suppressed_stage_nodes'], [])
        self.assertEqual(len(result['conflicts_or_unresolved']), 1)

    def test_exact_elf_instruction_table_has_no_fabricated_runtime_trace(self):
        self.assertEqual(len(ELF_INITIAL_WORDS), 18)
        self.assertEqual(ELF_INITIAL_WORDS[0x2402B4], 0x2403FCFF)
        self.assertEqual(ELF_INITIAL_WORDS[0x2402F4], 0x34420300)
        self.assertEqual(ELF_INITIAL_WORDS[0x240878], 0x30630300)
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            verify_native_stage_control_elf(b'not an original ELF')

    def test_exact_beta_elf_oracle_optional(self):
        path=os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact original EU-beta ELF not distributed in CI')
        original=Path(path).read_bytes()
        result=verify_native_stage_control_elf(original)
        self.assertEqual(result['verified_original_instruction_words'],18)
        self.assertEqual(result['mask'],0x300)
        self.assertFalse(result['runtime_execution_proven'])
        corrupt=bytearray(original)
        corrupt[0x240878-0xFFF80]^=1
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            verify_native_stage_control_elf(bytes(corrupt))

    @unittest.skipUnless(
        all(importlib.util.find_spec(name) for name in
            ('PySide6', 'wgpu', 'rendercanvas')),
        'Qt/WebGPU scene-editor dependencies required')
    def test_editor_toggle_is_read_only_and_restores_authored_hiding(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from types import SimpleNamespace
        from PySide6 import QtWidgets as W
        from arika_scene_editor import c_scene_editor
        app=W.QApplication.instance() or W.QApplication([])
        editor=c_scene_editor()
        scene=parse_stg(controlled_stage_fixture())
        document=gltf_stage_nodes(scene)
        # The preview must not depend on mesh resources or an active GPU.
        project=SimpleNamespace(
            m_stage=SimpleNamespace(m_scene=scene),
            m_document=document,
            m_background_preset=None,
            background_rgba=lambda:None,
        )
        try:
            editor.m_project=project
            editor.m_view.set_project(project)
            editor.m_object_view.set_project(project)
            self.assertEqual(editor.m_view.m_native_stage_hidden,{4})
            self.assertEqual(editor.m_view.effective_hidden_nodes(),set())
            original=copy.deepcopy(document)
            editor.m_native_stage_state_action.setChecked(True)
            self.assertTrue(editor.m_view.m_native_initial_state_preview)
            self.assertTrue(editor.m_object_view.m_native_initial_state_preview)
            self.assertEqual(editor.m_view.effective_hidden_nodes(),{4})
            self.assertEqual(editor.m_object_view.effective_hidden_nodes(),{4})
            self.assertIn('Diagnostic only',editor.statusBar().currentMessage())
            self.assertEqual(document,original)
            editor.m_native_stage_state_action.setChecked(False)
            self.assertEqual(editor.m_view.effective_hidden_nodes(),set())
            self.assertEqual(editor.m_object_view.effective_hidden_nodes(),set())
            self.assertEqual(document,original)
        finally:
            # The synthetic SimpleNamespace is not a c_scene_project and
            # has no save/dirty protocol. Remove it before closeEvent().
            editor.m_project=None
            editor.close()
            app.processEvents()

    def test_invalid_scene_and_cycles_rejected(self):
        with self.assertRaises(ValueError):
            inspect_native_initial_stage_state({'format': 'not stage'})
        scene = parse_stg(controlled_stage_fixture())
        scene['nodes'][4]['children'] = [2]
        with self.assertRaises(ValueError):
            inspect_native_initial_stage_state(scene)


if __name__ == '__main__':
    unittest.main()
