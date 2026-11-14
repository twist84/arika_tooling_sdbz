"""Tests for generating publishable menu layout data without game images."""
import json
from pathlib import Path
import tempfile
import unittest

from arika_menu_layout_data import write_layout_data


class MenuLayoutWriterTests(unittest.TestCase):
    def test_writes_only_frames_and_layout(self):
        report = {'resource': {'entry_count': 13}, 'elf_sha256': 'example'}
        payload = {
            'textures': [],
            'items': [{'first': [], 'middle': [], 'overlay': [], 'arrows': []}],
            'background': {'vertices': []},
            'tint': {'vertices': []},
            'frames': [{'tick': i, 'payload': [i * 7]} for i in range(5)],
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_layout_data(payload, report, tmp, chunk_size=2)
            self.assertEqual(manifest['expected_texture_count'], 13)
            self.assertEqual(manifest['frame_files'], [
                'menu_frames_000.json', 'menu_frames_001.json',
                'menu_frames_002.json'])
            loaded = json.loads((Path(tmp) / 'menu_layout.json').read_text())
            self.assertNotIn('textures', loaded)
            self.assertEqual(loaded['frame_count'], 5)
            frames = []
            for filename in loaded['frame_files']:
                frames.extend(json.loads((Path(tmp) / filename).read_text()))
            self.assertEqual(frames, payload['frames'])
            for path in Path(tmp).iterdir():
                self.assertNotIn('png', path.read_text().lower())
                self.assertNotIn('base64', path.read_text().lower())

    def test_refuses_embedded_artwork(self):
        report = {'resource': {'entry_count': 13}, 'elf_sha256': 'example'}
        payload = {'textures': [{'index': 0, 'png': 'data:image/png;base64,abcd'}],
                   'frames': []}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'texture'):
                write_layout_data(payload, report, tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_rejects_invalid_chunk_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'chunk'):
                write_layout_data({'textures': [], 'frames': []},
                                  {'resource': {'entry_count': 13}}, tmp, 0)


if __name__ == '__main__':
    unittest.main()
