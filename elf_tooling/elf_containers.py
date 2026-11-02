#!/usr/bin/env python3
"""ELF tooling for GAME.DAT/INFO.DAT container formats - trace archive loading code."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


def disasm_range(data, start_file_off, end_file_off):
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        mnemonic = decode_instruction(word, vaddr)
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')


def find_gp_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    target_lower = target_vaddr & 0xFFFF
    results = []
    for i in range(code_start, code_end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = file_to_vaddr(i)
        if op in (0x09, 0x0D, 0x23, 0x2B) and rs == 28 and imm == target_lower:
            kind = {0x09: 'addiu', 0x0D: 'ori', 0x23: 'lw', 0x2B: 'sw'}[op]
            results.append((kind, vaddr, i))
    return results


def find_string_in_data(data, search):
    results = []
    idx = 0
    while True:
        idx = data.find(search, idx)
        if idx == -1:
            break
        results.append(idx)
        idx += 1
    return results


def trace_containers(data):
    """Trace GAME.DAT/INFO.DAT container format usage in ELF."""
    print("=" * 70)
    print("Container Formats (GAME.DAT/INFO.DAT) - ELF Analysis")
    print("=" * 70)

    # INFO.DAT magic
    info_magic = b'\x7fwww.arika.co.jp'
    print(f"\n--- INFO.DAT magic ({info_magic!r}) ---")
    positions = find_string_in_data(data, info_magic)
    print(f"  {len(positions)} occurrence(s) in ELF data")
    for pos in positions[:10]:
        vaddr = file_to_vaddr(pos)
        start = max(0x80, pos - 16)
        end = min(len(data), pos + len(info_magic) + 16)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")

    # FPIX container magic (GAME.DAT)
    print(f"\n--- FPIX container magic (b'FPIX') ---")
    positions = find_string_in_data(data, b'FPIX')
    print(f"  {len(positions)} occurrence(s) in ELF data")
    for pos in positions[:10]:
        vaddr = file_to_vaddr(pos)
        start = max(0x80, pos - 16)
        end = min(len(data), pos + 16)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")

    # File path strings referencing GAME.DAT/INFO.DAT
    print(f"\n--- Container file path strings ---")
    for s in [b'GAME.DAT', b'INFO.DAT', b'game.dat', b'info.dat']:
        positions = find_string_in_data(data, s)
        if positions:
            print(f"  {s.decode()}: {len(positions)} occurrence(s)")
            for pos in positions[:5]:
                vaddr = file_to_vaddr(pos)
                print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X})")

    # Look for archive-related function names
    print(f"\n--- Archive-related function names ---")
    for s in [b'Open', b'Load', b'Read', b'Archive', b'Container', b'pak', b'Pak']:
        positions = find_string_in_data(data, s)
        if positions:
            print(f"  {s.decode()}: {len(positions)} occurrence(s)")
            for pos in positions[:5]:
                vaddr = file_to_vaddr(pos)
                start = max(0x80, pos - 8)
                end = min(len(data), pos + len(s) + 8)
                ctx = data[start:end]
                printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
                print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")

    # Check the resource table at 0x00610000 for container entries
    print(f"\n--- Resource table at 0x00610000+ ---")
    table_start_file = vaddr_to_file(0x00610000)
    for i in range(0, 0x400, 4):
        off = table_start_file + i
        if off + 4 > len(data):
            break
        ptr = struct.unpack_from('<I', data, off)[0]
        str_file = vaddr_to_file(ptr)
        if 0x80 <= str_file < len(data) - 1:
            end = data.find(b'\x00', str_file)
            if end == -1:
                end = len(data)
            s = data[str_file:end].decode('ascii', errors='replace')
            if len(s) >= 2 and '.' in s:
                print(f"  table[+0x{i:04X}] vaddr 0x{0x00610000+i:08X}: ptr=0x{ptr:08X} -> '{s}'")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    trace_containers(data)
