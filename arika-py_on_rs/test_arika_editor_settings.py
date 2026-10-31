import json
from pathlib import Path
import tempfile
import unittest

from arika_editor_settings import c_editor_settings


class test_editor_settings(unittest.TestCase):
    def test_recent_stage_and_project_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / 'arena.stg'
            project = root / 'arena.arika-scene.json'
            stage.write_bytes(b'stg')
            project.write_text('{}', encoding='utf-8')
            settings_path = root / '.arika' / 'editor_settings.json'
            settings = c_editor_settings(settings_path)
            settings.add_recent_file(stage, 'stage')
            settings.add_recent_file(project, 'project')
            settings.add_recent_file(stage, 'stage')
            settings.save()

            raw = json.loads(settings_path.read_text(encoding='utf-8'))
            self.assertEqual(raw['version'], 1)
            self.assertEqual([item['type'] for item in raw['recent_files']], ['stage', 'project'])
            reloaded = c_editor_settings(settings_path)
            self.assertEqual(reloaded.recent_files('stage')[0]['path'], str(stage.resolve()))
            self.assertEqual(reloaded.recent_files('project')[0]['path'], str(project.resolve()))

    def test_invalid_settings_and_recent_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text(json.dumps({'recent_files': [None, {'type': 'unknown', 'path': 'x'},
                {'type': 'project', 'path': 'good.json'}, {'type': 'project', 'path': 'good.json'}]}), encoding='utf-8')
            settings = c_editor_settings(path)
            self.assertEqual(settings.recent_files(), [{'type': 'project', 'path': 'good.json'}])

    def test_recent_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = c_editor_settings(Path(tmp) / 'settings.json')
            for i in range(20):
                settings.add_recent_file(Path(tmp) / ('%02d.stg' % i), 'stage')
            self.assertEqual(len(settings.recent_files()), 12)
            self.assertTrue(settings.recent_files()[0]['path'].endswith('19.stg'))


if __name__ == '__main__':
    unittest.main()
