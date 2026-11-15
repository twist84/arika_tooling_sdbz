"""Tests for event-local selection emphasis (not native input timing)."""
import unittest
from arika_menu_selection_effect import (
    EMPHASIS_DURATION, emphasis_geometry, emphasis_sample,
)


class MenuSelectionEffectTests(unittest.TestCase):
    def test_delta_applies_to_current_pose_without_mutating_source(self):
        live = {'vertices': [[10, 20], [30, 40]], 'position': [20, 30, 70],
                'bounds': [10, 20, 30, 40], 'uv_endpoints': [0, 0, 2, 2]}
        base = {'vertices': [[1, 2], [3, 4]], 'position': [2, 3, 70],
                'bounds': [1, 2, 3, 4]}
        emphasized = {'vertices': [[4, 6], [6, 8]], 'position': [5, 7, 70],
                      'bounds': [4, 6, 6, 8]}
        changed = emphasis_geometry(live, base, emphasized)
        self.assertEqual(changed['vertices'], [[13, 24], [33, 44]])
        self.assertEqual(changed['position'], [23, 34, 70])
        self.assertEqual(changed['bounds'], [13, 24, 33, 44])
        self.assertEqual(changed['uv_endpoints'], [0, 0, 2, 2])
        self.assertEqual(live['vertices'][0], [10, 20])

    def test_missing_data_and_age_limits(self):
        frames = [{'tick': i} for i in range(100)]
        self.assertEqual(emphasis_sample(frames, 0)['tick'], 80)
        self.assertEqual(emphasis_sample(frames, 14.9)['tick'], 94)
        self.assertIsNone(emphasis_sample(frames, -1))
        self.assertIsNone(emphasis_sample(frames, EMPHASIS_DURATION))
        self.assertIsNone(emphasis_sample(frames, None))
        self.assertIsNone(emphasis_sample(frames[:90], 14))
        self.assertIsNone(emphasis_sample([{}] * 100, 1))
        self.assertIsNone(emphasis_geometry(None, {}, {}))


if __name__ == '__main__':
    unittest.main()
