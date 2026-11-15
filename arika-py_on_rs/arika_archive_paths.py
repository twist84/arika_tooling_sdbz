"""Resolve the two-file Arika archive pair independently of the selected file.

The backend expects INFO.DAT first, followed by GAME.DAT. In particular,
selecting GAME.DAT in the file dialog must not reverse those arguments.
"""
from pathlib import Path


def resolve_archive_paths(info_path, game_path=None):
    info_path = Path(info_path)
    game_path = Path(game_path) if game_path is not None else None

    if game_path is not None:
        if info_path.name.upper() == 'GAME.DAT' and game_path.name.upper() == 'INFO.DAT':
            return game_path, info_path
        return info_path, game_path

    if info_path.name.upper() == 'GAME.DAT':
        candidate = info_path.with_name('INFO.DAT')
        if not candidate.is_file():
            raise FileNotFoundError('INFO.DAT is required alongside GAME.DAT')
        return candidate, info_path

    if info_path.name.upper() == 'INFO.DAT':
        candidate = info_path.with_name('GAME.DAT')
        return info_path, candidate if candidate.is_file() else None

    return info_path, None
