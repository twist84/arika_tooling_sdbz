import struct
import unittest
from arika_audio import ase_samples, ams_channels, decode_adpcm, sample_rate


class AudioTests(unittest.TestCase):
    def test_signed_nibbles(self):
        pcm, _ = decode_adpcm(bytes([12, 0]) + bytes([0x8f]) * 14)
        self.assertEqual(list(pcm), [-1, -8] * 14)

    def test_history_across_chunks(self):
        block = bytes([0x12, 0]) + bytes([0x12]) * 14
        whole, _ = decode_adpcm(block * 2)
        first, history = decode_adpcm(block)
        last, _ = decode_adpcm(block, history)
        self.assertEqual(whole, first + last)

    def test_pitch(self):
        self.assertEqual(sample_rate(4096), 48000)
        self.assertEqual(sample_rate(1536), 18000)
        self.assertEqual(sample_rate(1365), 15996)

    def test_bank(self):
        payload = bytes([12, 4]) + bytes(14) + bytes([12, 3]) + bytes(14)
        header = struct.pack('<5I', 100, 1, 32, 1536, 0).ljust(2048, b'\0')
        self.assertEqual(list(ase_samples(header + payload)), [(0, 18000, payload)])
        with self.assertRaises(ValueError):
            list(ase_samples(header + payload[:-1]))

    def test_stream_order_and_trim(self):
        # Physical blocks 0,1,2,3 become 0,2,3,1; two channel chunks per block.
        header = struct.pack('<4I', 120, 4096, 3 * 32768 + 16, 2).ljust(2048, b'\0')
        body = b''.join(bytes([i * 2]) * 32768 + bytes([i * 2 + 1]) * 32768 for i in range(4))
        rate, left, right = ams_channels(header + body)
        self.assertEqual(rate, 48000)
        self.assertEqual(left, bytes([0]) * 32768 + bytes([4]) * 32768 + bytes([6]) * 32768 + bytes([2]) * 16)
        self.assertEqual(right, bytes([1]) * 32768 + bytes([5]) * 32768 + bytes([7]) * 32768 + bytes([3]) * 16)

    def test_reject_invalid_frames(self):
        for payload in [bytes(15), bytes([0x50, 0]) + bytes(14), bytes([13, 0]) + bytes(14)]:
            with self.assertRaises(ValueError):
                decode_adpcm(payload)


if __name__ == '__main__':
    unittest.main()
