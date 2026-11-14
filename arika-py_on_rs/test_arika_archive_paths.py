"""Archive entrypoint regression tests for the integrated main-menu preview."""
import tempfile
from pathlib import Path
import unittest

from arika_archive_paths import resolve_archive_paths


class ArchivePathsTests(unittest.TestCase):
    def test_open_info_dat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = root / 'INFO.DAT'
            game = root / 'GAME.DAT'
            info.touch()
            game.touch()
            self.assertEqual(resolve_archive_paths(info), (info, game))

    def test_open_game_dat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = root / 'INFO.DAT'
            game = root / 'GAME.DAT'
            info.touch()
            game.touch()
            self.assertEqual(resolve_archive_paths(game), (info, game))
            self.assertEqual(resolve_archive_paths(game, info), (info, game))

    def test_info_only_and_missing_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = root / 'INFO.DAT'
            game = root / 'GAME.DAT'
            info.touch()
            self.assertEqual(resolve_archive_paths(info), (info, None))
            with self.assertRaisesRegex(FileNotFoundError, 'INFO.DAT'):
                resolve_archive_paths(game)


if __name__ == '__main__':
    unittest.main()
