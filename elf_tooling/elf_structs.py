#!/usr/bin/env python3
"""Dump PS2 ELF data structures: CEBZ class info block and trc path table."""
import struct
from pathlib import Path


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def dump_cebz_class_block(data, offset=0x3FE6A8):
    """Dump the CEBZ-related class info structure found at this offset."""
    print(f"=== CEBZ class info block at file 0x{offset:06X} ===\n")
    
    # Pointer 1: CEBZData
    ptr1 = struct.unpack_from('<I', data, offset)[0]
    val1 = struct.unpack_from('<I', data, offset + 4)[0]
    val2 = struct.unpack_from('<I', data, offset + 8)[0]
    ptr2 = struct.unpack_from('<I', data, offset + 0xC)[0]
    
    print(f"  [0x00] ptr = 0x{ptr1:08X}  (CEBZData string)")
    print(f"  [0x04] u32 = {val1}")
    print(f"  [0x08] u32 = {val2}")
    print(f"  [0x0C] ptr = 0x{ptr2:08X}  (CEBZEffectObj string)")
    
    # Floats
    f1 = struct.unpack_from('<f', data, offset + 0x10)[0]
    f2 = struct.unpack_from('<f', data, offset + 0x14)[0]
    u1 = struct.unpack_from('<I', data, offset + 0x18)[0]
    u2 = struct.unpack_from('<I', data, offset + 0x1C)[0]
    
    print(f"  [0x10] float = {f1}")
    print(f"  [0x14] float = {f2}")
    print(f"  [0x18] u32 = {u1}")
    print(f"  [0x1C] u32 = {u2}")
    
    # Four more pointers
    print(f"\n  [0x20-0x2C] class pointers:")
    for i in range(4):
        ptr = struct.unpack_from('<I', data, offset + 0x20 + i * 4)[0]
        print(f"    [0x{0x20 + i*4:02X}] ptr = 0x{ptr:08X}")
    
    # u16 values
    print(f"\n  [0x30-0x3E] u16 values:")
    for i in range(6):
        val = struct.unpack_from('<H', data, offset + 0x30 + i * 2)[0]
        print(f"    [0x{0x30 + i*2:02X}] u16 = {val} (0x{val:04X})")
    
    # More floats after that
    print(f"\n  [0x3C+] more floats:")
    for i in range(8):
        f = struct.unpack_from('<f', data, offset + 0x3C + i * 4)[0]
        print(f"    [0x{0x3C + i*4:02X}] float = {f}")


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def dump_trc_table(data, offset=0x3ACEE0, max_entries=64):
    """Dump the trc path pointer table."""
    print(f"\n=== trc path table at file 0x{offset:06X} ===\n")

    for i in range(max_entries):
        ptr = struct.unpack_from('<I', data, offset + i * 4)[0]
        file_off = vaddr_to_file(ptr)
        if 0 <= file_off < len(data):
            # Find null terminator
            end = data.index(b'\x00', file_off) if b'\x00' in data[file_off:] else len(data)
            s = data[file_off:end].decode('ascii', errors='replace')
        else:
            s = '(invalid ptr)'
        print(f"  [{i:2d}] ptr = 0x{ptr:08X}  -> {s!r}")


def find_all_pointer_tables(data, string_ptrs, code_start_file=0x80, code_end_file=0x400700):
    """Find tables of consecutive pointers that reference string addresses."""
    string_vaddrs = set(string_ptrs.values())
    tables = []
    
    i = code_start_file
    while i < code_end_file - 4:
        ptr = struct.unpack_from('<I', data, i)[0]
        if ptr in string_vaddrs:
            # Count consecutive pointers
            count = 0
            j = i
            while j < code_end_file - 4:
                p = struct.unpack_from('<I', data, j)[0]
                if p in string_vaddrs:
                    count += 1
                    j += 4
                else:
                    break
            if count >= 2:
                tables.append((i, count))
                i = j
            else:
                i += 4
        else:
            i += 4
    
    print(f"\n=== Pointer tables referencing string addresses ({len(tables)} found) ===\n")
    for off, count in tables:
        vaddr = 0x100000 + (off - 0x80)
        print(f"  file 0x{off:06X} (vaddr 0x{vaddr:08X}): {count} consecutive string pointers")


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    dump_cebz_class_block(data)
    dump_trc_table(data)

    # Build string map
    strings = {
        'CEBZData': 0x004CEF18,
        'CEBZHandle': 0x004CEF30,
        'CEBZBase': 0x004CEF40,
        'CEBZEffectObj': 0x004CEF50,
        'CEBZEffMatrix': 0x004CF020,
        'CEBZEffectEle': 0x004CF030,
        'CEBZEffectGen': 0x004CF040,
        'CEBZEffectBase': 0x004CF050,
        'trc/01/efin0001p0101': 0x004CF0A0,
    }
    find_all_pointer_tables(data, strings)
