"""No copyrighted fixtures: compare synthetic 4:3 menu animation frames."""
import unittest
from PIL import Image, ImageDraw

from arika_menu_frame_match import (
    REFERENCE_SIZE, normalize_reference, pose_score, rank_samples,
)


class MenuFrameMatcherTests(unittest.TestCase):
    def test_four_three_and_crop_validation(self):
        self.assertEqual(normalize_reference(
            Image.new('RGB', (960, 720))).size, REFERENCE_SIZE)
        with self.assertRaisesRegex(ValueError, 'crop screenshot'):
            normalize_reference(Image.new('RGB', (1280, 720)))
        with self.assertRaisesRegex(ValueError, 'too small'):
            normalize_reference(Image.new('RGB', (32, 24)))

    def test_rank_matching_pose(self):
        def frame(x):
            image = Image.new('RGB', REFERENCE_SIZE, '#303a40')
            ImageDraw.Draw(image).rectangle((x, 30, x+32, 95),
                                           fill='#f1a040')
            return image

        target = frame(112)
        candidates = [(12, frame(78)), (25, frame(112)), (30, frame(139))]
        self.assertEqual(rank_samples(target, candidates)[0][1], 25)
        self.assertEqual(pose_score(target, target), 0.0)
        self.assertGreater(pose_score(target, frame(78)), 0)
        with self.assertRaises(ValueError):
            rank_samples(target, candidates, top_n=0)


if __name__ == '__main__':
    unittest.main()
