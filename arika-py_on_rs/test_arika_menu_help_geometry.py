"""Reference screenshot geometry: measure TV 4:3 in 512x448 logical units.

Measurements are approximate pixel picks from the two user-provided
screenshots, NOT recovered ELF help-frame offsets. Do not bundle the
original screenshots or game art with these numeric regressions.
"""
import math
import unittest

from arika_menu_help_geometry import (
    LOGICAL_WIDTH, LOGICAL_HEIGHT, HELP_PANEL_RECT, HELP_TEXT_CLIP,
    HELP_TEXT_ORIGIN, HELP_LINE_ADVANCE, HELP_TEXT_MAX_WIDTH,
    screenshot_to_logical, logical_to_screenshot, help_text_row_rect,
)


# The PCSX2 image is 958x719, and the Qt image is 706x529.
# Both are 4:3 *displayed* frames of a 512x448 logical render.
# These are approximate visible upper-left pixel picks. Text rows are
# a much more reliable anchor than the irregular outer panel artwork.
REFERENCE_SIZE = (958, 719)
EDITOR_SIZE = (706, 529)
HELP_ANCHORS = {
    'frame_top_left': ((55, 447), (43, 324)),
    'first_line': ((165, 524), (121, 386)),
    'second_line': ((165, 564), (121, 416)),
    'third_line': ((165, 606), (121, 446)),
    'fourth_line': ((165, 647), (121, 475)),
}


class HelpAlignmentTests(unittest.TestCase):
    def test_image_axes_use_independent_non_square_pixel_scales(self):
        self.assertEqual((LOGICAL_WIDTH, LOGICAL_HEIGHT), (512, 448))
        self.assertAlmostEqual(REFERENCE_SIZE[0] / REFERENCE_SIZE[1],
                               4.0 / 3.0, places=2)
        self.assertNotAlmostEqual(
            REFERENCE_SIZE[0] / LOGICAL_WIDTH,
            REFERENCE_SIZE[1] / LOGICAL_HEIGHT, places=1)
        point = (87.0, 324.0)
        for size in (REFERENCE_SIZE, EDITOR_SIZE, (512, 384),
                     (512, 448), (1024, 768)):
            mapped = logical_to_screenshot(point, size)
            back = screenshot_to_logical(mapped, size)
            self.assertAlmostEqual(back[0], point[0])
            self.assertAlmostEqual(back[1], point[1])
        with self.assertRaises(ValueError):
            screenshot_to_logical((10, 20), (512, 0))
        with self.assertRaises(ValueError):
            logical_to_screenshot((10, 20), (0, 448))

    def test_original_and_qt_help_anchors_match_after_tv_pixel_aspect(self):
        for name, (reference_point, editor_point) in HELP_ANCHORS.items():
            with self.subTest(anchor=name):
                a = screenshot_to_logical(reference_point, REFERENCE_SIZE)
                b = screenshot_to_logical(editor_point, EDITOR_SIZE)
                tolerance = 7.0 if name == 'frame_top_left' else 3.0
                self.assertLess(abs(a[0] - b[0]), tolerance)
                self.assertLess(abs(a[1] - b[1]), tolerance)

    def test_reference_text_is_not_shifted_down_in_512x448_space(self):
        # The screenshot line positions match the already-existing
        # Qt FFON placement. A uniform horizontal scale would incorrectly
        # place line 1 near Y=280 rather than Y=324.
        for index, name in enumerate((
                'first_line', 'second_line', 'third_line', 'fourth_line')):
            original_y = screenshot_to_logical(
                HELP_ANCHORS[name][0], REFERENCE_SIZE)[1]
            expected_y = HELP_TEXT_ORIGIN[1] + index * HELP_LINE_ADVANCE
            self.assertLess(abs(original_y - expected_y), 5.0)
        uniform_y = HELP_ANCHORS['first_line'][0][1] * (
            LOGICAL_WIDTH / REFERENCE_SIZE[0])
        self.assertGreater(HELP_TEXT_ORIGIN[1] - uniform_y, 35.0)

    def test_help_panel_preview_geometry_and_stable_ffon_line_advance(self):
        self.assertEqual(HELP_PANEL_RECT, (30.0, 272.0, 450.0, 175.0))
        self.assertEqual(HELP_TEXT_CLIP, (76.0, 312.0, 359.0, 116.0))
        self.assertEqual(HELP_TEXT_MAX_WIDTH, 303.0)
        self.assertEqual(help_text_row_rect(0, 100, 20, 1.0),
                         (87.0, 324.0, 100.0, 20.0))
        self.assertEqual(help_text_row_rect(3, 100, 20, .75),
                         (87.0, 399.0, 75.0, 15.0))
        for size in (45, 180, 500):
            factor = min(1.0, HELP_TEXT_MAX_WIDTH / size)
            for row in range(4):
                rect = help_text_row_rect(row, size, 18, factor)
                self.assertEqual(rect[0], 87.0)
                self.assertLessEqual(rect[2], HELP_TEXT_MAX_WIDTH)
        with self.assertRaises(ValueError):
            help_text_row_rect(4, 50, 20)
        with self.assertRaises(ValueError):
            help_text_row_rect(-1, 50, 20)


if __name__ == '__main__':
    unittest.main()
