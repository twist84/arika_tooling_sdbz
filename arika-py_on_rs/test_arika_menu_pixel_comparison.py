"""Asset-free PCSX2-versus-Qt pixel comparison tests."""
import unittest

from PIL import Image, ImageDraw

from arika_menu_pixel_comparison import (
    RESAMPLE_MODES, compare_screenshot_pixels, difference_preview,
)


class PixelDifferenceTests(unittest.TestCase):
    def test_identical_captures_have_zero_error(self):
        image = Image.new('RGB', (64, 48), (20, 44, 66))
        metrics, diff = compare_screenshot_pixels(image, image)
        self.assertEqual(metrics['all_pixels']['mean_absolute_error'], 0.0)
        self.assertEqual(metrics['all_pixels']['root_mean_square_error'], 0.0)
        self.assertIsNone(metrics['reference_edges'])
        self.assertEqual(metrics['reference_flat']['mean_absolute_error'], 0.0)
        self.assertEqual(diff.getpixel((10, 10)), (0, 0, 0))

    def test_flat_colors_across_resolutions_and_rgb_difference(self):
        reference = Image.new('RGB', (64, 48), (20, 40, 60))
        candidate = Image.new('RGB', (256, 192), (30, 40, 60))
        stats, image = compare_screenshot_pixels(reference, candidate)
        self.assertEqual(stats['candidate_source_size'], [256, 192])
        self.assertEqual(stats['reference_output_size'], [64, 48])
        self.assertAlmostEqual(stats['all_pixels']['mean_absolute_error'],
                               10 / 3, delta=.001)
        self.assertEqual(stats['all_pixels']['channel_mean_absolute_error'],
                         [10, 0, 0])
        self.assertEqual(image.size, (64, 48))
        self.assertEqual(image.getpixel((0, 0)), (10, 0, 0))
        self.assertEqual(difference_preview(image).size, image.size)

    def test_reference_edges_are_separate_from_flat_regions(self):
        a = Image.new('RGB', (64, 48), 'black')
        b = Image.new('RGB', (64, 48), 'black')
        ImageDraw.Draw(a).rectangle((10, 10, 50, 38), fill='white')
        ImageDraw.Draw(b).rectangle((13, 10, 53, 38), fill='white')
        result, _diff = compare_screenshot_pixels(a, b)
        self.assertGreater(result['edge_pixels_percent'], 0)
        self.assertLess(result['edge_pixels_percent'], 100)
        self.assertGreater(result['reference_edges']['mean_absolute_error'],
                           result['reference_flat']['mean_absolute_error'])
        self.assertEqual(result['registration'], 'none')

    def test_explicit_resampling_and_threshold_validation(self):
        self.assertEqual(set(RESAMPLE_MODES),
                         {'nearest', 'bilinear', 'bicubic', 'lanczos'})
        image = Image.new('RGB', (32, 24), 'white')
        for method in RESAMPLE_MODES:
            metrics, _diff = compare_screenshot_pixels(
                image, image, resampling=method)
            self.assertEqual(metrics['candidate_resize_filter'], method)
        with self.assertRaises(ValueError):
            compare_screenshot_pixels(image, image, resampling='unknown')
        for bad in (0, 256, 1.25, True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                compare_screenshot_pixels(image, image, edge_threshold=bad)


if __name__ == '__main__':
    unittest.main()
