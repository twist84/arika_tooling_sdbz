#!/usr/bin/env python3
"""Find where the eff/e%c%c/%s format string is used - traces .ebz file loading."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from elf_string_refs import find_refs_to_addr


def trace_eff_format(data):
    """Trace references to the eff/e%c%c/%s format string."""
    fmt_vaddr = 0x004C3A88  # "eff/e%c%c/%s"

    print(f"=== 'eff/e%c%c/%s' format string references (vaddr 0x{fmt_vaddr:08X}) ===\n")
    refs = find_refs_to_addr(data, fmt_vaddr)
    print(f"Found {len(refs)} ref(s)")
    for kind, vaddr, off, _ in refs:
        print(f"  {kind} at vaddr 0x{vaddr:08X} (file 0x{off:06X})")

    # Search for raw fmt vaddr in code
    fmt_bytes = struct.pack('<I', fmt_vaddr)
    print(f"\n=== Raw fmt vaddr in code section ===\n")
    count = 0
    for i in range(0x80, 0x400700 - 4, 4):
        if data[i:i+4] == fmt_bytes:
            vaddr = 0x100000 + (i - 0x80)
            print(f"  vaddr 0x{vaddr:08X} (file 0x{i:06X})")
            count += 1
    print(f"Total: {count} raw hits")

    # Search for all occurrences of "eff/e" in code (as part of sprintf patterns)
    print(f"\n=== 'eff/e' string contexts in code ===\n")
    count = 0
    for i in range(0x80, 0x400700 - 4, 4):
        # Check if this 4-byte word contains "eff/"
        word = data[i:i+4]
        if b'eff/' in word:
            vaddr = 0x100000 + (i - 0x80)
            hexs = ' '.join(f'{b:02X}' for b in word)
            print(f"  vaddr 0x{vaddr:08X} (file 0x{i:06X}): 0x{struct.unpack_from('<I', data, i)[0]:08X} {hexs}")
            count += 1
    print(f"Total: {count} words containing 'eff/'")


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()
    trace_eff_format(data)
