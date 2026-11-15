"""Asset-free tests of screenshot capture geometry measurement."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

from compare_menu_captures import (
    MENU_ITEM_KEYS, compare_menu_captures, validate_capture,
)
from arika_menu_help_native import NATIVE_HELP_RECORDS
from arika_menu_navigation import MENU_ITEM_NAMES, read_menu_report


def synthetic_capture(size, shift=0, first_line_only=False, line_count=4):
    image = Image.new('RGB', size, (150, 45, 120))
    draw = ImageDraw.Draw(image)
    for index in range(1 if first_line_only else line_count):
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

    def test_all_seven_selections_follow_elf_record_counts(self):
        report = read_menu_report()
        self.assertEqual(len(NATIVE_HELP_RECORDS), len(MENU_ITEM_NAMES))
        self.assertEqual(MENU_ITEM_KEYS, (
            'original', 'z_survivor', 'versus', 'dragon_summoning',
            'training', 'customize', 'options'))
        for selection, (_text_id, _address, count) in enumerate(
                NATIVE_HELP_RECORDS):
            with self.subTest(selection=selection):
                self.assertEqual(count, len(
                    report['menu']['items'][selection]['help_text']['lines']))
                image = synthetic_capture((640, 480), line_count=count)
                result = compare_menu_captures(image, image, selection)
                self.assertEqual(result['selection'], selection)
                self.assertEqual(result['native_text_id'],
                                 NATIVE_HELP_RECORDS[selection][0])
                self.assertEqual(result['help_line_count'], count)
                self.assertEqual(len(result['help_lines']), count)
                self.assertTrue(all(row['delta'] is not None
                                    for row in result['help_lines']))

    def test_versus_and_options_skip_unowned_fourth_help_row(self):
        reference = synthetic_capture((640, 480), line_count=3)
        # A white fourth row in the candidate is an unrelated UI artifact.
        candidate = synthetic_capture((640, 480), line_count=4)
        for item in (2, 6):
            with self.subTest(selection=item):
                result = compare_menu_captures(reference, candidate, item)
                self.assertEqual(len(result['help_lines']), 3)
                self.assertEqual(result['help_line_count'], 3)
                self.assertTrue(all(row['delta']['left'] == 0
                                    for row in result['help_lines']))

    def test_invalid_menu_selection_is_rejected(self):
        image = synthetic_capture((640, 480))
        for selection in (-1, 7, None, True, 'versus'):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                compare_menu_captures(image, image, selection)

    def test_command_line_item_options_and_original_default(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            reference = folder / 'reference.png'
            candidate = folder / 'candidate.png'
            synthetic_capture((640, 480), line_count=3).save(reference)
            synthetic_capture((640, 480), line_count=3).save(candidate)
            script = Path(__file__).with_name('compare_menu_captures.py')
            base = [sys.executable, str(script),
                    str(reference), str(candidate)]
            options = subprocess.run(
                base + ['--item', 'options', '--json'],
                capture_output=True, text=True, check=True)
            decoded = json.loads(options.stdout)
            self.assertEqual(decoded['selection'], 6)
            self.assertEqual(decoded['help_line_count'], 3)
            self.assertEqual(len(decoded['help_lines']), 3)
            original = subprocess.run(
                base + ['--json'],
                capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(original.stdout)['help_line_count'], 4)

    def test_plain_background_has_no_false_white_text(self):
        image = Image.new('RGB', (640, 480), (160, 65, 144))
        result = compare_menu_captures(image, image)
        self.assertTrue(all(row['delta'] is None for row in result['help_lines']))


if __name__ == '__main__':
    unittest.main()
