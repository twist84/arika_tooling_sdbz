"""Regression tests for seedless INFO.DAT/GAME.DAT creation."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import arika_dat as dat


class SeedlessArchiveTests(unittest.TestCase):
    def test_roundtrip_multiple_assets_and_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            (assets / "dir").mkdir(parents=True)
            payloads = {
                "dir/alpha.bin": b"alpha" * 411,
                "empty.bin": b"",
                "last.bin": bytes(range(256)),
            }
            for name, data in payloads.items():
                target = assets / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

            info = root / "out" / "INFO.DAT"
            game = root / "out" / "GAME.DAT"
            dat.create_from_dir("usa", None, assets, info, game)
            archive = dat.Archive(info, game)
            self.assertEqual(archive.encoded[0], 0xC2)
            self.assertEqual({entry.name for entry in archive.entries}, set(payloads))
            for entry in archive.entries:
                self.assertEqual(entry.offset % dat.SECTOR, 0)
                self.assertEqual(entry.sectors, (entry.size + dat.SECTOR - 1) // dat.SECTOR)
                with game.open("rb") as handle:
                    handle.seek(entry.offset)
                    self.assertEqual(handle.read(entry.size), payloads[entry.name])

            # Identical input must yield identical INFO and GAME output.
            info_before, game_before = info.read_bytes(), game.read_bytes()
            dat.create_from_dir("usa", None, assets, info, game)
            self.assertEqual(info.read_bytes(), info_before)
            self.assertEqual(game.read_bytes(), game_before)

    def test_seedless_cli_produces_both_archives_without_game_option(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "file.bin").write_bytes(b"test")
            output = root / "out"
            result = subprocess.run(
                [sys.executable, str(Path(dat.__file__).resolve()), "repack",
                 str(output), "--replacements", str(assets), "--version", "eu"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = dat.Archive(output / "INFO.DAT", output / "GAME.DAT")
            self.assertEqual(archive.entries[0].name, "file.bin")
            self.assertEqual(archive.encoded[0], 0x11)

    def test_rejects_missing_source_and_output_inside_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                dat.create_from_dir("usa", None, root / "missing", root / "INFO.DAT")
            assets = root / "assets"
            assets.mkdir()
            (assets / "file.bin").write_bytes(b"test")
            with self.assertRaises(ValueError):
                dat.create_from_dir("usa", None, assets, assets / "out" / "INFO.DAT",
                                    assets / "out" / "GAME.DAT")

    def test_rejects_case_collisions_and_bad_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "File.bin").write_bytes(b"a")
            (assets / "file.bin").write_bytes(b"b")
            with self.assertRaisesRegex(ValueError, "case-colliding"):
                dat.create_from_dir("usa", None, assets, root / "INFO.DAT")

            with self.assertRaisesRegex(ValueError, "codec key"):
                dat.create_from_dir(None, bytes(16), assets, root / "INFO.DAT")


if __name__ == "__main__":
    unittest.main()
