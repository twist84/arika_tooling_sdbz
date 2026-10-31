#!/usr/bin/env python3
"""Persistent settings for the Arika scene editor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


class c_editor_settings:
    """JSON-backed settings stored in ``~/.arika/editor_settings.json``."""
    k_version = 1
    k_recent_limit = 12

    def __init__(self, path=None):
        self.m_path = Path(path).expanduser() if path is not None else Path.home() / '.arika' / 'editor_settings.json'
        self.m_data = {
            'version': self.k_version,
            'recent_files': [],
            'last_stage_directory': '',
            'last_project_directory': '',
            'window_geometry': '',
            'window_state': '',
        }
        self.load()

    @property
    def path(self):
        return self.m_path

    def load(self):
        try:
            data = json.loads(self.m_path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        recent = data.get('recent_files', [])
        if not isinstance(recent, list):
            recent = []
        clean = []
        seen = set()
        for entry in recent:
            if not isinstance(entry, dict):
                continue
            kind, raw_path = entry.get('type'), entry.get('path')
            if kind not in ('stage', 'project') or not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = str(Path(raw_path).expanduser())
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            clean.append({'type': kind, 'path': path})
        self.m_data.update({
            'recent_files': clean[:self.k_recent_limit],
            'last_stage_directory': self._string(data.get('last_stage_directory')),
            'last_project_directory': self._string(data.get('last_project_directory')),
            'window_geometry': self._string(data.get('window_geometry')),
            'window_state': self._string(data.get('window_state')),
            'version': self.k_version,
        })

    @staticmethod
    def _string(value):
        return value if isinstance(value, str) else ''

    def save(self):
        self.m_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.m_data, indent=2, ensure_ascii=False) + '\n'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                    dir=str(self.m_path.parent), prefix=self.m_path.name + '.',
                    suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(self.m_path))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def recent_files(self, kind=None):
        entries = self.m_data['recent_files']
        return [dict(item) for item in entries if kind is None or item['type'] == kind]

    def add_recent_file(self, path, kind):
        if kind not in ('stage', 'project'):
            raise ValueError('recent file type must be stage or project')
        path = str(Path(path).expanduser().resolve())
        key = os.path.normcase(os.path.abspath(path))
        recent = [item for item in self.m_data['recent_files']
                  if os.path.normcase(os.path.abspath(item['path'])) != key]
        self.m_data['recent_files'] = [{'type': kind, 'path': path}] + recent
        self.m_data['recent_files'] = self.m_data['recent_files'][:self.k_recent_limit]

    def set_last_directory(self, kind, path):
        if kind not in ('stage', 'project'):
            raise ValueError('directory type must be stage or project')
        directory = Path(path).expanduser()
        if directory.is_file():
            directory = directory.parent
        self.m_data['last_%s_directory' % kind] = str(directory.resolve())

    def last_directory(self, kind):
        if kind not in ('stage', 'project'):
            raise ValueError('directory type must be stage or project')
        value = self.m_data['last_%s_directory' % kind]
        return value if value and Path(value).is_dir() else str(Path.home())

    def set_window_bytes(self, geometry, state):
        self.m_data['window_geometry'] = bytes(geometry.toBase64()).decode('ascii') if geometry else ''
        self.m_data['window_state'] = bytes(state.toBase64()).decode('ascii') if state else ''

    def restore_window(self, window):
        from PySide6 import QtCore
        geometry = self.m_data.get('window_geometry', '')
        state = self.m_data.get('window_state', '')
        if geometry:
            window.restoreGeometry(QtCore.QByteArray.fromBase64(geometry.encode('ascii')))
        if state:
            window.restoreState(QtCore.QByteArray.fromBase64(state.encode('ascii')))
