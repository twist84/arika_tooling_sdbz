"""Synthetic ELF regression for cross-region video-mode instruction discovery."""
import struct
import unittest

from elf_video_modes import decode_jal, find_default_geometry, load_segments


class VideoModeProbeTests(unittest.TestCase):
    def test_program_header_and_relocated_jal(self):
        data = bytearray(0x100)
        data[:6] = bytes((127, 69, 76, 70, 1, 1))
        struct.pack_into('<H', data, 18, 8)
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        struct.pack_into('<8I', data, 52, 1, 0x80, 0x100000, 0x100000,
                         64, 64, 5, 128)
        words = [
            0x24040280, 0x240501c0, 0, 0x0080302d,
            0, 0x00a0382d, 0x0c040040, 0x0000402d,
        ]
        struct.pack_into('<8I', data, 0x80, *words)
        found = find_default_geometry(load_segments(data))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['immediates_va'], '0x00100000')
        self.assertEqual(found[0]['validator_va'], '0x00100100')
        self.assertEqual(found[0]['width'], 640)
        self.assertEqual(found[0]['height'], 448)

        # The site must include the argument-copy instructions, not
        # merely contain coincidental width and height constants.
        struct.pack_into('<I', data, 0x80 + 3 * 4, 0)
        self.assertEqual(find_default_geometry(load_segments(data)), [])

    def test_reject_bad_input(self):
        with self.assertRaises(ValueError):
            load_segments(b'bad')
        with self.assertRaises(ValueError):
            decode_jal(0, 0)


if __name__ == '__main__':
    unittest.main()
