"""No-disc unit tests for the ARKD_DVD.IRX fixture planning helpers."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).with_name("irx_boundary_fixture.py")
SPEC = importlib.util.spec_from_file_location("irx_boundary_fixture", MODULE)
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class IrxBoundaryFixtureTests(unittest.TestCase):
    def test_exact_boundary_counts_and_sorted_insertion(self):
        source = ["dis/a.bin", "ply/b.bin", "trc/z.bin"]
        source.extend(f"ply/asset_{i:04d}.bin" for i in range(1927))
        source.sort()
        for target in FIXTURE.TARGET_COUNTS:
            probes, ordered = FIXTURE.planned_names(source, target)
            self.assertEqual(len(ordered), target)
            self.assertEqual(len(probes), target - 1930)
            self.assertEqual(ordered, sorted(ordered))
            self.assertEqual(len(ordered), len(set(ordered)))
            self.assertEqual(ordered[0], probes[0] if probes else source[0])
            self.assertEqual(ordered[-1], "trc/z.bin")

    def test_rejects_incomplete_source_and_bad_target(self):
        with self.assertRaises(ValueError):
            FIXTURE.planned_names(["dis/a.bin"], 1931)
        with self.assertRaises(ValueError):
            FIXTURE.planned_names(["dis/a.bin"] * 1930, 1931)
        with self.assertRaises(ValueError):
            FIXTURE.planned_names([f"ply/{i:04d}" for i in range(1930)], 2048)

    def test_inventory_and_dry_run_do_not_copy_assets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            assets = root / "assets"
            for i in range(1930):
                p = assets / "dis" / f"{i:04d}.bin"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x")
            data = FIXTURE.make_fixture(
                assets, root / "output", 2005, "arika", dry_run=True
            )
            self.assertEqual(data["target_count"], 2005)
            self.assertEqual(data["added_probe_count"], 75)
            self.assertEqual(data["info_size"], 98304)
            self.assertEqual(data["minimum_game_size"], 2005 * 2048)
            self.assertTrue(data["record_2005"].startswith("dis/"))
            self.assertFalse((root / "output").exists())

    def test_rejects_insufficient_game_size(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            assets = root / "assets"
            for i in range(1930):
                p = assets / "dis" / f"{i:04d}.bin"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x")
            with self.assertRaises(ValueError):
                FIXTURE.make_fixture(
                    assets, root / "output", 2005, "arika",
                    dry_run=True, game_size=2048,
                )


if __name__ == "__main__":
    unittest.main()
