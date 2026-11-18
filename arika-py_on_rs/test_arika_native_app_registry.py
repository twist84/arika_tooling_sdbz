"""Deterministic 47-ID registry/graph checks; exact ELF oracle is opt-in."""
import copy
import json
import os
from pathlib import Path
import unittest

from arika_app_registry import (
    APP_ENTRIES, APP_FACTORIES, APP_NATIVE_REGISTRY, APP_REGISTRATION_SITES,
    APP_REGISTRY_COUNT, registered_native_requests, resolve_app,
)
from arika_native_app_extract import verify


class NativeAppRegistryTests(unittest.TestCase):
    def test_all_ids_and_nonnumeric_registration_order(self):
        self.assertEqual(APP_REGISTRY_COUNT, 47)
        self.assertEqual(set(APP_ENTRIES), set(range(1, 48)))
        self.assertEqual(len(APP_FACTORIES), 47)
        self.assertEqual(len(APP_REGISTRATION_SITES), 47)
        self.assertEqual(
            [a['id'] for a in APP_NATIVE_REGISTRY['applications']],
            APP_NATIVE_REGISTRY['registration_order'])
        self.assertNotEqual(APP_NATIVE_REGISTRY['registration_order'],
                            list(range(1, 48)))
        self.assertEqual(len(set(a['factory'] for a in APP_ENTRIES.values())), 47)
        self.assertEqual(len(set(a['constructor'] for a in APP_ENTRIES.values())), 47)

    def test_every_factory_registration_and_constructor_site(self):
        for app_id in range(1, 48):
            with self.subTest(id=app_id):
                record = resolve_app(app_id)
                app = APP_ENTRIES[app_id]
                self.assertEqual(record['factory'], app['factory'])
                self.assertEqual(record['registration_order'],
                                 app['registration_order'])
                self.assertEqual(record['constructor_callsite'],
                                 app['factory'] + 0x20)
                self.assertEqual(record['factory_table'],
                                 0x6217e0 + 4 * app_id)
                self.assertEqual(record['registration_callsite'],
                                 app['registration_callsite'])
                self.assertEqual(APP_REGISTRATION_SITES[app_id][1],
                                 app['factory_table_store_site'])
                self.assertEqual(record['name_address'],
                                 app['class_name_pointer'])
                self.assertTrue(record['class_name'].startswith('CApp'))
                self.assertEqual(len(record['base_slots']), 20)
                self.assertEqual(len(record['phase_slots']), 10)
                self.assertEqual(record['base_slots']['0x08'],
                                 record['name_getter'])
                self.assertEqual(record['callback_dispatch'],
                                 app['callback_dispatch'])
                self.assertFalse(record['factory_executed'])
                for offset in range(0x08, 0x30, 4):
                    base_key = '0x%02x' % (offset + 0x28)
                    phase_key = '0x%02x' % offset
                    self.assertEqual(record['base_slots'][base_key],
                                     record['phase_slots'][phase_key])
                self.assertEqual(record['base_slots']['0x28'], 0)
                self.assertEqual(record['base_slots']['0x2c'], 0)
                self.assertEqual(app['callback_dispatch']['phase_2'],
                                 record['base_slots']['0x38'])

    def test_shared_class_names_do_not_alias_native_objects(self):
        self.assertEqual(APP_ENTRIES[2]['class_name'], 'CAppCRISofdec')
        self.assertEqual(APP_ENTRIES[3]['class_name'], 'CAppTitleMain')
        self.assertEqual(APP_ENTRIES[5]['class_name'], 'CAppMonitorSelect')
        self.assertEqual(APP_ENTRIES[1]['class_name'], 'CAppWarning')
        self.assertEqual(APP_ENTRIES[42]['class_name'], 'CAppMenuMain')
        self.assertEqual(APP_ENTRIES[43]['class_name'], 'CAppShenronMain')
        for id_a, id_b in ((6, 8), (12, 13)):
            with self.subTest(first=id_a, second=id_b):
                self.assertEqual(APP_ENTRIES[id_a]['class_name'],
                                 APP_ENTRIES[id_b]['class_name'])
                for field in ('factory', 'constructor',
                              'base_vtable', 'phase_vtable'):
                    self.assertNotEqual(APP_ENTRIES[id_a][field],
                                        APP_ENTRIES[id_b][field])

    def test_110_instructions_and_request_types(self):
        calls = APP_NATIVE_REGISTRY['callsites']
        self.assertEqual(len(calls), 110)
        self.assertEqual(len({e['callsite'] for e in calls}), 110)
        counts = {kind: len(registered_native_requests(request_kind=kind))
                  for kind in ('transition', 'child_request', 'factory_lookup')}
        self.assertEqual(counts, {'transition': 41, 'child_request': 32,
                                  'factory_lookup': 37})
        self.assertEqual(sum(e['is_registered_destination'] for e in calls), 67)
        self.assertTrue(all(not e['requested_not_executed'] is False
                            for e in calls))
        self.assertEqual({e['target_id'] for e in calls if
                          e['target_id'] == 48}, {48})
        for edge in calls:
            with self.subTest(site=edge['callsite']):
                self.assertIn(edge['api'],
                              ('transition', 'child_request', 'factory_lookup'))
                self.assertEqual(edge['source_attribution_verified'],
                                 edge['callsite'] in (0x3E09E0, 0x3E4C54, 0x3E920C,
                                                       0x40BD0C))
                if edge['is_registered_destination']:
                    self.assertIn(edge['target_id'], APP_ENTRIES)
                    self.assertEqual(edge['target_class'],
                                     APP_ENTRIES[edge['target_id']]['class_name'])

    def test_graph_is_not_tab_order_or_automatic_factory_execution(self):
        progress = APP_NATIVE_REGISTRY['visible_progression']
        self.assertEqual([(e['from'], e['to']) for e in progress], [
            ('warning', 'startup'), ('startup', 'title'),
            ('title', 'press_start'), ('press_start', 'main_menu')])
        self.assertTrue(all(e['native_app_edge'] is False for e in progress))
        self.assertEqual(len(registered_native_requests(source_id=6,
                                                        request_kind='child_request')), 4)
        with self.assertRaises(ValueError):
            registered_native_requests(source_id=0)
        with self.assertRaises(ValueError):
            registered_native_requests(request_kind='fabricated')
        self.assertIsNone(resolve_app(0))
        self.assertIsNone(resolve_app(48))
        with self.assertRaises(ValueError):
            resolve_app(True)

    def test_conditional_demo_exit_and_generic_successor_are_distinct(self):
        relationships = APP_NATIVE_REGISTRY['relationships']
        self.assertEqual(len(relationships), 8)
        demo_exits = sorted(
            (e for e in relationships
             if e['type'] == 'conditional_native_transition_request'),
            key=lambda e: e['destination_id'])
        self.assertEqual([edge['destination_id'] for edge in demo_exits],
                         [3, 6])
        self.assertTrue(all(edge['source_id'] == 6
                            for edge in demo_exits))
        self.assertTrue(all(edge['native_callsite'] == 0x3E09E0
                            for edge in demo_exits))
        self.assertTrue(all(edge['confidence'] == 'exact_elf_conditional_target'
                            for edge in demo_exits))
        self.assertTrue(all(not edge['request_executed']
                            for edge in demo_exits))
        indirect = next(e for e in relationships
                        if e['type'] == 'indirect_dispatch')
        self.assertEqual(indirect['native_callsite'], 0x3F1C78)
        self.assertEqual(indirect['table_address'], 0x6217e0)
        self.assertFalse(indirect['request_executed'])
        self.assertTrue(all(not e['is_user_observed']
                            for e in relationships))
        successor = next(e for e in relationships
                         if e['type'] == 'child_completion_successor')
        self.assertEqual(successor['native_callsite'], 0x3DFF60)
        self.assertEqual(successor['confidence'],
                         'exact_elf_generic_dispatch')
        self.assertIsNone(successor['source_id'])
        self.assertIsNone(successor['destination_id'])
        self.assertFalse(successor['request_executed'])

    def test_demo_dynamic_exit_has_exact_field_and_instruction_evidence(self):
        demo = APP_NATIVE_REGISTRY['demo_main_exit']
        self.assertEqual(demo['app_id'], 6)
        self.assertEqual(demo['default_target_id'], 3)
        self.assertEqual(demo['alternate_target_id'], 6)
        self.assertEqual(demo['exit_target_byte'], 0x2A)
        self.assertEqual(demo['default_target_store'], 0x3E0478)
        self.assertEqual(demo['choice3_override_store'], 0x3E0970)
        self.assertEqual(demo['choice1_exit_flag_store'], 0x3E0960)
        self.assertEqual(demo['transition_callsite'], 0x3E09E0)
        self.assertEqual(demo['initialize_callback'],
                         APP_ENTRIES[6]['base_slots']['0x34'])
        self.assertEqual(demo['update_callback'],
                         APP_ENTRIES[6]['base_slots']['0x40'])
        self.assertEqual(len(demo['instruction_signatures']), 13)
        native_edge = next(e for e in APP_NATIVE_REGISTRY['callsites']
                           if e['callsite'] == 0x3E09E0)
        self.assertTrue(native_edge['source_attribution_verified'])
        self.assertEqual(native_edge['target_candidates'], [3, 6])
        self.assertIsNone(native_edge['target_id'])
        self.assertFalse(native_edge['is_registered_destination'])

    def test_fight_result_conditional_child_selector(self):
        fight = APP_NATIVE_REGISTRY['fight_result_dispatch']
        self.assertEqual(fight['source_id'], 28)
        self.assertEqual(fight['callback'],
                         APP_ENTRIES[28]['base_slots']['0x3c'])
        self.assertEqual(fight['helper_callsite'], 0x40BBB8)
        self.assertEqual(fight['dispatch_callsite'], 0x40BD0C)
        self.assertEqual(fight['default_target_sentinel'], 48)
        self.assertEqual(len(fight['evidence_sites']), 17)
        self.assertEqual(
            [record['target_id'] for record in fight['conditional_destinations']],
            [29, 30, 34, 38])
        edge = next(edge for edge in APP_NATIVE_REGISTRY['callsites']
                    if edge['callsite'] == 0x40BD0C)
        self.assertEqual(edge['api'], 'child_request')
        self.assertTrue(edge['source_attribution_verified'])
        self.assertEqual(edge['source_candidates'], [28])
        self.assertEqual(edge['target_candidates'], [29, 30, 34, 38])
        self.assertIsNone(edge['target_id'])
        self.assertFalse(edge['is_registered_destination'])
        self.assertEqual(edge['sentinel_target'], 48)
        children = [e for e in APP_NATIVE_REGISTRY['relationships']
                    if e['type'] == 'conditional_native_child_request']
        self.assertEqual(len(children), 4)
        self.assertEqual(sorted(e['destination_id'] for e in children),
                         [29, 30, 34, 38])
        self.assertTrue(all(e['source_id'] == 28 and
                            not e['request_executed'] for e in children))

    def test_every_native_transition_and_child_site_is_classified(self):
        requests = [edge for edge in APP_NATIVE_REGISTRY['callsites']
                    if edge['api'] in ('transition', 'child_request')]
        self.assertEqual(len(requests), 73)
        registered = [edge for edge in requests
                      if edge['is_registered_destination']]
        self.assertEqual(len(registered), 67)
        other = {edge['callsite']: edge for edge in requests
                 if not edge['is_registered_destination']}
        self.assertEqual(set(other), {
            0x3DFB8C, 0x3DFC1C, 0x3E09E0,
            0x3E4C54, 0x3E920C, 0x40BD0C,
        })
        for site in (0x3DFB8C, 0x3E4C54, 0x3E920C):
            with self.subTest(sentinel_site=site):
                self.assertEqual(other[site]['target_id'], 48)
                self.assertEqual(other[site]['api'], 'transition')
        self.assertEqual(other[0x3DFC1C]['argument_kind'],
                         'forwarded_caller_argument_a1')
        self.assertIsNone(other[0x3DFC1C]['target_id'])
        self.assertEqual(other[0x3E09E0]['target_candidates'], [3, 6])
        self.assertEqual(other[0x40BD0C]['target_candidates'],
                         [29, 30, 34, 38])
        self.assertEqual(other[0x40BD0C]['sentinel_target'], 48)
        self.assertEqual(sum(edge['source_attribution_verified']
                             for edge in other.values()), 4)
        self.assertEqual(len(APP_NATIVE_REGISTRY['callsites']) -
                         len(requests), 37)

    def test_root_factory_dispatch_has_real_jalr_not_inferred_request(self):
        root = APP_NATIVE_REGISTRY['native_root_factory_dispatch']
        self.assertEqual(root['scheduler_root_handoff_callsite'], 0x3DFF34)
        self.assertEqual(root['scheduler_handoff_id_load_site'], 0x3DFF38)
        self.assertEqual(root['root_handoff_function'], 0x3F1BA0)
        self.assertEqual(root['registry_init_callsite'], 0x3F1BAC)
        self.assertEqual(root['indirect_factory_callsite'], 0x3F1BE0)
        self.assertEqual(root['factory_table_base'], 0x6217E0)
        self.assertEqual(root['active_root_pointer_slot'], 0x63BE38)
        self.assertEqual(root['active_root_pointer_store_sites'],
                         [0x3F1C04, 0x3F1C30])
        self.assertEqual(root['factory_fallback_pointer'], 0x4FCAD4)
        self.assertEqual(root['invalid_id_fallback_pointer'], 0x5E1AC0)
        self.assertEqual(root['parent_sentinel'], 48)
        self.assertEqual((root['minimum_valid_id'],
                          root['maximum_valid_id']), (1, 47))
        self.assertEqual(len(root['instruction_signatures']), 40)
        self.assertFalse(root['factory_executed'])
        self.assertFalse(root['root_pointer_written_observed'])
        provider = root['instance_provider']
        self.assertEqual(provider['function'], 0x3F1C40)
        self.assertEqual(provider['registry_init_callsite'], 0x3F1C4C)
        self.assertEqual(provider['indirect_factory_callsite'], 0x3F1C78)
        self.assertEqual(provider['maximum_exclusive_id'], 48)
        self.assertEqual(provider['factory_table_base'], 0x6217E0)
        self.assertEqual(len(provider['signatures']), 9)
        self.assertFalse(provider['installs_active_root'])
        self.assertFalse(provider['factory_executed'])

    def test_generic_forward_and_sentinel_cancel_are_not_app_edges(self):
        native = APP_NATIVE_REGISTRY['cancel_and_forward_dispatch']
        self.assertEqual(native['native_sentinel_id'], 48)
        self.assertEqual(len(native['instruction_signatures']), 54)
        self.assertEqual(native['forwarded_child_request']['helper'],
                         0x3DFBD0)
        self.assertEqual(native['forwarded_child_request']['forward_site'],
                         0x3DFC1C)
        self.assertEqual(native['recursive_cancel']['site'], 0x3DFB8C)
        self.assertEqual(native['recursive_cancel']['guarded_phases'],
                         [1, 2, 3, 4])
        timer = native['fight_demo_end_timeout']
        single = native['fight_play_single_finish']
        self.assertEqual(timer['app_id'], 25)
        self.assertEqual(timer['threshold_float32_bits'], 0x3CA3D70A)
        self.assertEqual(timer['callback'],
                         APP_ENTRIES[25]['base_slots']['0x40'])
        self.assertEqual(timer['request_site'], 0x3E4C54)
        self.assertEqual(single['app_id'], 20)
        self.assertEqual(single['callback'],
                         APP_ENTRIES[20]['base_slots']['0x40'])
        self.assertEqual(single['state9_entry'], 0x3E91D4)
        self.assertEqual(single['request_site'], 0x3E920C)

        by_site = {edge['callsite']: edge
                   for edge in APP_NATIVE_REGISTRY['callsites']}
        for site in (0x3DFB8C, 0x3DFC1C, 0x3E4C54, 0x3E920C):
            with self.subTest(site=site):
                edge = by_site[site]
                self.assertEqual(edge['api'], 'transition')
                self.assertFalse(edge['is_registered_destination'])
                self.assertTrue(edge['condition_verified_by_elf'])
                self.assertFalse(edge['requested_not_executed'] is False)
        self.assertIsNone(by_site[0x3DFC1C]['target_id'])
        self.assertEqual(by_site[0x3DFC1C]['argument_site'], 0x3DFC14)
        self.assertEqual(by_site[0x3DFC1C]['source_function'], 0x3DFBD0)
        self.assertEqual(by_site[0x3DFB8C]['target_id'], 48)
        self.assertEqual(by_site[0x3E4C54]['source_candidates'], [25])
        self.assertEqual(by_site[0x3E920C]['source_candidates'], [20])
        self.assertFalse(by_site[0x3DFB8C]['source_attribution_verified'])
        self.assertFalse(by_site[0x3DFC1C]['source_attribution_verified'])
        self.assertTrue(by_site[0x3E4C54]['source_attribution_verified'])
        self.assertTrue(by_site[0x3E920C]['source_attribution_verified'])

    def test_warning_cri_cross_app_methods_do_not_imply_child_creation(self):
        edges = APP_NATIVE_REGISTRY['cross_app_interactions']
        self.assertEqual(len(edges), 4)
        self.assertEqual(
            [(e['source_id'], e['destination_id']) for e in edges],
            [(1, 2)] * 4)
        self.assertEqual([e['mechanism'] for e in edges], [
            'factory_lookup', 'direct_method_call',
            'factory_lookup', 'indirect_virtual_call'])
        self.assertEqual([e['callsite'] for e in edges],
                         [0x3FABF8, 0x3FAC00, 0x3FAC30, 0x3FAC40])
        self.assertEqual(edges[1]['callee'], 0x3F8780)
        self.assertEqual(edges[3]['vtable_load_site'], 0x3FAC3C)
        self.assertEqual(edges[3]['callback_target'],
                         APP_ENTRIES[2]['base_slots']['0x38'])
        for edge in edges:
            with self.subTest(site=edge['callsite']):
                self.assertEqual(edge['source_function'],
                                 APP_ENTRIES[1]['base_slots'][
                                     '0x3c' if edge['source_phase'] == 3
                                     else '0x40'])
                self.assertTrue(edge['verified_elf'])
                self.assertFalse(edge['child_construction_proven'])
                self.assertFalse(edge['runtime_executed'])

    def test_metadata_rejects_invalid_ids_and_duplicates(self):
        # Check a mutated snapshot with the exact ELF when supplied.
        elf_path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not elf_path:
            self.skipTest('original user-owned EU-beta ELF absent in CI')
        data = Path(elf_path).read_bytes()
        self.assertEqual(verify(data, APP_NATIVE_REGISTRY), {
            'verified_applications': 47,
            'verified_callsites': 110,
            'literal_registered_destinations': 67,
            'class_names': 45,
        })
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['applications'][1]['class_name'] = 'CAppTitleMain'
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['applications'][1]['id'] = 1
        with self.assertRaises(ValueError):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['callsites'][0]['callsite'] = corrupted['callsites'][1]['callsite']
        with self.assertRaises(ValueError):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['native_root_factory_dispatch']['instance_provider'][
            'indirect_factory_callsite'] += 4
        with self.assertRaisesRegex(ValueError, 'instance-provider'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['native_root_factory_dispatch']['active_root_pointer_slot'] += 4
        with self.assertRaisesRegex(ValueError, 'root factory'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['native_root_factory_dispatch'][
            'instruction_signatures']['0x003f1be0'] ^= 4
        with self.assertRaisesRegex(ValueError, 'root factory'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['cancel_and_forward_dispatch']['instruction_signatures'][
            '0x003e4c54'] ^= 4
        with self.assertRaisesRegex(ValueError, 'cancel/forward'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['cancel_and_forward_dispatch'][
            'fight_play_single_finish']['state9_entry'] += 4
        with self.assertRaisesRegex(ValueError, 'FightPlaySingle'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['demo_main_exit']['default_target_id'] = 42
        with self.assertRaisesRegex(ValueError, 'DemoMain'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['fight_result_dispatch']['conditional_destinations'][2]['target_id'] = 43
        with self.assertRaisesRegex(ValueError, 'FightResultMain'):
            verify(data, corrupted)
        corrupted = copy.deepcopy(APP_NATIVE_REGISTRY)
        corrupted['cross_app_interactions'][3]['callback_target'] += 4
        with self.assertRaisesRegex(ValueError, 'cross-app'):
            verify(data, corrupted)
        with self.assertRaisesRegex(ValueError, 'exact EU-beta'):
            verify(b'wrong ELF', APP_NATIVE_REGISTRY)


if __name__ == '__main__':
    unittest.main()
