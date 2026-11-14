"""History-conditional recovered arrow placements and non-destructive bob."""
import json
from pathlib import Path
import unittest

from arika_menu_arrow_preview import arrow_parts, arrow_variant, bobbed_arrow_geometry


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

    def test_bob_translates_without_mutating_source(self):
        geometry = {'vertices': [[1, 2], [3, 4]], 'position': [1, 2],
                    'bounds': [1, 2, 3, 4], 'uv_endpoints': [0, 0, 2, 2]}
        shifted = bobbed_arrow_geometry(geometry, 8)
        self.assertAlmostEqual(shifted['vertices'][0][1], 5)
        self.assertEqual(shifted['uv_endpoints'], geometry['uv_endpoints'])
        self.assertEqual(geometry['vertices'][0], [1, 2])
        self.assertAlmostEqual(bobbed_arrow_geometry(geometry, 0)['vertices'][0][1], 2)


if __name__ == '__main__':
    unittest.main()
