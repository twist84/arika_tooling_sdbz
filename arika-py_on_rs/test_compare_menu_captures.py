"""Asset-free tests of screenshot capture geometry measurement."""
import unittest

from PIL import Image, ImageDraw

from compare_menu_captures import compare_menu_captures, validate_capture


def synthetic_capture(size, shift=0, first_line_only=False):
    image = Image.new('RGB', size, (150, 45, 120))
    draw = ImageDraw.Draw(image)
    for index in range(1 if first_line_only else 4):
        x = int((105 + shift) * size[0] / 512)
        y = int((327 + 25 * index) * size[1] / 448)
        width = max(1, int(80 * size[0] / 512))
        height = max(1, int(11 * size[1] / 448))
        draw.rectangle((x, y, x + width, y + height), fill=(255, 255, 255))
    return image


class CompareMenuCapturesTests(unittest.TestCase):
    def test_full_frame_4_by_3_required(self):
        validate_capture(Image.new('RGB', (958, 719)))
        validate_capture(Image.new('RGB', (706, 529)))
        with self.assertRaisesRegex(ValueError, '4:3'):
            validate_capture(Image.new('RGB', (512, 448)))

    def test_size_independent_native_coordinates(self):
        original = synthetic_capture((958, 719))
        candidate = synthetic_capture((706, 529))
        result = compare_menu_captures(original, candidate)
        self.assertEqual(result['native_canvas'], [512, 448])
        for row in result['help_lines']:
            self.assertIsNotNone(row['delta'])
            self.assertLess(abs(row['delta']['left']), 1.1)
            self.assertLess(abs(row['delta']['right']), 1.1)
            self.assertLess(abs(row['delta']['top']), 1.1)

    def test_actual_x_shift_is_reported_without_autocorrect(self):
        original = synthetic_capture((958, 719), first_line_only=True)
        candidate = synthetic_capture((706, 529), shift=4, first_line_only=True)
        result = compare_menu_captures(original, candidate)
        delta = result['help_lines'][0]['delta']
        self.assertAlmostEqual(delta['left'], 4, delta=1)
        self.assertAlmostEqual(delta['right'], 4, delta=1)
        for row in result['help_lines'][1:]:
            self.assertIsNone(row['delta'])

    def test_plain_background_has_no_false_white_text(self):
        image = Image.new('RGB', (640, 480), (160, 65, 144))
        result = compare_menu_captures(image, image)
        self.assertTrue(all(row['delta'] is None for row in result['help_lines']))


if __name__ == '__main__':
    unittest.main()
