"""EU-beta FFON cell-advance tests, with optional original ELF word parity."""
import hashlib
import os
import struct
import unittest
from pathlib import Path

from arika_ffon import c_ffon_font
from arika_menu_ffon_native import (
    FONT_OBJECT_VTABLE, NATIVE_ASCII_ADVANCE, NATIVE_FONT_CELL_HEIGHT,
    NATIVE_FONT_CELL_WIDTH, NATIVE_MENU_FONT_SCALE,
    native_help_glyph_origins, render_native_help_line,
)
from arika_menu_navigation import read_menu_report


def synthetic_font():
    """Two 24x24 4bpp glyphs: one opaque dot each, no game font data."""
    char_map = [0] * 96
    char_map[ord('A') - 0x20] = 1
    char_map[ord('B') - 0x20] = 2
    glyphs = bytearray(2 * 12 * 24)
    glyphs[0] = 15
    glyphs[12 * 24] = 15
    return c_ffon_font(
        width=24, height=24, bits_per_pixel=4, row_stride=12,
        page_count=1, last_column=95, glyph_count=2,
        char_map=char_map, glyph_data_offset=0, bytes_per_glyph=288,
    ), bytes(glyphs)


class NativeMenuFfonAdvanceTests(unittest.TestCase):
    def test_native_halfwidth_cell_and_menu_scale(self):
        self.assertEqual((NATIVE_FONT_CELL_WIDTH, NATIVE_FONT_CELL_HEIGHT), (24, 24))
        self.assertEqual((NATIVE_ASCII_ADVANCE, NATIVE_MENU_FONT_SCALE), (12, .75))
        self.assertEqual(native_help_glyph_origins('A B'),
                         ((0.0, 9.0, 18.0), 27.0))
        self.assertEqual(native_help_glyph_origins('A B', 1.0),
                         ((0.0, 12.0, 24.0), 36.0))
        self.assertEqual(native_help_glyph_origins(''), ((), 0.0))

    def test_all_seven_original_help_records_use_supported_ascii(self):
        report = read_menu_report()
        for item in report['menu']['items']:
            for line in item['help_text']['lines']:
                text = line['text']
                positions, width = native_help_glyph_origins(text)
                self.assertEqual(len(positions), len(text))
                self.assertEqual(width, 9.0 * len(text))
                if len(positions) > 1:
                    self.assertEqual(positions[1] - positions[0], 9.0)

    def test_unverified_markup_and_multibyte_paths_are_not_guessed(self):
        for text in (None, 42, 'A\nB', '$R', 'é', '\t'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                native_help_glyph_origins(text)
        for scale in (0.0, -1.0, float('nan'), float('inf')):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                native_help_glyph_origins('A', scale)

    def test_synthetic_bitmap_is_positioned_by_native_cell_not_trimmed_bbox(self):
        font, data = synthetic_font()
        image = render_native_help_line(font, data, 'A B')
        self.assertEqual(image.size, (36, 24))
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255, 255))
        self.assertEqual(image.getpixel((12, 0))[3], 0)
        self.assertEqual(image.getpixel((24, 0)), (255, 255, 255, 255))
        self.assertEqual(image.getpixel((23, 0))[3], 0)
        self.assertEqual(render_native_help_line(font, data, '').size, (1, 24))

    def test_half_cell_clip_prevents_hidden_ffon_overdraw(self):
        font, data = synthetic_font()
        data = bytearray(data)
        # Second 12-pixel half of the A bitmap must NOT be composited
        # over a subsequent ASCII cell. x=13 is byte 6, upper nibble.
        data[6] = 0xf0
        legacy = render_native_help_line(font, bytes(data), 'A B')
        clipped = render_native_help_line(
            font, bytes(data), 'A B', clip_ascii_to_half_cell=True)
        self.assertEqual(clipped.size, (36, 24))
        self.assertEqual(legacy.getpixel((13, 0))[3], 255)
        self.assertEqual(clipped.getpixel((13, 0))[3], 0)
        self.assertEqual(clipped.getpixel((0, 0))[3], 255)
        self.assertEqual(clipped.getpixel((24, 0))[3], 255)
        # A 12-unit character pitch is invariant under source clipping.
        self.assertEqual(native_help_glyph_origins('A B', 1.0),
                         ((0.0, 12.0, 24.0), 36.0))
        with self.assertRaisesRegex(ValueError, 'clipping flag'):
            render_native_help_line(
                font, bytes(data), 'A', clip_ascii_to_half_cell=1)

    def test_native_raster_refuses_unproven_font_dimensions(self):
        font, data = synthetic_font()
        font.width = 12
        with self.assertRaises(ValueError):
            render_native_help_line(font, data, 'A')


@unittest.skipUnless(os.environ.get('SDBZ_FFON_FONT'),
                     'set SDBZ_FFON_FONT to test a user-owned original font')
class NativeFfonAssetCoverageTests(unittest.TestCase):
    def test_ascii_glyphs_fit_in_fixed_half_width_source_cells(self):
        from arika_ffon import parse_ffon
        data = Path(os.environ['SDBZ_FFON_FONT']).read_bytes()
        font = parse_ffon(data)
        self.assertEqual((font.width, font.height, font.row_stride),
                         (24, 24, 12))
        self.assertEqual(font.char_map[0], 1,
                         'mapped ASCII space is the first blank glyph')
        for code in range(0x20, 0x7f):
            with self.subTest(code=hex(code)):
                glyph_id = font.char_map[code - 0x20]
                self.assertNotEqual(glyph_id, 0)
                base = font.glyph_offset(glyph_id - 1)
                for y in range(24):
                    # In a 24x24 4bpp record the right 12 columns
                    # occupy bytes 6..11 of each 12-byte row.
                    self.assertEqual(
                        data[base + y * 12 + 6:base + y * 12 + 12],
                        bytes(6))


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'requires original EU-beta ELF, not included in repo/CI')
class NativeFfonElfOracleTests(unittest.TestCase):
    def test_font_constructor_vtable_and_halfwidth_kernel(self):
        data = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')

        def word(va):
            return struct.unpack_from('<I', data,
                                      va - 0x100000 + 0x80)[0]

        # Static constructor initializes object 0x63BE80 with vtable
        # 0x4E3390; startup 0x3264A4 writes float24 into +4 and +8.
        self.assertEqual(word(0x4E2E60), 0x0c000000 | (0x19A120 >> 2))
        self.assertEqual(word(0x32648C), 0x3C0441C0)
        self.assertEqual(word(0x3264A4), 0xAC44BE88)
        self.assertEqual(word(0x3264AC), 0xAC64BE84)
        for offset, callback in {
            0x10: 0x19A1B0,  # string width/height
            0x14: 0x199DC0,  # space advance: 0.5 * width
            0x18: 0x199DE0,  # line advance: height
            0x1C: 0x19A030,  # codepoint advance
            0x20: 0x199EE0,  # texture/font draw packet
        }.items():
            with self.subTest(slot=offset):
                self.assertEqual(word(FONT_OBJECT_VTABLE + offset), callback)
        self.assertEqual(word(0x19A030), 0x30A2FFFF)
        self.assertEqual(word(0x19A034), 0x28410100)
        self.assertEqual(word(0x19A04C), 0x3C023F00)
        self.assertEqual(word(0x19A048), 0xC4800004)
        self.assertEqual(word(0x2CDF38), 0x8F390020)


if __name__ == '__main__':
    unittest.main()
