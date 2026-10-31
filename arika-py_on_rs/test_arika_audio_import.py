from array import array
import math
from pathlib import Path
import struct
import tempfile
import unittest

from arika_audio import ams_channels, ase_samples, decode_adpcm, write_wave
from arika_audio_import import (encode_adpcm, pack_ams, pitch_for_rate,
                               read_wave, rebuild_ams, rebuild_ase)


def sine(frames=280, period=53):
    return array('h', (round(12000 * math.sin(i * 2 * math.pi / period)) for i in range(frames)))


def bank(payloads):
    header = bytearray(2048)
    struct.pack_into('<III', header, 0, 100, len(payloads), sum(map(len, payloads)))
    offset = 0
    for index, payload in enumerate(payloads):
        struct.pack_into('<II', header, 12 + index * 8, 1536, offset)
        offset += len(payload)
    header[2000:2004] = b'KEEP'
    return bytes(header) + b''.join(payloads)


class AudioImportTests(unittest.TestCase):
    def test_encoder_silence(self):
        encoded = encode_adpcm(array('h', [0] * 56), 4, 3, 2)
        self.assertEqual(encoded[1], 4)
        self.assertEqual(encoded[-15], 3)
        self.assertEqual(decode_adpcm(encoded)[0], array('h', [0] * 56))

    def test_encoder_quality_and_padding(self):
        original = sine(281)
        encoded = encode_adpcm(original)
        decoded, _ = decode_adpcm(encoded)
        self.assertEqual(len(decoded), 308)
        signal = sum(x * x for x in original)
        error = sum((x - y) ** 2 for x, y in zip(original, decoded))
        self.assertGreater(10 * math.log10(signal / error), 35)

    def test_encoder_extremes(self):
        pcm = array('h', [-32768, 32767] * 28)
        decoded, _ = decode_adpcm(encode_adpcm(pcm))
        self.assertEqual(len(decoded), len(pcm))
        self.assertLess(max(abs(a - b) for a, b in zip(pcm, decoded)), 5000)

    def test_ams_inverse_multi_unit(self):
        left = bytes(range(256)) * 600
        right = bytes(reversed(range(256))) * 600
        header = bytearray(2048)
        header[2000:2004] = b'KEEP'
        encoded = pack_ams(header, 4096, left, right)
        rate, out_left, out_right = ams_channels(encoded)
        self.assertEqual((rate, out_left, out_right), (48000, left, right))
        self.assertEqual(encoded[2000:2004], b'KEEP')

    def test_ase_noop_partial_edit_and_resize(self):
        first = encode_adpcm(sine(), 4, 3, 2)
        second = encode_adpcm(sine(period=31), 4, 3, 2)
        original = bank([first, second])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            write_wave(folder / '000.wav', 18000, [decode_adpcm(first)[0]])
            result, _ = rebuild_ase(original, folder)
            self.assertEqual(result, original)
            write_wave(folder / '000.wav', 18000, [array('h', [0] * 280)])
            result, _ = rebuild_ase(original, folder)
            samples = list(ase_samples(result))
            self.assertEqual(samples[1][2], second)
            self.assertEqual(result[2000:2004], b'KEEP')
            self.assertEqual(decode_adpcm(samples[0][2])[0], array('h', [0] * 280))
            write_wave(folder / '000.wav', 18000, [sine(300)])
            with self.assertRaises(ValueError):
                rebuild_ase(original, folder)
            result, _ = rebuild_ase(original, folder, True)
            self.assertEqual(len(list(ase_samples(result))[0][2]), 11 * 16)
            self.assertEqual(list(ase_samples(result))[1][2], second)

    def test_ams_noop_one_channel_edit_and_resize(self):
        left = encode_adpcm(sine())
        right = encode_adpcm(sine(period=31))
        original = pack_ams(bytes(2048), 4096, left, right)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio.wav'
            write_wave(path, 48000, [decode_adpcm(left)[0], decode_adpcm(right)[0]])
            self.assertEqual(rebuild_ams(original, path)[0], original)
            write_wave(path, 48000, [array('h', [0] * 280), decode_adpcm(right)[0]])
            result, edits = rebuild_ams(original, path)
            _, new_left, new_right = ams_channels(result)
            self.assertEqual(new_right, right)
            self.assertEqual(edits[0]['reencoded_channels'], [True, False])
            self.assertEqual(decode_adpcm(new_left)[0], array('h', [0] * 280))
            write_wave(path, 48000, [sine(301), sine(301, 31)])
            with self.assertRaises(ValueError):
                rebuild_ams(original, path)
            result, _ = rebuild_ams(original, path, True)
            self.assertEqual(len(ams_channels(result)[1]), 11 * 16)

    def test_wave_channels_and_pitch(self):
        self.assertEqual(pitch_for_rate(15996, 1365), 1365)
        self.assertEqual(pitch_for_rate(44100, 4096), 3763)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mono.wav'
            write_wave(path, 18000, [sine()])
            with self.assertRaises(ValueError):
                read_wave(path, 2)

    def test_unknown_slot_rejected(self):
        original = bank([encode_adpcm(sine(), 4, 3, 2)])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            write_wave(folder / '123.wav', 18000, [sine()])
            with self.assertRaises(ValueError):
                rebuild_ase(original, folder)


if __name__ == '__main__':
    unittest.main()
