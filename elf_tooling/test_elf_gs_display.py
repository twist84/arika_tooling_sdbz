"""Deterministic tests for GS register bits and SDBZ's DISPLAY2 packer."""
import unittest

from elf_gs_display import (
    find_display2_packers, pack_display, unpack_display, unpack_dispfb,
)


class GSDisplayTests(unittest.TestCase):
    def test_display_640x448_magh3(self):
        raw = pack_display(636, 50, 3, 0, 2559, 447)
        decoded = unpack_display(raw)
        self.assertEqual(decoded['dx'], 636)
        self.assertEqual(decoded['dy'], 50)
        self.assertEqual(decoded['dw'], 2559)
        self.assertEqual(decoded['dh'], 447)
        self.assertEqual(decoded['nominal_source_width'], 640)
        self.assertEqual(decoded['nominal_source_height'], 448)

    def test_display_512x448_magh4(self):
        decoded = unpack_display(pack_display(0, 0, 4, 0, 2559, 447))
        self.assertEqual(decoded['nominal_source_width'], 512)
        self.assertEqual(decoded['horizontal_magnification'], 5)

    def test_dispfb(self):
        raw = 10 | (8 << 9) | (0 << 15) | (12 << 32) | (24 << 43)
        self.assertEqual(unpack_dispfb(raw),
                         dict(fbp=10, fbw=8, psm=0, dbx=12, dby=24))

    def test_bounds(self):
        with self.assertRaises(ValueError):
            pack_display(4096, 0, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            unpack_display(-1)
        with self.assertRaises(ValueError):
            unpack_dispfb(1 << 64)

    def test_packer_signature(self):
        words = [0x240409ff, 0x0004283c, 0x3c030050,
                 0x000633f8, 0x8c64f384, 0x00c73025,
                 0x00a52825, 0x2484ffff, 0x3c031200,
                 0x0004203c, 0x0004203f, 0x0004233c,
                 0x00852025, 0x10000114, 0xfc6400a0, 0, 0]
        from struct import pack
        blob = pack('<%dI' % len(words), *words)
        found = find_display2_packers([(0x100000, blob)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['register_write_va'], '0x00100038')
        words[14] = 0
        self.assertEqual(find_display2_packers(
            [(0x100000, pack('<%dI' % len(words), *words))]), [])


if __name__ == '__main__':
    unittest.main()
