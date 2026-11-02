#!/usr/bin/env python3
"""Super Dragon Ball Z .ani animation parser.

ANI files contain per-track skeletal animation keyframes.

Format (inferred from ELF cross-referencing at 0x004CFAF0 "%s.ani"):
  * 0x00: u32 track_count
  * 0x04-0x0C: reserved (zeros)
  * 0x10+: track_count pairs of (u32 frame_count, u32 file_offset)
  * At each track offset:
      - frame_count x u32 relative frame offsets (from track data start)
      - Frame records at those offsets (best-effort interpretation):
          u32 frame_index, u8 bone_index, u8 channel_count, u8 pad[2],
          then channel_count x float32 values
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_ani(data):
    """Parse an .ani animation file."""
    require(len(data) >= 0x10, "truncated ANI header")
    track_count = struct.unpack_from('<I', data, 0)[0]
    require(track_count > 0 and track_count <= 1024, "invalid track count")

    # Reserved 12 bytes
    for off in (4, 8, 0xC):
        val = struct.unpack_from('<I', data, off)[0]
        require(val == 0, f"reserved field at 0x{off:X} must be zero")

    # Track table at 0x10: (frame_count, file_offset) pairs
    table_end = 0x10 + track_count * 8
    require(table_end <= len(data), "truncated track table")

    tracks = []
    for i in range(track_count):
        frame_count, file_offset = struct.unpack_from('<II', data, 0x10 + i * 8)
        require(frame_count > 0 and frame_count <= 65536,
                f"track {i}: invalid frame count {frame_count}")
        require(file_offset < len(data),
                f"track {i}: offset 0x{file_offset:X} beyond file")
        tracks.append({
            'index': i,
            'frame_count': frame_count,
            'offset': file_offset,
            'frames': [],
        })

    # Parse each track
    for track in tracks:
        base = track['offset']
        require(base + track['frame_count'] * 4 <= len(data),
                f"track {track['index']}: truncated frame offset table")

        # Read frame offset table
        frame_offsets = list(struct.unpack_from(
            '<' + 'I' * track['frame_count'], data, base))

        # Parse each frame (best-effort; frame record format is inferred)
        for j, rel_off in enumerate(frame_offsets):
            fpos = base + rel_off
            if fpos + 8 > len(data):
                track['frames'].append({
                    'index': j,
                    'error': 'truncated frame header',
                    'file_offset': fpos,
                })
                continue

            frame_index = struct.unpack_from('<I', data, fpos)[0]
            bone_index = data[fpos + 4]
            channel_count = data[fpos + 5]
            pad1 = data[fpos + 6]
            pad2 = data[fpos + 7]

            fdata_start = fpos + 8
            available = len(data) - fdata_start
            readable_channels = min(channel_count, available // 4)

            channels = []
            truncated = False
            if readable_channels < channel_count:
                truncated = True
            for k in range(readable_channels):
                val = struct.unpack_from('<f', data, fdata_start + k * 4)[0]
                if not math.isfinite(val):
                    truncated = True
                channels.append(val)

            track['frames'].append({
                'index': j,
                'frame_index': frame_index,
                'bone_index': bone_index,
                'channel_count': channel_count,
                'channels_read': readable_channels,
                'channels': channels,
                'pad1': pad1,
                'pad2': pad2,
                'truncated': truncated,
                'file_offset': fpos,
            })

    return {
        'format': 'ARIKA_ANI',
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'byte_size': len(data),
        'track_count': track_count,
        'tracks': tracks,
        'scope': 'Track structure decoded; frame channel semantics (translation/rotation/scale per bone) are inferred but not fully validated. Some frames may be truncated due to uncertain record layout.',
    }


def ani_summary(doc):
    """Human-readable summary of parsed ANI data."""
    lines = [
        f"Format: {doc['format']}",
        f"Size: {doc['byte_size']} bytes",
        f"SHA-256: {doc['source_sha256']}",
        f"Tracks: {doc['track_count']}",
    ]
    total_frames = sum(len(t['frames']) for t in doc['tracks'])
    total_truncated = sum(
        1 for t in doc['tracks'] for f in t['frames'] if f.get('truncated')
    )
    lines.append(f"Total frames: {total_frames}")
    if total_truncated:
        lines.append(f"Truncated frames: {total_truncated}")
    for t in doc['tracks']:
        bones = set(f.get('bone_index', 0) for f in t['frames']
                   if 'bone_index' in f)
        chans = set(f.get('channel_count', 0) for f in t['frames']
                    if 'channel_count' in f)
        lines.append(
            f"  Track {t['index']}: {len(t['frames'])} frames, "
            f"bones={sorted(bones)}, channel_counts={sorted(chans)}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('json'); p.add_argument('ani'); p.add_argument('output')
    p = subs.add_parser('summary'); p.add_argument('ani')
    args = parser.parse_args()
    try:
        result = parse_ani(Path(args.ani).read_bytes())
        if args.command == 'json':
            Path(args.output).write_bytes(json.dumps(result, indent=2).encode())
            print('Wrote ' + args.output)
        else:
            print(ani_summary(result))
    except (OSError, ValueError, struct.error) as error:
        print('error: ' + str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
