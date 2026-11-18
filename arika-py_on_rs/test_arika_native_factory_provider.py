"""Regression checks for the full original EU-beta factory-provider audit."""
import copy
import os
from pathlib import Path
import unittest

from arika_app_registry import (
    APP_ENTRIES, APP_NATIVE_PROVIDER_AUDIT, APP_NATIVE_PROVIDER_CALLS,
    APP_NATIVE_REGISTRY, registered_factory_providers,
    registered_native_requests,
)
from arika_native_factory_provider_extract import verify_provider_audit


class NativeFactoryProviderTests(unittest.TestCase):
    def test_37_calls_have_independent_complete_argument_classification(self):
        audit = APP_NATIVE_PROVIDER_AUDIT
        self.assertEqual(audit['provider_entrypoint'], 0x3F1C40)
        self.assertEqual(audit['provider_indirect_factory_callsite'],
                         0x3F1C78)
        self.assertEqual(audit['provider_callsite_count'], 37)
        self.assertEqual(len(APP_NATIVE_PROVIDER_CALLS), 37)
        self.assertEqual(len(set(e['callsite']
                                 for e in APP_NATIVE_PROVIDER_CALLS)), 37)
        self.assertEqual(audit['classification_counts'], {
            'literal': 26,
            'child_id_byte': 9,
            'pending_id_byte': 1,
            'requested_child_id': 1,
        })
        self.assertEqual(
            {e['callsite'] for e in APP_NATIVE_PROVIDER_CALLS},
            {e['callsite'] for e in
             registered_native_requests(request_kind='factory_lookup')})
        self.assertEqual(len([e for e in APP_NATIVE_REGISTRY['callsites']
                              if e['api'] in ('transition', 'child_request')]),
                         73)
        self.assertEqual(sum(e['is_registered_destination']
                             for e in APP_NATIVE_REGISTRY['callsites']), 67)

    def test_exact_literal_ids_and_delay_slot_arguments(self):
        rows = registered_factory_providers(argument_kind='literal')
        self.assertEqual(len(rows), 26)
        self.assertEqual({e['target_id'] for e in rows},
                         {2, 5, 6, 8, 9, 14, 15, 22})
        for row in rows:
            with self.subTest(site=row['callsite']):
                self.assertEqual(row['target_class'],
                                 APP_ENTRIES[row['target_id']]['class_name'])
                self.assertEqual(row['argument_opcode'],
                                 0x24040000 | row['target_id'])
                self.assertEqual(row['call_opcode'], 0x0C0FC710)
                self.assertIn(row['argument_position'],
                              ('jal_delay_slot', 'branch_delay_slot',
                               'before_jal'))
                if row['argument_position'] == 'jal_delay_slot':
                    self.assertEqual(row['argument_site'],
                                     row['callsite'] + 4)
                self.assertFalse(row['factory_invoked_in_observed_runtime'])
                self.assertFalse(row['returned_object_observed'])
        by_site = {edge['callsite']: edge for edge in rows}
        self.assertEqual(by_site[0x1CA1F8]['target_id'], 15)
        self.assertEqual(by_site[0x1CA1F8]['argument_site'], 0x1CA11C)
        self.assertEqual(by_site[0x1CBFA0]['argument_site'], 0x1CBED4)
        self.assertEqual(by_site[0x3FABF8]['target_id'], 2)
        self.assertEqual(by_site[0x3FAC30]['target_id'], 2)
        self.assertEqual(by_site[0x326B84]['target_id'], 5)
        self.assertEqual(by_site[0x3E9340]['target_id'], 22)
        self.assertEqual(len(registered_factory_providers(target_id=15)), 12)

    def test_warning_cri_ownership_is_proven_not_proximity_assigned(self):
        verified = [e for e in APP_NATIVE_PROVIDER_CALLS
                    if e['source_ownership_verified']]
        self.assertEqual({e['callsite'] for e in verified},
                         {0x3FABF8, 0x3FAC30})
        phase_data = {
            0x3FABF8: (3, 0x3C, 0x3FABF0),
            0x3FAC30: (4, 0x40, 0x3FAC20),
        }
        for row in verified:
            with self.subTest(site=row['callsite']):
                phase, offset, callback = phase_data[row['callsite']]
                self.assertEqual(row['source_application_id'], 1)
                self.assertEqual(row['source_callback_phase'], phase)
                self.assertEqual(row['source_base_vtable_offset'], offset)
                self.assertEqual(row['source_callback_address'], callback)
                self.assertEqual(APP_ENTRIES[1]['base_slots'][
                    '0x%02x' % offset], callback)
                self.assertEqual(row['target_id'], 2)
                self.assertFalse(row['factory_invoked_in_observed_runtime'])
        self.assertEqual(sum(e['source_application_id'] is None
                             for e in APP_NATIVE_PROVIDER_CALLS), 35)

    def test_dynamic_provider_reads_never_claim_registered_destination(self):
        dynamic = [e for e in APP_NATIVE_PROVIDER_CALLS
                   if e['argument_kind'] != 'literal']
        self.assertEqual(len(dynamic), 11)
        for row in dynamic:
            with self.subTest(site=row['callsite']):
                self.assertIsNone(row['target_id'])
                self.assertIsNone(row['target_class'])
                self.assertFalse(row['source_ownership_verified'])
                self.assertFalse(row['factory_invoked_in_observed_runtime'])
                self.assertFalse(row['returned_object_observed'])
        child = registered_factory_providers(argument_kind='child_id_byte')
        self.assertEqual(len(child), 9)
        self.assertEqual({e['argument_opcode'] for e in child},
                         {0x80840012, 0x82040012})
        pending = registered_factory_providers(
            argument_kind='pending_id_byte')
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['callsite'], 0x3DFDFC)
        self.assertEqual(pending[0]['argument_opcode'], 0x82040010)
        forwarded = registered_factory_providers(
            argument_kind='requested_child_id')
        self.assertEqual(len(forwarded), 1)
        self.assertEqual(forwarded[0]['callsite'], 0x3DFC2C)
        self.assertEqual(forwarded[0]['argument_site'], 0x3DFC08)
        self.assertEqual(forwarded[0]['argument_opcode'], 0x0220202D)

    def test_public_query_rejects_invalid_filters(self):
        self.assertEqual(len(registered_factory_providers()), 37)
        self.assertEqual(len(registered_factory_providers(target_id=2)), 2)
        self.assertEqual(len(registered_factory_providers(target_id=47)), 0)
        self.assertEqual(
            len(registered_factory_providers(
                target_id=15, argument_kind='child_id_byte')), 0)
        for bad in (0, 48, True, '2'):
            with self.assertRaises(ValueError):
                registered_factory_providers(target_id=bad)
        with self.assertRaises(ValueError):
            registered_factory_providers(argument_kind='unknown')

    def test_exact_original_eu_beta_elf_oracle_optional(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact original EU-beta ELF not distributed in CI')
        data = Path(path).read_bytes()
        result = verify_provider_audit(
            data, APP_NATIVE_PROVIDER_AUDIT, APP_NATIVE_REGISTRY)
        self.assertEqual(result['verified_provider_sites'], 37)
        self.assertEqual(result['verified_argument_sites'], 37)
        self.assertEqual(result['distinct_literal_ids'],
                         [2, 5, 6, 8, 9, 14, 15, 22])
        self.assertFalse(result['runtime_execution_proven'])
        corrupted = copy.deepcopy(APP_NATIVE_PROVIDER_AUDIT)
        corrupted['callsites'][0]['argument_opcode'] ^= 1
        with self.assertRaisesRegex(ValueError, 'argument source opcode'):
            verify_provider_audit(data, corrupted, APP_NATIVE_REGISTRY)
        corrupted = copy.deepcopy(APP_NATIVE_PROVIDER_AUDIT)
        corrupted['callsites'][0]['target_id'] = 14
        with self.assertRaisesRegex(ValueError, 'literal provider ID'):
            verify_provider_audit(data, corrupted, APP_NATIVE_REGISTRY)
        corrupted = copy.deepcopy(APP_NATIVE_PROVIDER_AUDIT)
        owner = next(e for e in corrupted['callsites']
                     if e['callsite'] == 0x3FABF8)
        owner['source_application_id'] = 3
        with self.assertRaisesRegex(ValueError, 'ownership'):
            verify_provider_audit(data, corrupted, APP_NATIVE_REGISTRY)
        corrupted = copy.deepcopy(APP_NATIVE_PROVIDER_AUDIT)
        corrupted['callsites'][0]['factory_invoked_in_observed_runtime'] = True
        with self.assertRaisesRegex(ValueError, 'runtime'):
            verify_provider_audit(data, corrupted, APP_NATIVE_REGISTRY)
        corrupted = copy.deepcopy(APP_NATIVE_PROVIDER_AUDIT)
        corrupted['callsites'][0]['callsite'] = (
            corrupted['callsites'][1]['callsite'])
        with self.assertRaisesRegex(ValueError, 'duplicate/invalid'):
            verify_provider_audit(data, corrupted, APP_NATIVE_REGISTRY)
        with self.assertRaisesRegex(ValueError, 'exact EU-beta'):
            verify_provider_audit(b'wrong ELF', APP_NATIVE_PROVIDER_AUDIT,
                                  APP_NATIVE_REGISTRY)


if __name__ == '__main__':
    unittest.main()
