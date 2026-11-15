"""Regression for rendering spaces with the existing FFON bitmap font."""
import unittest

from arika_ffon import c_ffon_font, render_text


class FontSpacingTests(unittest.TestCase):
    def test_spaces_advance_without_drawing_a_glyph(self):
        mapping = [0] * 96
        mapping[ord('A') - 32] = 1
        mapping[ord('B') - 32] = 2
        font = c_ffon_font(width=2, height=2, row_stride=1,
                           page_count=1, last_column=95, glyph_count=2,
                           char_map=mapping, glyph_data_offset=0,
                           bytes_per_glyph=2)
        data = bytes((255, 255, 255, 255))
        tight = render_text(font, data, 'AB', spacing=1)
        spaced = render_text(font, data, 'A B', spacing=1)
        self.assertGreater(spaced.width, tight.width)
        self.assertEqual(spaced.getpixel((0, 0))[3], 255)
        # Space between words must remain transparent.
        self.assertEqual(spaced.getpixel((5, 0))[3], 0)
        self.assertEqual(spaced.getpixel((spaced.width - 1, 0))[3], 255)


if __name__ == '__main__':
    unittest.main()
