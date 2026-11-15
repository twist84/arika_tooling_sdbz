"""Synthetic and optional EU-beta ELF-oracle tests for native help drawing."""
import hashlib
import os
import struct
import unittest
from pathlib import Path

from arika_menu_help_native import (
    HELP_FRAME_DEPTH, HELP_FRAME_SOURCE_BOUNDS, HELP_FRAME_TEXTURE_INDEX,
    HELP_SETTLED_COMPONENT_ORIGIN,
    HELP_LINE_ADVANCE, HELP_TEXT_OFFSET, HELP_TEXT_SCALE,
    NATIVE_HELP_RECORDS, help_record, native_help_layout,
)
from arika_menu_navigation import read_menu_report


class NativeHelpLayoutTests(unittest.TestCase):
    def test_native_text_table_matches_existing_navigation_extraction(self):
        items = read_menu_report()['menu']['items']
        self.assertEqual(len(items), len(NATIVE_HELP_RECORDS))
        for index, item in enumerate(items):
            with self.subTest(item=index):
                text_id, address, count = help_record(index)
                self.assertEqual(text_id, item['text_lookup_id'])
                self.assertEqual(address, item['help_text']['address'])
                self.assertEqual(count, item['help_text']['line_count'])
                self.assertEqual(count, len(item['help_text']['lines']))
        self.assertEqual(tuple(entry[0] for entry in NATIVE_HELP_RECORDS),
                         (0x11C, 0x11D, 0x11F, 0x120, 0x11E, 0x121, 0x122))

    def test_frame_and_font_parameters_are_native_relative_values(self):
        self.assertEqual(HELP_FRAME_TEXTURE_INDEX, 4)
        self.assertEqual(HELP_FRAME_SOURCE_BOUNDS, (0, 0, 464, 176))
        self.assertEqual(HELP_FRAME_DEPTH, 97.0)
        self.assertEqual(HELP_TEXT_OFFSET, (64.0, 52.0))
        self.assertEqual(HELP_TEXT_SCALE, 0.75)
        self.assertEqual(HELP_LINE_ADVANCE, 25.0)
        self.assertEqual(HELP_SETTLED_COMPONENT_ORIGIN, (24.0, 272.0))
        self.assertEqual(native_help_layout(0, *HELP_SETTLED_COMPONENT_ORIGIN)['line_origins'][0],
                         (88.0, 324.0))

        # These input coordinates are synthetic, not a claim that the
        # native owner uses the Qt editor's calibrated screen origin.
        result = native_help_layout(0, 20, 270)
        self.assertEqual(result['panel_rect'], (20.0, 270.0, 464, 176))
        self.assertEqual(result['panel_texture'], 4)
        self.assertEqual(result['panel_depth'], 97.0)
        self.assertEqual(result['font_scale'], .75)
        self.assertEqual(result['line_origins'],
                         ((84.0, 322.0), (84.0, 347.0),
                          (84.0, 372.0), (84.0, 397.0)))

    def test_three_line_items_do_not_draw_a_phantom_fourth_line(self):
        for index in (2, 6):
            result = native_help_layout(index, 0, 0)
            self.assertEqual(result['line_count'], 3)
            self.assertEqual(result['line_origins'],
                             ((64.0, 52.0), (64.0, 77.0),
                              (64.0, 102.0)))

    def test_per_line_additions_round_to_float32(self):
        def f32(value):
            return struct.unpack('<f', struct.pack('<f', value))[0]

        x, y = 1.25, 123456.03125
        result = native_help_layout(1, x, y)
        ex = f32(f32(x) + 64.0)
        ey = f32(f32(y) + 52.0)
        for origin in result['line_origins']:
            self.assertEqual(origin, (ex, ey))
            ey = f32(ey + 25.0)

    def test_invalid_selection_and_coordinates(self):
        for index in (-1, 7, None, '0', True):
            with self.subTest(index=index), self.assertRaises(ValueError):
                native_help_layout(index, 0, 0)
        for x, y in ((float('nan'), 0), (0, float('inf')),
                     (None, 0), (0, 'wrong')):
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                native_help_layout(0, x, y)


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'set SDBZ_EU_BETA_ELF to test original, uncommitted ELF')
class NativeHelpElfOracleTests(unittest.TestCase):
    def test_exact_elf_words_and_text_records(self):
        binary = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(binary).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')

        def word(va):
            return struct.unpack_from('<I', binary,
                                      va - 0x00100000 + 0x80)[0]

        def real(va):
            return struct.unpack_from('<f', binary,
                                      va - 0x00100000 + 0x80)[0]

        # Selection array and records, including out-of-order text IDs.
        self.assertEqual(tuple(word(0x4A9FA0 + index * 4)
                               for index in range(7)),
                         tuple(record[0] for record in NATIVE_HELP_RECORDS))
        for text_id, address, line_count in NATIVE_HELP_RECORDS:
            with self.subTest(text_id=text_id):
                self.assertEqual(word(address), line_count)
                for offset in range(line_count):
                    string_address = word(address + 4 + offset * 4)
                    self.assertGreaterEqual(string_address, 0x00100000)
                    self.assertLess(string_address, 0x004FC900)

        # The live derived vtable is installed by 0x3FDD60, NOT
        # the 0x37A200 deleting destructor.
        self.assertEqual(word(0x3FDDC8), 0x24421F30)
        self.assertEqual(word(0x4F1F30 + 0x4C), 0x37BF60)
        self.assertEqual(word(0x4F1F30 + 0x50), 0x37C010)
        self.assertEqual(word(0x37C014), 0xAC850070)  # SW a1,+0x70(a0)
        self.assertEqual(word(0x37C240), 0x0C000000 | (0x2CDCA0 >> 2))

        # Native GP float constants used by the per-line loop.
        self.assertEqual(real(0x4FA770), HELP_SETTLED_COMPONENT_ORIGIN[0])
        self.assertEqual(real(0x4FA774), HELP_SETTLED_COMPONENT_ORIGIN[1])
        self.assertEqual(real(0x4FA798), HELP_TEXT_SCALE)
        self.assertEqual(real(0x4FA79C), HELP_TEXT_OFFSET[0])
        self.assertEqual(real(0x4FA7A0), HELP_TEXT_OFFSET[1])
        self.assertEqual(real(0x4FA7A4), HELP_LINE_ADVANCE)


if __name__ == '__main__':
    unittest.main()
