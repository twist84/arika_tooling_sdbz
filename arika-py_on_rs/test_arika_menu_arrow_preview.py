"""History-conditional recovered arrow placements and non-destructive bob."""
import json
from pathlib import Path
import unittest

from arika_menu_arrow_preview import (arrow_parts, arrow_variant, arrow_direction,
                                     native_arrow_displacement, bobbed_arrow_geometry)


class ArrowPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((Path(__file__).parent / 'research/main_menu_map.json').read_text())

    def test_conditional_layouts(self):
        self.assertEqual(arrow_variant(0, 2), 1)
        self.assertEqual(arrow_variant(0, 1), 0)
        for previous in (0, 1, 5):
            self.assertEqual(arrow_variant(2, previous), 1)
        self.assertEqual(arrow_variant(2, 6), 0)
        self.assertEqual(arrow_variant(3, 2), 0)
        self.assertEqual(len(arrow_parts(self.report, 0, 2)), 2)
        self.assertEqual(len(arrow_parts(self.report, 2, 0)), 3)

    def test_each_native_arrow_moves_only_along_its_own_axis(self):
        directions = {
            (81, 63, 113, 100): (0, -1),   # up
            (81, 100, 113, 63): (0, 1),    # down
            (0, 19, 37, 50): (-1, 0),      # left
            (37, 19, 0, 50): (1, 0),       # right
        }
        for uv, direction in directions.items():
            with self.subTest(uv=uv):
                geometry = {'vertices': [[1, 2], [3, 4]],
                            'position': [1, 2, 7],
                            'bounds': [1, 2, 3, 4],
                            'uv_endpoints': list(uv)}
                self.assertEqual(arrow_direction(geometry), direction)
                shifted = bobbed_arrow_geometry(geometry, 10)
                dx, dy = (3 * component for component in direction)
                self.assertAlmostEqual(shifted['vertices'][0][0], 1 + dx)
                self.assertAlmostEqual(shifted['vertices'][0][1], 2 + dy)
                self.assertAlmostEqual(shifted['position'][0], 1 + dx)
                self.assertAlmostEqual(shifted['position'][1], 2 + dy)
                self.assertEqual(shifted['position'][2], 7)
                self.assertEqual(shifted['bounds'],
                                 [1 + dx, 2 + dy, 3 + dx, 4 + dy])
                self.assertEqual(shifted['uv_endpoints'], geometry['uv_endpoints'])
                self.assertEqual(geometry['vertices'][0], [1, 2])
                self.assertEqual(geometry['position'], [1, 2, 7])
                self.assertEqual(bobbed_arrow_geometry(geometry, 0)['vertices'],
                                 geometry['vertices'])

    def test_every_extracted_arrow_has_known_direction(self):
        for item_index, item in enumerate(self.report['arrow_baselines']['items']):
            for variant_index, variant in enumerate(item['variants']):
                for part in variant:
                    with self.subTest(item=item_index, variant=variant_index):
                        dx, dy = arrow_direction(part['geometry'])
                        self.assertEqual(abs(dx) + abs(dy), 1)

    def test_native_interpolation_samples_and_wrapping(self):
        # Four table points from the actual 0x3753A0 helper.
        expected = {
            0: 0.0, 5: 1.5, 10: 3.0,
            15: 1.5, 20: 0.0, 25: -1.5,
            30: -3.0, 35: -1.5, 40: 0.0,
            45: 1.5, 70: -3.0, 80: 0.0,
        }
        for age, value in expected.items():
            with self.subTest(age=age):
                self.assertAlmostEqual(native_arrow_displacement(age), value)
        self.assertAlmostEqual(native_arrow_displacement(10.5), 2.85)
        self.assertAlmostEqual(native_arrow_displacement(30.5), -2.85)

    def test_no_sine_shape_between_keyframes(self):
        # A sine approximation at tick 5 would produce ~2.12 for amplitude 3;
        # the native curve is linear and yields exactly 1.5.
        self.assertEqual(native_arrow_displacement(5), 1.5)

    def test_unknown_uv_does_not_guess_direction(self):
        with self.assertRaisesRegex(ValueError, 'unrecognised'):
            arrow_direction({'uv_endpoints': [0, 0, 2, 2]})


if __name__ == '__main__':
    unittest.main()
