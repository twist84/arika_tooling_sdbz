import tempfile
import unittest
from pathlib import Path
import struct
import arika_dat as dat


def info(name="dir/test.bin", size=3, sectors=1):
    header = dat.MAGIC + bytes(28) + struct.pack("<I", 1)
    record = name.encode("cp932").ljust(32, b"\0") + struct.pack("<4I", 0, 0, sectors, size)
    return dat.encode_info(header + record + b"\x40" * 32)


class ArchiveTests(unittest.TestCase):
    def test_codec_all_byte_values(self):
        for first_byte in range(256):
            with self.subTest(first_byte=first_byte):
                plain = bytes([first_byte]) + dat.MAGIC[1:] + bytes(range(256)) * 7
                self.assertEqual(dat.decode_info(dat.encode_info(plain)), plain)

    def test_extract_and_repack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ip, gp = root / "INFO.DAT", root / "GAME.DAT"
            original_info = info()
            original_game = b"abc" + b"\x7e" * 2045 + bytes(2048)
            ip.write_bytes(original_info); gp.write_bytes(original_game)
            archive = dat.Archive(ip, gp)
            dat.extract(archive, root / "assets")
            self.assertEqual((root / "assets/dir/test.bin").read_bytes(), b"abc")
            dat.rebuild(archive, root / "rebuilt")
            self.assertEqual((root / "rebuilt/INFO.DAT").read_bytes(), original_info)
            self.assertEqual((root / "rebuilt/GAME.DAT").read_bytes(), original_game)
            (root / "assets/dir/test.bin").write_bytes(b"longer test")
            dat.rebuild(archive, root / "modified", root / "assets")
            changed = dat.Archive(root / "modified/INFO.DAT", root / "modified/GAME.DAT")
            self.assertEqual(changed.entries[0].size, 11)
            self.assertEqual(changed.game.stat().st_size, len(original_game))
            self.assertEqual(changed.game.read_bytes()[:11], b"longer test")
            self.assertEqual(ip.read_bytes(), original_info)
            self.assertEqual(gp.read_bytes(), original_game)
            with self.assertRaises(ValueError): dat.rebuild(archive, root)
            (root / "assets/dir/test.bin").write_bytes(bytes(9000))
            with self.assertRaises(ValueError): dat.rebuild(archive, root / "overflow", root / "assets")

    def test_unsafe_path_and_bad_extents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); ip, gp = root / "INFO.DAT", root / "GAME.DAT"
            gp.write_bytes(bytes(2048))
            ip.write_bytes(info("../escape"))
            with self.assertRaises(ValueError): dat.Archive(ip, gp)
            ip.write_bytes(info(size=4096, sectors=1))
            with self.assertRaises(ValueError): dat.Archive(ip, gp)
            ip.write_bytes(info(size=4096, sectors=2))
            with self.assertRaises(ValueError): dat.Archive(ip, gp)

    def test_container(self):
        chunk = b"XPIX" + struct.pack("<I", 40) + bytes(24) + b"TIM2abcd"
        data = b"FPIX" + struct.pack("<III", 36 + len(chunk), 1, 0x100) + bytes(16) + struct.pack("<I", 36) + chunk
        result = dat.container(data)
        self.assertEqual(result["chunks"][0]["offset"], 36)
        self.assertEqual(result["chunks"][0]["magic"], "XPIX")
        with self.assertRaises(ValueError): dat.container(data[:-1])

    def test_rfsm(self):
        data = bytearray(112)
        data[:16] = b"RFSML3" + struct.pack("<HII", 1, 48, 85)
        data[16:32] = b"test.mot".ljust(16, b"\0")
        struct.pack_into("<4I", data, 32, 96, 16, 0, 0x10006)
        struct.pack_into("<HHIII", data, 48, 1, 1, 64, 80, 84)
        data[64:80] = b"HipRoot".ljust(16, b"\0"); data[84] = 0x22
        data[96:104] = b"MOT2" + struct.pack("<I", 16)
        result = dat.motion_archive(data)
        self.assertEqual(result["bones"][0]["name"], "HipRoot")
        self.assertEqual(result["motions"][0]["name"], "test.mot")

    def test_tim2(self):
        data = bytearray(128 + 128 + 2 + 1024)
        data[:8] = b"TIM2" + struct.pack("<BBH", 4, 1, 1)
        struct.pack_into("<IIIHHBBBBHH", data, 128, 128 + 2 + 1024, 1024, 2, 128, 256, 0, 1, 3, 5, 2, 1)
        data[256:258] = bytes([0, 8])
        data[258:262] = bytes([255, 0, 0, 128])
        data[258 + 8 * 4:262 + 8 * 4] = bytes([0, 0, 255, 128])
        data[258 + 16 * 4:262 + 16 * 4] = bytes([0, 255, 0, 128])
        width, height, rgba = dat.tim2_rgba(data)
        self.assertEqual((width, height), (2, 1))
        self.assertEqual(rgba, bytes([255,0,0,255,0,255,0,255]))
        self.assertEqual(dat.tim2_rgba(data, linear_clut=True)[2][-4:], bytes([0,0,255,255]))
        png = dat.tim2_png_bytes(data)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.tm2"
            output = Path(directory) / "sample.png"
            source.write_bytes(data)
            dat.tim2_png(source, output)
            self.assertEqual(output.read_bytes(), png)


if __name__ == "__main__": unittest.main()
