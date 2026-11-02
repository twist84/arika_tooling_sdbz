#!/usr/bin/env python3
"""Examine raw data at effect name table location 0x3DB1E9+."""
import struct
from pathlib import Path


def dump_region(data, start, length=256):
    """Hex dump with vaddr annotations."""
    print(f"=== Region at file 0x{start:06X} (vaddr 0x{0x100000 + (start - 0x80):08X}) ===\n")
    for off in range(start, min(start + length, len(data)), 16):
        chunk = data[off:off+16]
        hexs = ' '.join(f'{b:02X}' for b in chunk)
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        vaddr = 0x100000 + (off - 0x80)
        print(f"  0x{off:06X} (v 0x{vaddr:08X}): {hexs:<48} {asc}")


def main():
    path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()
    
    # The effect name regions found earlier were at 0x3DB1E9 onwards
    # Let's dump a larger area to see the structure
    dump_region(data, 0x3DB1E0, 512)
    
    # Also look at the sequential entries found at 0x3DB1E9+
    print("\n\n=== Trying to interpret as 4-byte entries ===\n")
    off = 0x3DB1E9
    for i in range(50):
        if off + 4 > len(data):
            break
        val = struct.unpack_from('<I', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        
        # Check if this looks like a pointer to a string
        file_off = val - 0x100000 + 0x80
        if 0x80 <= file_off < len(data) - 4:
            # Try to read a string at that location
            s_end = data.find(b'\x00', file_off) if b'\x00' in data[file_off:] else len(data)
            s = data[file_off:s_end].decode('ascii', errors='replace') if s_end > file_off else ''
            if len(s) >= 2:
                print(f"  file 0x{off:06X} (v 0x{vaddr:08X}): ptr=0x{val:08X} -> {s!r}")
            else:
                print(f"  file 0x{off:06X} (v 0x{vaddr:08X}): u32=0x{val:08X} ({val})")
        else:
            print(f"  file 0x{off:06X} (v 0x{vaddr:08X}): u32=0x{val:08X} ({val})")
        off += 4
