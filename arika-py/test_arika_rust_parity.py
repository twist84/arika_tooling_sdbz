"""Shared golden fixtures checked by both the Python and Rust parsers."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUST_FIXTURES = ROOT.parent / "arika-rs" / "arika_core" / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

import arika_dat
import arika_models
import arika_stages
import arika_cht
import arika_menu_rng


class SharedRustParityFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((RUST_FIXTURES / "parity_fixtures.json").read_text(encoding="utf-8"))

    def test_stg_shared_golden(self):
        parsed = arika_stages.parse_stg((RUST_FIXTURES / "sample.stg").read_bytes())
        expected = self.expected["stg"]
        self.assertEqual(parsed["names"], expected["names"])
        self.assertEqual(parsed["template_count"], expected["template_count"])
        self.assertEqual(parsed["roots"], expected["roots"])
        self.assertEqual(len(parsed["nodes"]), expected["node_count"])
        self.assertEqual(parsed["nodes"][parsed["stage_root"]]["name"], expected["stage_root"])
        mesh = next(node for node in parsed["nodes"] if node["name"] == expected["mesh_instance"]["name"])
        self.assertEqual(mesh["translation"], expected["mesh_instance"]["translation"])

    def test_hit_shared_golden(self):
        parsed = arika_stages.parse_hit((RUST_FIXTURES / "sample.hit").read_bytes())
        expected = self.expected["hit"]
        self.assertEqual(len(parsed["objects"]), expected["object_count"])
        self.assertEqual(len(parsed["polygons"]), expected["polygon_count"])
        self.assertEqual(len(parsed["vertices"]), expected["vertex_count"])
        self.assertEqual(parsed["objects"][0]["name"], expected["object_name"])
        self.assertEqual(parsed["polygons"][0]["vertex_count"], expected["polygon_vertex_count"])

    def test_mot2_shared_golden(self):
        parsed = arika_models.parse_motion((RUST_FIXTURES / "sample.mot2").read_bytes())
        expected = self.expected["mot2"]
        self.assertEqual(parsed["fps"], expected["fps"])
        self.assertEqual(parsed["frame_count"], expected["frame_count"])
        self.assertEqual(len(parsed["nodes"]), expected["node_count"])
        self.assertEqual(parsed["channel_counts"], expected["channel_counts"])
        tracks = parsed["nodes"][0]["tracks"]
        self.assertEqual(tracks["translation"]["values"], expected["translation_values"])
        self.assertEqual(tracks["rotation"]["values"], expected["rotation_values"])
        self.assertEqual(tracks["scale"]["animated"], expected["scale_animated"])

    def test_tim2_shared_golden(self):
        width, height, rgba = arika_dat.tim2_rgba((RUST_FIXTURES / "sample.tim2").read_bytes())
        expected = self.expected["tim2"]
        self.assertEqual(width, expected["width"])
        self.assertEqual(height, expected["height"])
        self.assertEqual(rgba.hex(), expected["rgba_hex"])

    def test_cht_shared_golden(self):
        parsed = arika_cht.parse_cht((RUST_FIXTURES / "sample.cht").read_bytes())
        expected = self.expected["cht"]
        self.assertEqual(parsed["byte_size"], expected["byte_size"])
        self.assertEqual(parsed["name_table"], expected["name_table"])
        self.assertEqual(len(parsed["actions"]), expected["action_count"])
        action = parsed["actions"][0]
        self.assertEqual(action["motion_id"], expected["motion_id"])
        self.assertEqual(len(action["variants"]), expected["variant_count"])
        v0 = action["variants"][0]
        self.assertEqual(v0["motion_name"], expected["v0_motion_name"])
        self.assertEqual(v0["resource_bank"], expected["v0_resource_bank"])
        self.assertEqual(v0["child_blocks"], expected["v0_child_blocks"])
        v1 = action["variants"][1]
        self.assertEqual(v1["motion_name"], expected["v1_motion_name"])
        self.assertEqual(v1["resource_bank"], expected["v1_resource_bank"])

    def test_rng_shared_golden(self):
        expected = self.expected["rng"]
        s0, v0 = arika_menu_rng.next_rng(0)
        self.assertEqual(v0, expected["seed_0_next"])
        self.assertEqual(s0, expected["seed_0_state_after"])
        s1, v1 = arika_menu_rng.next_rng(1)
        self.assertEqual(v1, expected["seed_1_next"])
        self.assertEqual(s1, expected["seed_1_state_after"])


if __name__ == "__main__":
    unittest.main()
