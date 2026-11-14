"""Tests for the region-independent native arrow table signature."""
import struct
import unittest

from elf_menu_arrows import (
    TABLE_BYTES, NATIVE_UV_RECTS, NATIVE_TIMES, NATIVE_VALUES,
    find_arrow_tables,
)


class NativeArrowTableTests(unittest.TestCase):
    def test_exact_tables_and_addresses(self):
        result = find_arrow_tables([(0x400000, bytes(32) + TABLE_BYTES)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['uv_table_va'], '0x00400020')
        self.assertEqual(result[0]['curve_times_va'], '0x00400040')
        self.assertEqual(result[0]['curve_values_va'], '0x00400050')
        self.assertEqual(result[0]['key_times'], list(NATIVE_TIMES))
        self.assertEqual(result[0]['key_values'], list(NATIVE_VALUES))
        self.assertEqual(result[0]['uv_rectangles'][0], list(NATIVE_UV_RECTS[0]))

    def test_does_not_accept_near_miss(self):
        altered = bytearray(TABLE_BYTES)
        # Replace 40.0 period with a false 32.0 near-miss.
        struct.pack_into('<f', altered, 32 + 3*4, 32.0)
        self.assertEqual(find_arrow_tables([(0x100000, altered)]), [])
        self.assertEqual(find_arrow_tables([]), [])


if __name__ == '__main__':
    unittest.main()
