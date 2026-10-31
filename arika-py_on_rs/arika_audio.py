#!/usr/bin/env python3
"""Export Super Dragon Ball Z ASE banks and AMS streams to signed 16-bit WAV."""
import argparse
from array import array
import base64
import json
from pathlib import Path
import struct
import sys
import wave

import arika_backend as backend

HEADER = 0x800
INTERLEAVE = 0x8000
COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


def sample_rate(pitch):
    return backend.sample_rate(pitch)


def decode_adpcm(data, history=(0, 0)):
    """PS ADPCM, using FFmpeg-compatible prediction rounding and history."""
    if len(data) % 16:
        raise ValueError('partial ADPCM frame')
    output = array('h')
    h1, h2 = history
    append = output.append
    for at in range(0, len(data), 16):
        header, flags = data[at:at + 2]
        predictor, shift = header >> 4, header & 15
        if predictor > 4 or shift > 12 or flags > 7:
            raise ValueError('invalid ADPCM frame at 0x%x' % at)
        c1, c2 = COEFFICIENTS[predictor]
        for byte in data[at + 2:at + 16]:
            for nibble in (byte & 15, byte >> 4):
                signed = nibble - 16 if nibble & 8 else nibble
                value = ((signed * 4096) >> shift) + int((h1 * c1 + h2 * c2) / 64)
                if flags == 7:
                    value = 0
                append(max(-32768, min(32767, value)))
                h2, h1 = h1, value
    return output, (h1, h2)


def ase_samples(data):
    if len(data) < HEADER:
        raise ValueError('truncated ASE header')
    version, count, size = struct.unpack_from('<III', data)
    if version != 100 or size != len(data) - HEADER or 12 + count * 8 > HEADER:
        raise ValueError('invalid ASE header')
    entries = [struct.unpack_from('<II', data, 12 + i * 8) for i in range(count)]
    offsets = [entry[1] for entry in entries] + [size]
    if offsets[0] != 0 or any(a >= b or a % 16 for a, b in zip(offsets, offsets[1:])) or size % 16:
        raise ValueError('invalid ASE sample extents')
    for index, (pitch, offset) in enumerate(entries):
        end = offsets[index + 1]
        payload = data[HEADER + offset:HEADER + end]
        if payload[1] != 4 or payload[-15] != 3:
            raise ValueError('unexpected ASE start/end flags')
        yield index, sample_rate(pitch), payload


def ams_channels(data):
    if len(data) < HEADER:
        raise ValueError('truncated AMS header')
    version, pitch, channel_size, pairs = struct.unpack_from('<4I', data)
    if version != 120 or len(data) != HEADER + pairs * 0x20000:
        raise ValueError('invalid AMS header or padded size')
    if not 0 < channel_size <= pairs * 0x10000 or channel_size % 16:
        raise ValueError('invalid AMS audio length')
    # Physical stereo blocks: 0,2,4,... then ...,5,3,1 in playback order.
    order = list(range(0, pairs * 2, 2)) + list(range(pairs * 2 - 1, 0, -2))
    result = backend.ams_channels(data)
    left = base64.b64decode(result['left'])
    right = base64.b64decode(result['right'])
    rate = result['sample_rate']
    return rate, bytes(left[:channel_size]), bytes(right[:channel_size])


def write_wave(path, rate, channels):
    if len({len(channel) for channel in channels}) != 1:
        raise ValueError('unequal channel lengths')
    samples = array('h', [0]) * (len(channels[0]) * len(channels))
    for index, channel in enumerate(channels):
        samples[index::len(channels)] = channel
    if sys.byteorder != 'little':
        samples.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as target:
        target.setparams((len(channels), 2, rate, 0, 'NONE', 'not compressed'))
        target.writeframes(samples.tobytes())


def export_file(source, destination):
    data = source.read_bytes()
    records = []
    if source.suffix.lower() == '.ase':
        for index, rate, payload in ase_samples(data):
            pcm, _ = decode_adpcm(payload)
            path = destination / ('%03d.wav' % index)
            write_wave(path, rate, [pcm])
            records.append(dict(output=str(path), sample_index=index, channels=1,
                                sample_rate=rate, frames=len(pcm)))
    elif source.suffix.lower() == '.ams':
        rate, left, right = ams_channels(data)
        left, _ = decode_adpcm(left)
        right, _ = decode_adpcm(right)
        path = destination.with_suffix(destination.suffix + '.wav')
        write_wave(path, rate, [left, right])
        records.append(dict(output=str(path), channels=2, sample_rate=rate, frames=len(left)))
    else:
        raise ValueError('expected .ase or .ams')
    for record in records:
        record['source'] = str(source)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='one .ase/.ams or an extracted asset directory')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    sources = sorted(p for p in args.source.rglob('*') if p.is_file() and p.suffix.lower() in ('.ase', '.ams')) if args.source.is_dir() else [args.source]
    records, errors = [], []
    for source in sources:
        relative = source.relative_to(args.source) if args.source.is_dir() else Path(source.name)
        try:
            records.extend(export_file(source, args.output / relative))
            print('Exported', source, flush=True)
        except (ValueError, OSError) as error:
            errors.append(dict(source=str(source), error=str(error)))
            print('ERROR:', source, error, file=sys.stderr, flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'audio_manifest.json').write_text(json.dumps(dict(files=records, errors=errors), indent=2) + '\n')
    print('Exported %d WAV files; %d errors' % (len(records), len(errors)))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
