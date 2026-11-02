#!/usr/bin/env python3
"""Trace the CEBZ class info block usage - who references 0x3FE6A8 and its contents."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from elf_string_refs import find_refs_to_addr


def trace_cebz_block(data, block_offset=0x3FE6A8):
    """Trace references to the CEBZ class info block."""
    block_vaddr = 0x100000 + (block_offset - 0x80)

    print(f"=== CEBZ class info block at file 0x{block_offset:06X} (vaddr 0x{block_vaddr:08X}) ===\n")

    # Dump the block contents
    print("Block contents:")
    for off in range(block_offset, block_offset + 0x60, 4):
        val = struct.unpack_from('<I', data, off)[0]
        fval = struct.unpack_from('<f', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        print(f"  0x{off:06X} (v 0x{vaddr:08X}): u32=0x{val:08X} ({val}) f32={fval:.6f}")

    # Find references to the block vaddr
    print(f"\n=== References to block vaddr 0x{block_vaddr:08X} ===\n")
    refs = find_refs_to_addr(data, block_vaddr)
    print(f"Found {len(refs)} ref(s)")
    for kind, ref_vaddr, off, _ in refs:
        print(f"  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{off:06X})")

    # Also search for raw block vaddr value in code section
    print(f"\n=== Raw block vaddr value in code section ===\n")
    block_bytes = struct.pack('<I', block_vaddr)
    count = 0
    for i in range(0x80, 0x400700 - 4, 4):
        if data[i:i+4] == block_bytes:
            vaddr = 0x100000 + (i - 0x80)
            print(f"  vaddr 0x{vaddr:08X} (file 0x{i:06X})")
            count += 1
    print(f"Total: {count} raw hits")


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()
    trace_cebz_block(data)
