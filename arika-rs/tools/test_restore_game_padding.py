"""Synthetic regression tests for strict GAME.DAT padding restoration."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


MODULE = Path(__file__).with_name("restore_game_padding.py")
SPEC = importlib.util.spec_from_file_location("restore_game_padding", MODULE)
RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESTORE)


def encode_info(decoded: bytes) -> bytes:
    key = decoded[:16]
    encoded = bytearray(decoded)
    for i in range(16, len(decoded)):
        value = (~((decoded[i] + key[(i - 16) & 15]) & 255)) & 255
        encoded[i] = ((value & 15) << 4) | (value >> 4)
    return bytes(encoded)


class RestoreGamePaddingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.original_info = root / "source.INFO.DAT"
        self.rebuilt_info = root / "rebuilt.INFO.DAT"
        self.original_game = root / "source.GAME.DAT"
        self.rebuilt_game = root / "rebuilt.GAME.DAT"

        decoded = bytearray(48 + 2 * 48)
        decoded[:16] = b"\xc2www.arika.co.jp"
        struct.pack_into("<I", decoded, 0x2C, 2)
        decoded[48:53] = b"a.bin"
        struct.pack_into("<III", decoded, 48 + 36, 0, 1, 3)
        decoded[96:101] = b"z.bin"
        struct.pack_into("<III", decoded, 96 + 36, 1, 1, 4)
        encoded = encode_info(decoded)
        self.original_info.write_bytes(encoded)
        self.rebuilt_info.write_bytes(encoded)
        self.original_game.write_bytes(
            b"abc" + b"\xab" * (2048 - 3)
            + b"wxyz" + b"\xcd" * (2048 - 4)
            + b"\xef" * 2048
        )
        self.rebuilt_game.write_bytes(
            b"abc" + b"\x00" * (2048 - 3)
            + b"wxyz" + b"\x00" * (2048 - 4)
            + b"\x00" * 2048
        )

    def test_check_does_not_modify_output(self):
        before = self.rebuilt_game.read_bytes()
        report = RESTORE.restore_padding(
            self.original_info, self.original_game,
            self.rebuilt_info, self.rebuilt_game, check_only=True,
        )
        self.assertEqual(report["entries"], 2)
        self.assertEqual(report["padding_bytes_differing"], 6144 - 7)
        self.assertFalse(report["restored"])
        self.assertEqual(self.rebuilt_game.read_bytes(), before)

    def test_restoration_produces_byte_identical_game(self):
        report = RESTORE.restore_padding(
            self.original_info, self.original_game,
            self.rebuilt_info, self.rebuilt_game,
        )
        self.assertEqual(report["padding_bytes_differing"], 6144 - 7)
        self.assertEqual(
            self.rebuilt_game.read_bytes(), self.original_game.read_bytes()
        )
        again = RESTORE.restore_padding(
            self.original_info, self.original_game,
            self.rebuilt_info, self.rebuilt_game, check_only=True,
        )
        self.assertEqual(again["padding_bytes_differing"], 0)

    def test_rejects_modified_payload_without_touching_output(self):
        changed = bytearray(self.rebuilt_game.read_bytes())
        changed[2048] = ord("X")
        self.rebuilt_game.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "payload differs"):
            RESTORE.restore_padding(
                self.original_info, self.original_game,
                self.rebuilt_info, self.rebuilt_game,
            )
        self.assertEqual(self.rebuilt_game.read_bytes(), bytes(changed))

    def test_rejects_mismatched_info_and_game_size(self):
        bad_info = self.rebuilt_info.read_bytes() + b"\x40"
        self.rebuilt_info.write_bytes(bad_info)
        with self.assertRaisesRegex(ValueError, "INFO.DAT files differ"):
            RESTORE.restore_padding(
                self.original_info, self.original_game,
                self.rebuilt_info, self.rebuilt_game,
            )
        self.rebuilt_info.write_bytes(self.original_info.read_bytes())
        self.rebuilt_game.write_bytes(self.rebuilt_game.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "GAME.DAT lengths differ"):
            RESTORE.restore_padding(
                self.original_info, self.original_game,
                self.rebuilt_info, self.rebuilt_game,
            )


if __name__ == "__main__":
    unittest.main()
