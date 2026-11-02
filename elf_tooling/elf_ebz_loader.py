#!/usr/bin/env python3
"""Find where .ebz files are loaded in the ELF: trace the %s.ebz format string."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from elf_string_refs import find_refs_to_addr


def trace_ebz_loading(data):
    """Find all references to %s.ebz and surrounding context."""
    ebz_fmt_vaddr = 0x004CEF28  # "%s.ebz" string
    
    print(f"=== %s.ebz format string references (vaddr 0x{ebz_fmt_vaddr:08X}) ===\n")
    refs = find_refs_to_addr(data, ebz_fmt_vaddr)
    print(f"Found {len(refs)} ref(s)\n")
    for kind, vaddr, off, _ in refs:
        print(f"  {kind} at vaddr 0x{vaddr:08X} (file 0x{off:06X})")
    
    # Also search for the .ebz string literal itself
    print(f"\n=== '.ebz' string literal locations ===\n")
    for i in range(0x80, len(data) - 4, 1):
        if data[i:i+4] == b'.ebz':
            vaddr = 0x100000 + (i - 0x80)
            # Show context
            start = max(0x80, i - 16)
            end = min(len(data), i + 16)
            ctx = data[start:end]
            printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
            print(f"  file 0x{i:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")
    
    # Search for calls to file-open functions (common PS2 SDK: sceIoOpen)
    print(f"\n=== File I/O related strings ===\n")
    for off in range(0x80, len(data) - 1):
        if data[off] == ord('o') and data[off+1:off+5] == b'pen\0':
            vaddr = 0x100000 + (off - 0x80)
            print(f"  'open\0' at file 0x{off:06X} (vaddr 0x{vaddr:08X})")
        if data[off:off+7] == b'Read\0\0\0':
            vaddr = 0x100000 + (off - 0x80)
            print(f"  'Read' at file 0x{off:06X} (vaddr 0x{vaddr:08X})")


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()
    trace_ebz_loading(data)
