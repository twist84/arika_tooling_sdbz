#!/usr/bin/env python3
"""Rebuild original ASE/AMS audio assets from edited signed 16-bit PCM WAVs."""
import argparse
from array import array
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import wave

from arika_audio import (HEADER, INTERLEAVE, COEFFICIENTS, ams_channels,
                         ase_samples, decode_adpcm, sample_rate)
from arika_dat import asset_path


def read_wave(path, channel_count):
    with wave.open(str(path), 'rb') as source:
        if source.getcomptype() != 'NONE' or source.getsampwidth() != 2:
            raise ValueError('WAV must be uncompressed signed 16-bit PCM')
        if source.getnchannels() != channel_count:
            raise ValueError('WAV must have %d channel(s)' % channel_count)
        rate, frames = source.getframerate(), source.getnframes()
        if not frames:
            raise ValueError('empty WAV')
        payload = source.readframes(frames)
        if len(payload) != frames * channel_count * 2:
            raise ValueError('truncated WAV data')
    samples = array('h')
    samples.frombytes(payload)
    if sys.byteorder != 'little':
        samples.byteswap()
    return rate, [samples[index::channel_count] for index in range(channel_count)]


def pitch_for_rate(rate, original_pitch):
    # Exported integer-Hz rates must recover the original fractional SPU2 pitch.
    if rate == sample_rate(original_pitch):
        return original_pitch
    pitch = (rate * 4096 + 24000) // 48000
    if not 1 <= pitch <= 0x3FFF:
        raise ValueError('WAV sample rate is outside the supported SPU2 pitch range')
    return pitch


def predict(h1, h2, c1, c2):
    # Truncate toward zero, matching the companion decoder and FFmpeg.
    value = h1 * c1 + h2 * c2
    return value // 64 if value >= 0 else -((-value) // 64)


def encode_adpcm(samples, first_flag=0, last_flag=0, minimum_frames=1):
    """Search five filters and nearby quantizer scales, retaining decoded history."""
    if not samples:
        raise ValueError('cannot encode empty audio')
    frame_count = max(minimum_frames, (len(samples) + 27) // 28)
    output = bytearray(frame_count * 16)
    h1 = h2 = 0
    for frame_index in range(frame_count):
        block = list(samples[frame_index * 28:(frame_index + 1) * 28])
        block += [0] * (28 - len(block))
        best = None
        for filter_index, (c1, c2) in enumerate(COEFFICIENTS):
            # Estimate scale using the input signal, then test adjacent scales
            # using actual quantized predictor feedback.
            a, b = h1, h2
            peak = 0
            for target in block:
                peak = max(peak, abs(target - predict(a, b, c1, c2)))
                b, a = a, target
            step = 1
            while step < 4096 and peak > 7 * step:
                step *= 2
            shift = 12 - (step.bit_length() - 1)
            for candidate_shift in range(max(0, shift - 1), min(12, shift + 1) + 1):
                quantizer = 1 << (12 - candidate_shift)
                a, b = h1, h2
                error = 0
                nibbles = []
                for target in block:
                    prediction = predict(a, b, c1, c2)
                    delta = target - prediction
                    nibble = (delta + quantizer // 2) // quantizer
                    nibble = max(-8, min(7, nibble))
                    decoded = prediction + nibble * quantizer
                    audible = max(-32768, min(32767, decoded))
                    error += (audible - target) ** 2
                    nibbles.append(nibble & 15)
                    b, a = a, decoded
                if best is None or error < best[0]:
                    best = (error, filter_index, candidate_shift, nibbles, a, b)
        _, filter_index, shift, nibbles, h1, h2 = best
        at = frame_index * 16
        output[at] = filter_index * 16 + shift
        output[at + 1] = first_flag if frame_index == 0 else 0
        if frame_index == frame_count - 1:
            output[at + 1] = last_flag
        for index in range(14):
            output[at + 2 + index] = nibbles[index * 2] | (nibbles[index * 2 + 1] << 4)
    return bytes(output)


def validate_timing(rate, frames, original_pitch, original_bytes, allow_duration_change):
    if not allow_duration_change and (rate != sample_rate(original_pitch) or frames != original_bytes // 16 * 28):
        raise ValueError('WAV rate/frame count differs from the original; keep its duration or use --allow-duration-change')


def rebuild_ase(original, wav_directory, allow_duration_change=False):
    samples = list(ase_samples(original))
    known = {'%03d.wav' % index for index, _, _ in samples}
    for path in wav_directory.glob('*.wav'):
        if path.name not in known:
            raise ValueError('unknown sample filename: ' + path.name)
    header = bytearray(original[:HEADER])
    payload = bytearray()
    records = []
    for index, _, compressed in samples:
        original_pitch, _ = struct.unpack_from('<II', original, 12 + index * 8)
        pitch = original_pitch
        path = wav_directory / ('%03d.wav' % index)
        if path.is_file():
            rate, channels = read_wave(path, 1)
            pcm = channels[0]
            validate_timing(rate, len(pcm), original_pitch, len(compressed), allow_duration_change)
            decoded, _ = decode_adpcm(compressed)
            changed = pcm != decoded
            if changed:
                compressed = encode_adpcm(pcm, 4, 3, minimum_frames=2)
            pitch = pitch_for_rate(rate, original_pitch)
            records.append(dict(sample_index=index, reencoded=changed, pitch=pitch,
                                source_frames=len(pcm), encoded_frames=len(compressed) // 16 * 28))
        struct.pack_into('<II', header, 12 + index * 8, pitch, len(payload))
        payload.extend(compressed)
    struct.pack_into('<I', header, 8, len(payload))
    result = bytes(header + payload)
    list(ase_samples(result))
    return result, records


def pack_ams(header, pitch, left, right):
    if len(left) != len(right) or not left or len(left) % 16:
        raise ValueError('invalid encoded stereo channels')
    pairs = (len(left) + 0xFFFF) // 0x10000
    body = bytearray(pairs * 0x20000)
    order = list(range(0, pairs * 2, 2)) + list(range(pairs * 2 - 1, 0, -2))
    for logical_index, physical_index in enumerate(order):
        start = logical_index * INTERLEAVE
        for channel_index, channel in enumerate((left, right)):
            chunk = channel[start:start + INTERLEAVE]
            at = physical_index * 0x10000 + channel_index * INTERLEAVE
            body[at:at + len(chunk)] = chunk
    header = bytearray(header[:HEADER])
    struct.pack_into('<4I', header, 0, 120, pitch, len(left), pairs)
    return bytes(header + body)


def rebuild_ams(original, wav_path, allow_duration_change=False):
    _, left, right = ams_channels(original)
    original_pitch, = struct.unpack_from('<I', original, 4)
    rate, channels = read_wave(wav_path, 2)
    validate_timing(rate, len(channels[0]), original_pitch, len(left), allow_duration_change)
    encoded = []
    changed = []
    for pcm, compressed in zip(channels, (left, right)):
        decoded, _ = decode_adpcm(compressed)
        changed.append(pcm != decoded)
        encoded.append(encode_adpcm(pcm) if changed[-1] else compressed)
    pitch = pitch_for_rate(rate, original_pitch)
    if not any(changed) and pitch == original_pitch:
        return original, [dict(reencoded_channels=changed, pitch=pitch, source_frames=len(channels[0]))]
    result = pack_ams(original[:HEADER], pitch, *encoded)
    ams_channels(result)
    return result, [dict(reencoded_channels=changed, pitch=pitch,
                         source_frames=len(channels[0]), encoded_frames=len(encoded[0]) // 16 * 28)]


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as target:
            temporary = Path(target.name)
            target.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('originals', type=Path, help='original extracted asset directory')
    parser.add_argument('wavs', type=Path, help='exported WAV directory; may contain only edited WAVs')
    parser.add_argument('output', type=Path, help='replacement asset directory for arika_dat.py repack')
    parser.add_argument('--allow-duration-change', action='store_true', help='allow changed frame counts/rates; game event timings are not updated')
    args = parser.parse_args()
    if not args.originals.is_dir() or not args.wavs.is_dir():
        parser.error('originals and wavs must be existing directories')
    roots = [path.resolve() for path in (args.originals, args.wavs, args.output)]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:]):
        parser.error('originals, wavs and output must be separate, non-overlapping directories')
    plan, errors = [], []
    # Resolve from provided WAVs so misspelled paths cannot be silently ignored.
    for path in sorted(args.wavs.rglob('*')):
        if not path.is_file() or path.suffix.lower() != '.wav':
            continue
        relative = path.relative_to(args.wavs)
        if relative.name.endswith('.ams.wav'):
            asset = relative.with_suffix('')
        elif relative.parent.suffix.lower() == '.ase':
            asset = relative.parent
        else:
            errors.append(dict(source=str(relative), error='expected asset.ams.wav or asset.ase/000.wav'))
            continue
        try:
            source = asset_path(args.originals, asset.as_posix())
            destination = asset_path(args.output, asset.as_posix())
            if not source.is_file():
                raise ValueError('original asset does not exist')
            if asset not in plan:
                plan.append(asset)
        except (ValueError, OSError) as error:
            errors.append(dict(source=str(relative), error=str(error)))
    if errors or not plan:
        for error in errors:
            print('ERROR:', error['source'], error['error'], file=sys.stderr)
        if not plan:
            print('ERROR: no matching audio WAVs found', file=sys.stderr)
        return 1
    records = []
    for asset in plan:
        try:
            source = asset_path(args.originals, asset.as_posix())
            destination = asset_path(args.output, asset.as_posix())
            original = source.read_bytes()
            wav_source = asset_path(args.wavs, asset.as_posix())
            if asset.suffix.lower() == '.ase':
                rebuilt, edits = rebuild_ase(original, wav_source, args.allow_duration_change)
            else:
                rebuilt, edits = rebuild_ams(original, wav_source.with_suffix('.ams.wav'), args.allow_duration_change)
            atomic_write(destination, rebuilt)
            records.append(dict(asset=asset.as_posix(), byte_identical=original == rebuilt,
                                original_bytes=len(original), rebuilt_bytes=len(rebuilt), edits=edits))
            print('Rebuilt', asset, flush=True)
        except (ValueError, OSError, wave.Error, struct.error) as error:
            errors.append(dict(source=asset.as_posix(), error=str(error)))
            print('ERROR:', asset, error, file=sys.stderr, flush=True)
    report = dict(assets=records, errors=errors, allow_duration_change=args.allow_duration_change)
    atomic_write(args.output / 'audio_import_manifest.json', (json.dumps(report, indent=2) + '\n').encode())
    print('Rebuilt %d assets; %d errors' % (len(records), len(errors)))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
