#!/usr/bin/env python3
"""Regenerate proprietary-image-free main menu poses from verified ELF research.

Usage:
    python arika_menu_layout_data.py research/main_menu_map.json \\
        ../examples/menu_shared_children_trace.json ../previews

Only numeric menu layout and motion data are emitted; no PIX, PNG or texture
base64 payload is read or written. Requires the existing Rust backend for
importing arika_menu_textured.py through arika_dat.
"""
import argparse
import json
from pathlib import Path


def write_layout_data(payload, report, destination, chunk_size=16):
    """Split numeric frames into files without ever copying texture images."""
    if payload.get('textures'):
        raise ValueError('layout writer refuses embedded texture images')
    if chunk_size < 1:
        raise ValueError('invalid chunk size')

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    frames = payload['frames']
    for part, start in enumerate(range(0, len(frames), chunk_size)):
        name = 'menu_frames_%03d.json' % part
        (destination / name).write_text(
            json.dumps(frames[start:start + chunk_size],
                       separators=(',', ':'), ensure_ascii=False) + '\n',
            encoding='utf-8')
        files.append(name)

    manifest = {
        'format': 'arika-menu-layout',
        'version': 1,
        'items': payload['items'],
        'background': payload['background'],
        'tint': payload['tint'],
        'frame_files': files,
        'frame_count': len(frames),
        'expected_texture_count': report['resource']['entry_count'],
        'provenance': {
            'elf_sha256': report['elf_sha256'],
            'note': ('Recovered menu geometry and sampled motion only; '
                     'requires user-provided dis/main_menu.pix. No artwork is embedded.'),
            'timing': ('Diagnostic sample-0..139 schedule; selection timing '
                       'and real input are not yet verified.'),
        },
    }
    (destination / 'menu_layout.json').write_text(
        json.dumps(manifest, separators=(',', ':'), ensure_ascii=False) + '\n',
        encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('trace', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    # Import here: tests for the writer do not need the native backend.
    from arika_menu_textured import build_payload
    report = json.loads(args.report.read_text(encoding='utf-8'))
    trace = json.loads(args.trace.read_text(encoding='utf-8'))
    payload = build_payload(report, None, trace)
    manifest = write_layout_data(payload, report, args.output)
    print('Wrote %d asset-free frames in %d JSON parts to %s' %
          (manifest['frame_count'], len(manifest['frame_files']), args.output))


if __name__ == '__main__':
    main()
