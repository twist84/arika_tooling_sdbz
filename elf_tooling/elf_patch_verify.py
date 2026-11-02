#!/usr/bin/env python3
"""
ELF tooling: PS2 cheat patch verifier for SLUS_214.42.

Parses pnach (PCSX2) and cht (OPL) cheat files, converts EE virtual addresses
to ELF file offsets, verifies the current bytes match the expected patch value,
and disassembles the surrounding code so each patch can be anchored in the ELF.

Usage:
    python elf_patch_verify.py [elf] [pnach_or_cht]

Defaults:
    elf      = source_data/SLUS_214.42
    cheat    = (none; pass a .pnach or .cht path)
"""
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disasm_around(data, file_off, before=8, after=8):
    """Return disassembly lines around file_off."""
    start = max(0x80, file_off - before * 4)
    end = min(len(data) - 4, file_off + after * 4)
    lines = []
    for off in range(start, end, 4):
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mark = ' <<< PATCH' if off == file_off else ''
        lines.append(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {info.get("mnemonic", "?")}{mark}')
    return lines


def parse_pnach(path):
    """Parse a PCSX2 .pnach file. Returns list of patch dicts."""
    patches = []
    text = Path(path).read_text(errors='replace')
    patch_re = re.compile(
        r'patch\s*=\s*(\d+),\s*([A-Za-z]+),\s*([0-9A-Fa-f]+),\s*(\w+),\s*([0-9A-Fa-f]+)',
        re.IGNORECASE,
    )
    for line in text.splitlines():
        m = patch_re.search(line)
        if not m:
            continue
        ptype, mem, addr, size, value = m.groups()
        patches.append({
            'source': 'pnach',
            'type': ptype,
            'mem': mem.upper(),
            'vaddr': int(addr, 16),
            'size': size.lower(),
            'value': int(value, 16),
            'line': line.strip(),
        })
    return patches


def parse_cht(path, data):
    """Parse an OPL .cht cheat file. Returns list of patch dicts."""
    patches = []
    text = Path(path).read_text(errors='replace')
    # CHT lines are hex pairs like "202b12d4 3c023f10" (address value)
    line_re = re.compile(r'^\s*([0-9A-Fa-f]{6,8})\s+([0-9A-Fa-f]{8})\s*$')
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('"'):
            continue
        m = line_re.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        value = int(m.group(2), 16)
        # CHT addresses may carry a type/flag byte in the top position
        # (e.g. "202b12d4" where 0x20 is type and 0x002b12d4 is the EE vaddr).
        # Try the raw value first, then fall back to stripping the top byte.
        candidates = [addr, addr & 0x00FFFFFF]
        chosen = None
        for cand in candidates:
            fo = vaddr_to_file(cand)
            if 0x80 <= fo < len(data) - 4:
                chosen = cand
                break
        if chosen is None:
            chosen = addr  # report the raw value even if out of range
        patches.append({
            'source': 'cht',
            'type': '1',
            'mem': 'EE',
            'vaddr': chosen,
            'size': 'word',
            'value': value,
            'line': line,
        })
    return patches


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    cheat_path = sys.argv[2] if len(sys.argv) > 2 else None

    data = Path(elf_path).read_bytes()

    if cheat_path is None:
        print("Usage: python elf_patch_verify.py [elf] [pnach|cht]")
        print(f"  Default ELF: {elf_path}")
        print("  Provide a .pnach or .cht cheat file to verify against.")
        return

    cheat_path = Path(cheat_path)
    if cheat_path.suffix.lower() == '.pnach':
        patches = parse_pnach(cheat_path)
    elif cheat_path.suffix.lower() == '.cht':
        patches = parse_cht(cheat_path, data)
    else:
        print(f"Unknown cheat format: {cheat_path.suffix}")
        return

    print("=" * 72)
    print(f"CHEAT PATCH VERIFICATION: {cheat_path.name}")
    print(f"ELF: {elf_path}")
    print("=" * 72)

    total = len(patches)
    matched = 0
    for i, p in enumerate(patches, 1):
        vaddr = p['vaddr']
        value = p['value']
        file_off = vaddr_to_file(vaddr)

        print(f"\n[{i}/{total}] {p['source']}: {p['line']}")
        print(f"  EE vaddr = 0x{vaddr:08X}  ->  file offset = 0x{file_off:06X}")
        print(f"  patch value = 0x{value:08X} ({p['size']})")

        if file_off < 0x80 or file_off + 4 > len(data):
            print(f"  OUTSIDE ELF file range (file size 0x{len(data):06X})")
            continue

        cur = struct.unpack_from('<I', data, file_off)[0]
        match = (cur == value)
        matched += 1 if match else 0
        print(f"  current bytes = 0x{cur:08X}  ->  {'MATCH' if match else 'MISMATCH'}")

        if not match:
            # Try to interpret current instruction
            op = (cur >> 26) & 0x3F
            rt = (cur >> 16) & 0x1F
            imm = cur & 0xFFFF
            if op == 0x0F:
                print(f"  current is LUI v{rt},0x{imm:04X}; patch would make it LUI v{rt},0x{value & 0xFFFF:04X}")

        # Disassemble around the patch
        print(f"  Disassembly context:")
        for line in disasm_around(data, file_off):
            print(line)

    print(f"\n{'=' * 72}")
    print(f"Summary: {matched}/{total} patches match current ELF bytes")


if __name__ == '__main__':
    main()
