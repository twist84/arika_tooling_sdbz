"""Native ELF 0x199500 render-state copy and 0x199340 lookup tests.

The instruction-only oracle supports this 13-word scalar copy verbatim.
The caller provides context values; no actual hardware GS settings,
game memory capture or renderer video mode are inferred.
"""
import struct
import unittest

from arika_menu_gs_context import (
    decode_render_context, resolve_backend_arguments,
    WORD0_ARG4, WORD0_ARG5, WORD0_ARG6,
    WORD6_ARG4, WORD8_ARG5, BYTE2_ARG6, BYTE2_ARG7)
from menu_strip_oracle import c_strip_oracle


# 0x199500 through 0x199530 inclusive, including JR delay-slot SH.
CONTEXT_COPY = (
    0x848a005c, 0x8089005e, 0x8088005f, 0x80870060,
    0x84860062, 0x84830064, 0xa4aa0000, 0xa0a90002,
    0xa0a80003, 0xa0a70004, 0xa4a60006, 0x03e00008,
    0xa4a30008,
)


class NativeRenderContextTests(unittest.TestCase):
    def test_six_fields_exactly_match_native_context_copy(self):
        self.assertEqual(len(CONTEXT_COPY), (0x199534 - 0x199500) // 4)
        cases = (
            (1, 2, 0, 0, 3, 1),
            (0, 0, 0, 0, 0, 0),
            (3, 3, 1, 5, 2, 1),
            (-1, -128, 127, -1, -2, 17),
        )
        for fields in cases:
            # Six fields occupy renderer +0x5C .. +0x65.
            source = struct.pack('<hbbbxhh', *fields)
            machine = c_strip_oracle(
                dict(draw_address=0x199500,
                     draw_words=CONTEXT_COPY,
                     clock_address=0, clock_words=[]),
                [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
            machine.m_registers[4] = 0x1000
            machine.m_registers[5] = 0x2000
            machine.write(0x105c, source)
            machine.write(0x2000, b'\xaa' * 10)
            machine.run(0x199500)
            # The copy covers exactly 9 used bytes and preserves the
            # explicit padding byte at local state +0x5.
            self.assertEqual(
                machine.read(0x2000, 10),
                source[:5] + b'\xaa' + source[6:])
            self.assertEqual(
                decode_render_context(source),
                dict(zip(
                    ('word0', 'byte2', 'byte3',
                     'byte4', 'word6', 'word8'), fields)))

    def test_back_end_lookup_tables_are_file_backed_literals(self):
        self.assertEqual(
            (WORD0_ARG4, WORD0_ARG5, WORD0_ARG6),
            ((1, 2, 2, 2, 1, 4, 0, 0),
             (0, 3, 1, 1, 1, 5, 0, 0),
             (0, 0, 0, 2, 1, 0, 0, 0)))
        self.assertEqual(WORD6_ARG4, (1, 0, 6, 7))
        self.assertEqual(WORD8_ARG5, (0, 1))
        self.assertEqual(BYTE2_ARG6, (1, 2, 3, 7, 3, 0, 0, 0))
        self.assertEqual(BYTE2_ARG7, (0, 0, 0, 128, 128, 0))

        for word0 in range(8):
            out = resolve_backend_arguments({'word0': word0})
            self.assertEqual(
                out['backend_0x104920'],
                (WORD0_ARG4[word0], WORD0_ARG5[word0],
                 WORD0_ARG6[word0]))
            self.assertIsNone(out['backend_0x104840'])
        for word6 in range(4):
            for byte2 in range(6):
                for word8 in (0, 1):
                    out = resolve_backend_arguments(
                        {'word6': word6, 'byte2': byte2, 'word8': word8})
                    self.assertEqual(
                        out['backend_0x104840'],
                        (WORD6_ARG4[word6], WORD8_ARG5[word8],
                         BYTE2_ARG6[byte2], BYTE2_ARG7[byte2]))

    def test_constructor_stores_defaults_but_does_not_store_all_bytes(self):
        # Stores at 0x199CDC/+0x199CE8/+0x199CF8/+0x199D08/
        # +0x199D14; local +0x60 is not explicitly written here.
        raw = {
            'word0': 1,
            'byte2': 2,
            'byte3': 0,
            'byte4': None,
            'word6': 3,
            'word8': 1,
        }
        translated = resolve_backend_arguments(raw)
        self.assertEqual(translated['backend_0x104920'], (2, 3, 0))
        self.assertEqual(translated['backend_0x104840'], (7, 1, 3, 0))
        self.assertIsNone(raw['byte4'])
        self.assertIn('GS semantics unverified', translated['note'])

    def test_missing_or_out_of_bounds_fields_do_not_imply_gs_modes(self):
        self.assertEqual(
            resolve_backend_arguments({}),
            dict(backend_0x104920=None, backend_0x104840=None,
                 note='Raw engine backend arguments; GS semantics unverified'))
        for state in (
                {'word0': -1}, {'word0': 8},
                {'word6': 4, 'byte2': 0, 'word8': 0},
                {'word6': 1, 'byte2': 6, 'word8': 0},
                {'word6': 1, 'byte2': 1, 'word8': 2},
                {'invented_gs_alpha': 0},
                {'word0': 'blend'}):
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    resolve_backend_arguments(state)
        for data in (b'', b'\x00' * 9, b'\x00' * 11, bytearray(10)):
            with self.assertRaises(ValueError):
                decode_render_context(data)


if __name__ == '__main__':
    unittest.main()
