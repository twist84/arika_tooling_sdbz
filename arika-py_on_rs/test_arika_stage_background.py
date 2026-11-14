"""Regression tests for the native stage background tables."""
import unittest

from arika_stage_background import (
    STAGE_CLASS_RGB, default_stage_background, stage_background_choices,
    stage_background_rgba,
)


class StageBackgroundTests(unittest.TestCase):
    def test_elf_contains_sixteen_presets_in_thirteen_stage_classes(self):
        self.assertEqual(len(STAGE_CLASS_RGB), 13)
        self.assertEqual(sum(len(value) for value in STAGE_CLASS_RGB.values()), 16)
        self.assertEqual(STAGE_CLASS_RGB['CStage01'], ((30, 164, 212),))
        self.assertEqual(STAGE_CLASS_RGB['CStage05'], ((90, 164, 54), (31, 71, 40)))
        self.assertEqual(STAGE_CLASS_RGB['CStage08'], ((20, 4, 29),))

    def test_shared_asset_still_has_distinct_native_stage_classes(self):
        a=stage_background_choices('stg/s01/s01a.stg')
        b=stage_background_choices(r'C:\Extracted\stg\s02\s02a.stg')
        self.assertEqual([v['key'] for v in a], ['CStage01:0', 'CStage08:0'])
        self.assertEqual([v['key'] for v in b], ['CStage02:0', 'CStage09:0'])
        self.assertNotEqual(a[0]['rgb'], a[1]['rgb'])
        self.assertNotEqual(b[0]['rgb'], b[1]['rgb'])

    def test_stage_state_and_asset_suffix(self):
        self.assertEqual(default_stage_background('s03a.stg'), 'CStage03:0')
        self.assertEqual(default_stage_background('s03b.stg'), 'CStage03:1')
        self.assertEqual(default_stage_background('s04a.stg'), 'CStage04:0')
        self.assertEqual(default_stage_background('s04b.stg'), 'CStage04:1')
        self.assertEqual(default_stage_background('s05a.stg'), 'CStage05:0')
        self.assertEqual(len(stage_background_choices('s05a.stg')), 2)
        self.assertEqual(len(stage_background_choices('s03b.stg')), 2)

    def test_color_components_remain_display_encoded_rgb(self):
        self.assertEqual(stage_background_rgba('CStage01:0'),
                         (30/255, 164/255, 212/255, 1))
        self.assertEqual(stage_background_rgba('CStage05:1'),
                         (31/255, 71/255, 40/255, 1))
        self.assertIsNone(stage_background_rgba('CStage05:2'))
        self.assertIsNone(stage_background_rgba('CStage99:0'))
        self.assertIsNone(stage_background_rgba(None))

    def test_unknown_stages_do_not_pick_arbitrary_colors(self):
        self.assertEqual(stage_background_choices('unknown.stg'), ())
        self.assertIsNone(default_stage_background('unknown.stg'))
        self.assertEqual(stage_background_choices(None), ())


if __name__ == '__main__':
    unittest.main()
