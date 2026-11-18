"""Strict evidence-bound tests for SDBZ EU-beta PCSX2 EE trace import."""
import json
from pathlib import Path
import tempfile
import unittest

from arika_app_registry import APP_ENTRIES
from arika_native_ee_trace import (
    ELF_SHA256, TRACE_FORMAT, inspect_native_ee_trace,
    load_native_ee_trace, ROOT_DISPATCH, PROVIDER_DISPATCH,
    ROOT_RETURN, PROVIDER_RETURN, ROOT_SLOT, ROOT_STORE, FALLBACK_STORE,
    ROOT_INVALID_FALLBACK, pcsx2_ee_symbols,
)


def fixture(events=None, source='synthetic-test-fixture'):
    return {'format': TRACE_FORMAT, 'source': source,
            'elf_sha256': ELF_SHA256,
            'events': list(events or [])}


def dispatch(seq, app_id=3, root=True):
    return {'sequence': seq, 'kind': 'factory_dispatch',
            'pc': hex(ROOT_DISPATCH if root else PROVIDER_DISPATCH),
            'registers': {'s0': app_id, 'v0': hex(APP_ENTRIES[app_id]['factory'])}}


def entry(seq, app_id=3, root=True):
    return {'sequence': seq, 'kind': 'factory_entry',
            'pc': hex(APP_ENTRIES[app_id]['factory']),
            'registers': {'ra': hex(ROOT_RETURN if root else PROVIDER_RETURN)}}


def ret(seq, value=0x123450, root=True):
    return {'sequence': seq, 'kind': 'factory_return',
            'pc': hex(ROOT_RETURN if root else PROVIDER_RETURN),
            'registers': {'v0': hex(value)}}


def store(seq, value=0x123450, site=ROOT_STORE):
    return {'sequence': seq, 'kind': 'root_write',
            'store_pc': hex(site), 'address': hex(ROOT_SLOT),
            'value': hex(value), 'registers': {'a0': hex(value)},
            'post_write': True}


class NativeEeTraceTests(unittest.TestCase):
    def test_empty_trace_proves_nothing(self):
        result = inspect_native_ee_trace(fixture())
        self.assertEqual(result['event_count'], 0)
        self.assertEqual(result['factory_entry_count'], 0)
        self.assertEqual(result['root_write_count'], 0)
        self.assertEqual(result['observed_factory_ids'], [])
        self.assertIsNone(result['last_root_pointer'])
        self.assertTrue(result['synthetic_fixture'])
        self.assertTrue(result['source_is_user_reported'])
        self.assertFalse(result['visual_transition_verified'])
        self.assertFalse(result['new_allocation_proven'])

    def test_root_handoff_factory_entered_and_active_root_committed(self):
        events = [
            {'sequence': 1, 'kind': 'root_handoff', 'pc': '0x3f1ba0',
             'registers': {'a0': 3, 'ra': '0x3dff3c'}},
            dispatch(2),
            entry(3),
            ret(4),
            store(5),
        ]
        result = inspect_native_ee_trace(fixture(events))
        self.assertEqual(result['root_handoff_count'], 1)
        self.assertTrue(result['events'][0]['scheduler_caller'])
        self.assertEqual(result['factory_dispatch_count'], 1)
        self.assertEqual(result['factory_entry_count'], 1)
        self.assertEqual(result['observed_factory_ids'], [3])
        self.assertEqual(result['factory_return_count'], 1)
        self.assertEqual(result['root_write_count'], 1)
        self.assertEqual(result['last_root_pointer'], 0x123450)
        self.assertEqual(result['events'][-1]['correlated_return_sequence'], 4)
        self.assertEqual(result['warnings'], [])
        self.assertFalse(result['visual_transition_verified'])
        self.assertFalse(result['new_allocation_proven'])

    def test_dispatch_breakpoint_alone_is_not_factory_execution(self):
        result = inspect_native_ee_trace(fixture([dispatch(1)]))
        self.assertEqual(result['factory_dispatch_count'], 1)
        self.assertEqual(result['factory_entry_count'], 0)
        self.assertEqual(result['root_write_count'], 0)
        self.assertEqual(result['observed_factory_ids'], [])
        self.assertEqual(result['events'][0]['execution_confirmed'], False)
        self.assertIn('no captured return', result['warnings'][0])

    def test_nested_factory_providers_use_lifo_return_tracking(self):
        result = inspect_native_ee_trace(fixture([
            dispatch(1, 2, root=False),
            entry(2, 2, root=False),
            dispatch(3, 15, root=False),
            entry(4, 15, root=False),
            ret(5, 0xA000, root=False),
            ret(6, 0xB000, root=False),
        ]))
        self.assertEqual(result['observed_factory_ids'], [2, 15])
        self.assertEqual(result['factory_entry_count'], 2)
        self.assertEqual(result['factory_return_count'], 2)
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['events'][4]['requested_id'], 15)
        self.assertEqual(result['events'][5]['requested_id'], 2)

    def test_null_factory_return_and_both_fallbacks(self):
        result = inspect_native_ee_trace(fixture([
            dispatch(1), entry(2), ret(3, value=0),
            store(4, value=0x004FCAD4),
            store(5, value=ROOT_INVALID_FALLBACK, site=FALLBACK_STORE),
        ]))
        self.assertEqual(result['root_write_count'], 2)
        self.assertEqual(result['last_root_pointer'], ROOT_INVALID_FALLBACK)
        self.assertEqual(result['events'][3]['correlated_return_sequence'], 3)

    def test_sparse_return_and_postwrite_can_be_recorded_independently(self):
        result = inspect_native_ee_trace(fixture([
            ret(0, value=0x123456),
            store(1, value=0x123456),
        ], source='pcsx2-ee-debugger'))
        self.assertEqual(result['factory_entry_count'], 0)
        self.assertEqual(result['root_write_count'], 1)
        self.assertTrue(result['source_is_user_reported'])
        self.assertFalse(result['synthetic_fixture'])
        self.assertIn('unpaired return', result['warnings'][0])

    def test_wrong_elf_and_claims_without_proper_breakpoint_are_rejected(self):
        base = fixture([dispatch(1), entry(2), ret(3), store(4)])
        variants = [
            (lambda d: d.update(elf_sha256='0'*64), 'SHA-256'),
            (lambda d: d.update(source='made-up-attestation'), 'source'),
            (lambda d: d.update(format='v2'), 'format'),
            (lambda d: d['events'][0]['registers'].update(v0=0x1000),
             'factory pointer'),
            (lambda d: d['events'][0]['registers'].update(s0=48), 'bounds'),
            (lambda d: d['events'][1]['registers'].update(ra=0x1234),
             'factory entry'),
            (lambda d: d['events'][1].update(pc=0x1234),
             'factory entry'),
            (lambda d: d['events'][2].update(pc=0xDEADBEEF), 'return PC'),
            (lambda d: d['events'][3].update(post_write=False), 'post-write'),
            (lambda d: d['events'][3]['registers'].update(a0=0), 'stored a0'),
            (lambda d: d['events'][3].update(address=0x1234),
             'active-root'),
            (lambda d: (d['events'][3].update(value=0x456789),
                        d['events'][3]['registers'].update(a0=0x456789)),
             'captured return/fallback'),
            (lambda d: d['events'][3].update(sequence=2), 'sequence'),
            (lambda d: d['events'][0].update(kind='fake'), 'kind'),
        ]
        for change, expected in variants:
            sample = json.loads(json.dumps(base))
            change(sample)
            with self.subTest(case=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    inspect_native_ee_trace(sample)

    def test_root_zero_and_invalid_id_cannot_enter_jalr_path(self):
        sample = fixture([dispatch(1)])
        sample['events'][0]['registers']['s0'] = 0
        with self.assertRaisesRegex(ValueError, 'bounds'):
            inspect_native_ee_trace(sample)
        sample['events'][0]['registers']['s0'] = '0x100000003'
        # MIPS EE GPRs are 128-bit, but the trace exposes the 32-bit
        # unsigned low part used by s0 & 0xff, rejecting ambiguous width.
        with self.assertRaisesRegex(ValueError, '32-bit'):
            inspect_native_ee_trace(sample)

    def test_pcsx2_symbol_labels_cover_every_factory_and_trace_site(self):
        lines = pcsx2_ee_symbols().splitlines()
        self.assertEqual(len(lines), 56)
        self.assertEqual(len({line.split()[0] for line in lines}), 56)
        self.assertTrue(all(len(line.split()) == 2 for line in lines))
        self.assertIn('003F1C78 ee_provider_factory_jalr', lines)
        self.assertIn('003F1BE0 ee_root_factory_jalr', lines)
        self.assertIn('0063BE38 ee_active_root_global', lines)
        for app_id, app in APP_ENTRIES.items():
            with self.subTest(app_id=app_id):
                self.assertEqual(
                    sum(line.startswith('%08X ' % app['factory'])
                        for line in lines), 1)
                self.assertIn('ee_app_%02d_' % app_id, ''.join(lines))

    def test_file_load_and_synthetic_fixture_remain_explicit(self):
        sample = fixture([dispatch(1), entry(2), ret(3), store(4)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.json'
            path.write_text(json.dumps(sample), encoding='utf-8')
            self.assertEqual(load_native_ee_trace(path)['factory_entry_count'],
                             1)
            path.write_text('{not json}', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                load_native_ee_trace(path)


if __name__ == '__main__':
    unittest.main()
