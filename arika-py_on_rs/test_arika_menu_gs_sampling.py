"""ELF-backed two-table per-binding filter selection tests.

All normal CI cases use synthetic 12-byte engine commands; the optional
original-ELF oracle verifies both table values and native call sites
without shipping any copyrighted executable data.
"""
import hashlib
import os
from pathlib import Path
import struct
import unittest

from arika_menu_gs_sampling import (
    BIND_RESOURCE_ADDRESS, CLAMP_BY_SELECTOR, ELF_CLAMP_SELECTOR_TABLE_ADDRESS,
    ELF_FILTER_SELECTOR_TABLE_ADDRESS, EMIT_TEXTURE_ADDRESS, FILTER_BY_SELECTOR,
    SET_FLAGS_ADDRESS, annotate_packet_sampling, decode_packet_sampling,
    resolve_texture_binding,
)
from arika_menu_gs_packet import decode_packet


def texture_binding(filter_selector=0, clamp_selector=0,
                    selector_at_plus_two=0, resource_pointer=0x12345678):
    return struct.pack('<HHHBBI', 1, selector_at_plus_two,
                       filter_selector, clamp_selector, 0, resource_pointer)


def callback(payload=b''):
    return struct.pack('<HHI', 0, 0, len(payload)) + payload


def packet(*commands):
    return struct.pack('<II', 0x5678, len(commands)) + b''.join(commands)


class NativeTextureSamplingTests(unittest.TestCase):
    def test_exact_file_backed_selector_tables(self):
        self.assertEqual(ELF_FILTER_SELECTOR_TABLE_ADDRESS, 0x4f73c8)
        self.assertEqual(ELF_CLAMP_SELECTOR_TABLE_ADDRESS, 0x4f73d0)
        self.assertEqual(FILTER_BY_SELECTOR, (0, 1))
        self.assertEqual(CLAMP_BY_SELECTOR, (1, 0))
        self.assertEqual(
            (SET_FLAGS_ADDRESS, BIND_RESOURCE_ADDRESS, EMIT_TEXTURE_ADDRESS),
            (0x104820, 0x10da20, 0x10c3e0))

    def test_all_four_independent_filter_and_clamp_combinations(self):
        for f in range(2):
            for c in range(2):
                with self.subTest(filter_selector=f, clamp_selector=c):
                    decoded = decode_packet(packet(texture_binding(
                        f, c, selector_at_plus_two=400)))['commands'][0]
                    result = resolve_texture_binding(decoded)
                    self.assertTrue(result['complete'])
                    self.assertEqual(result['filter_flag'], FILTER_BY_SELECTOR[f])
                    self.assertEqual(result['clamp_flag'], CLAMP_BY_SELECTOR[c])
                    self.assertEqual(result['resource_pointer'], 0x12345678)
                    self.assertEqual(result['texture_filter'],
                                     'linear' if f else 'nearest')
                    self.assertEqual(result['tex1_if_texture_writer_succeeds'],
                                     0x60 if f else 0)
                    self.assertEqual(result['tex1_fields_if_emitted']['mmag'], f)
                    self.assertEqual(result['tex1_fields_if_emitted']['mmin'], f)

    def test_unknown_indices_do_not_guess_native_state(self):
        for f, c in ((2, 0), (0, 2), (65535, 255)):
            with self.subTest(f=f, c=c):
                decoded = decode_packet(packet(
                    texture_binding(f, c)))['commands'][0]
                result = resolve_texture_binding(decoded)
                self.assertFalse(result['complete'])
                self.assertEqual(result['filter_flag'],
                                 FILTER_BY_SELECTOR[f] if f < 2 else None)
                self.assertEqual(result['clamp_flag'],
                                 CLAMP_BY_SELECTOR[c] if c < 2 else None)
                if f >= 2:
                    self.assertIsNone(result['tex1_if_texture_writer_succeeds'])
        with self.assertRaises(ValueError):
            resolve_texture_binding({'opcode': 0})
        with self.assertRaises(ValueError):
            resolve_texture_binding({'opcode': 1, 'selectors': [0]})

    def test_packet_binding_context_and_indirect_callback_invalidation(self):
        native = packet(
            callback(b'first'),
            texture_binding(1, 0),
            struct.pack('<Hh', 2, 2),
            struct.pack('<Hh', 8, 0),
            callback(b'geometry'),
            callback(b'another'),
            texture_binding(0, 1),
            callback(b'end'),
        )
        result = decode_packet_sampling(native)
        commands = result['commands']
        self.assertIsNone(commands[0]['binding_at_callback_entry'])
        self.assertEqual(commands[1]['texture_binding']['filter_flag'], 1)
        self.assertEqual(commands[1]['texture_binding']['clamp_flag'], 1)
        self.assertEqual(commands[4]['binding_at_callback_entry']['filter_flag'], 1)
        self.assertEqual(commands[4]['binding_at_callback_entry']['clamp_flag'], 1)
        self.assertIsNone(commands[5]['binding_at_callback_entry'])
        self.assertEqual(commands[6]['texture_binding']['filter_flag'], 0)
        self.assertEqual(commands[7]['binding_at_callback_entry']['filter_flag'], 0)
        self.assertIn('may modify', result['sampling_analysis'][
            'limitations'][-1])
        # Existing packet decoder is left untouched.
        original = decode_packet(native)
        self.assertNotIn('texture_binding', original['commands'][1])
        self.assertNotIn('binding_at_callback_entry', original['commands'][4])

    def test_rejects_invalid_input_without_corrupting_source(self):
        with self.assertRaises(ValueError):
            annotate_packet_sampling({'bad': True})


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'optional original EU-beta ELF word parity')
class NativeSamplingElfOracleTests(unittest.TestCase):
    def test_elf_table_words_and_exact_chain(self):
        data = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')

        def word(va):
            return struct.unpack_from('<I', data, va - 0xfff80)[0]

        self.assertEqual(tuple(word(ELF_FILTER_SELECTOR_TABLE_ADDRESS + n*4)
                               for n in range(2)), FILTER_BY_SELECTOR)
        self.assertEqual(tuple(word(ELF_CLAMP_SELECTOR_TABLE_ADDRESS + n*4)
                               for n in range(2)), CLAMP_BY_SELECTOR)
        # Interpreter reads the halfword +4 and byte +6; does not
        # use the other 16-bit selector at +2 for filtering.
        self.assertEqual(word(0x19b688), 0x96850004)
        self.assertEqual(word(0x19b68c), 0x92830006)
        self.assertEqual(word(0x19b690), 0x27848058)
        self.assertEqual(word(0x19b694), 0x27828060)
        self.assertEqual(word(0x19b6ac), 0x0c000000 | (SET_FLAGS_ADDRESS >> 2))
        self.assertEqual(word(0x19b6b8), 0x0c000000 | (BIND_RESOURCE_ADDRESS >> 2))
        self.assertEqual(word(0x10da84), 0x0c000000 | (EMIT_TEXTURE_ADDRESS >> 2))
        # Global g_filter/g_clamp BSS writes in native setter.
        self.assertEqual(word(0x104824), 0xac44f470)
        self.assertEqual(word(0x10482c), 0xac45f474)


if __name__ == '__main__':
    unittest.main()
