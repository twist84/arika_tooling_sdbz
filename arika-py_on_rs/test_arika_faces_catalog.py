import tempfile
import unittest
from pathlib import Path

import arika_faces


class FaceCatalogTests(unittest.TestCase):
    def test_catalog_exposes_verified_native_slots_and_unknown_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'p01' / 'p01.ani'
            path.parent.mkdir()
            # Four groups, one terminated program per group.
            data = bytearray(16 + 4 * 8 + 4 * 4 + 4 * 8)
            data[:4] = (4).to_bytes(4, 'little')
            cursor = 16 + 4 * 8
            for i in range(4):
                table = 16 + i * 8
                data[table:table+8] = (1).to_bytes(4, 'little') + cursor.to_bytes(4, 'little')
                data[cursor:cursor+4] = (cursor + 8).to_bytes(4, 'little')
                cursor += 4
            # The distinct program offsets are stored in the group tables.
            program_base = 16 + 4 * 8 + 4 * 4
            for i in range(4):
                table_data = 16 + 4 * 8 + i * 4
                program_offset = program_base + i * 8
                data[table_data:table_data+4] = program_offset.to_bytes(4, 'little')
                import struct
                struct.pack_into('<fBBH', data, program_offset, 0.0, 0, 0, 0x1000)
            path.write_bytes(data)
            catalog = arika_faces.face_catalog(directory)
            groups = catalog['characters'][0]['groups']
            self.assertEqual([g['native_player_slot'] for g in groups], [0, 1, 2, None])
            self.assertEqual([g['program_count'] for g in groups], [1, 1, 1, 1])


if __name__ == '__main__':
    unittest.main()
