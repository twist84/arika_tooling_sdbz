#!/usr/bin/env python3
"""
ELF tooling: Function trace via JAL-target entry detection.

This PS2 ELF does not use standard `sw $ra,imm($sp)` prologues (only one such
store exists in the entire code section, and it is not stack-related), so
prologue-based function detection fails. Instead, function entries are inferred
from JAL instruction targets: every address that is the target of a JAL is
treated as a function entry point.

For a given address, finds the enclosing JAL-target function (the nearest JAL
target at-or-below the address, bounded by the next JAL target or jr $ra
afterwards), disassembles it, lists every JAL call it makes, and finds every
other function that calls it.

Usage:
    python elf_func_trace.py [elf] [vaddr1] [vaddr2] ...

Defaults:
    elf   = source_data/SLUS_214.42
    vaddr = 0x002B12D4 (widescreen patch) and 0x003301E0 (CEBZ loading)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


CODE_START = 0x80
CODE_END = 0x400700


def jal_instructions(data, start=CODE_START, end=CODE_END):
    """Yield (from_file_off, from_vaddr, target_vaddr, target_file_off) for each JAL."""
    for i in range(start, end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:
            from_vaddr = file_to_vaddr(i)
            target_idx = word & 0x3FFFFFF
            target_vaddr = (from_vaddr & 0xF0000000) | (target_idx << 2)
            target_file = vaddr_to_file(target_vaddr)
            yield i, from_vaddr, target_vaddr, target_file


def jr_ra_instructions(data, start=CODE_START, end=CODE_END):
    """Yield file offsets of jr $ra instructions."""
    for i in range(start, end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x00:
            funct = word & 0x3F
            rs = (word >> 21) & 0x1F
            rd = (word >> 11) & 0x1F
            if funct == 0x08 and rs == 31 and rd == 0:
                yield i


def find_function_entries(data):
    """Return sorted set of file offsets that are JAL targets (function entries)."""
    entries = set()
    for _, _, target_vaddr, target_file in jal_instructions(data):
        if CODE_START <= target_file < CODE_END:
            entries.add(target_file)
    return sorted(entries)


def enclosing_function(entries, file_off):
    """Find the function entry at-or-before file_off. Returns entry offset or None."""
    prev = None
    for e in entries:
        if e <= file_off:
            prev = e
        else:
            break
    return prev


def function_end(entries, jr_ra_set, start_file_off, code_end=CODE_END):
    """End of function = earliest of next JAL target, next jr $ra, or code end."""
    best = code_end
    for e in entries:
        if e > start_file_off:
            best = min(best, e)
            break
    for j in jr_ra_set:
        if j > start_file_off:
            best = min(best, j)
            break
    return best


def build_callers_map(data, entries):
    """Map function entry file offset -> list of (caller_file_off, caller_vaddr)."""
    entry_set = set(entries)
    callers = {e: [] for e in entries}
    for from_file, from_vaddr, target_vaddr, target_file in jal_instructions(data):
        if target_file in entry_set:
            callers[target_file].append((from_file, from_vaddr))
    return callers


def disasm_range(data, start_file_off, end_file_off):
    """Disassemble [start_file_off, end_file_off), return list of tuples."""
    lines = []
    off = start_file_off
    while off < end_file_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        lines.append((off, vaddr, word, info.get('mnemonic', f'unk 0x{word:08X}'), info))
        off += 4
    return lines


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    vaddrs = [int(x, 0) for x in sys.argv[2:]] if len(sys.argv) > 2 else [0x002B12D4, 0x003301E0]

    data = Path(elf_path).read_bytes()

    entries = find_function_entries(data)
    jr_ra_set = set(jr_ra_instructions(data))
    callers_map = build_callers_map(data, entries)

    print("=" * 72)
    print("ELF FUNCTION TRACE (JAL-target based)")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Function entries (JAL targets): {len(entries)}")
    print(f"jr $ra sites: {len(jr_ra_set)}")
    print()

    for vaddr in vaddrs:
        file_off = vaddr_to_file(vaddr)
        if file_off < CODE_START or file_off >= CODE_END:
            print(f"\n{'=' * 72}")
            print(f"vaddr 0x{vaddr:08X} (file 0x{file_off:06X}) is OUTSIDE code range")
            print(f"{'=' * 72}")
            continue

        entry = enclosing_function(entries, file_off)
        if entry is None:
            print(f"\n{'=' * 72}")
            print(f"No enclosing JAL-target function for vaddr 0x{vaddr:08X} (file 0x{file_off:06X})")
            print(f"{'=' * 72}")
            continue

        end = function_end(entries, jr_ra_set, entry)
        entry_vaddr = file_to_vaddr(entry)

        print(f"\n{'=' * 72}")
        print(f"FUNCTION at vaddr 0x{entry_vaddr:08X} (file 0x{entry:06X})")
        print(f"  contains target vaddr 0x{vaddr:08X} (file 0x{file_off:06X})")
        print(f"  bounds: file 0x{entry:06X} - 0x{end:06X} (0x{end - entry:06X} bytes)")
        print(f"{'=' * 72}")

        # JAL calls made by this function
        jal_targets = []
        func_end = min(end, CODE_END)
        for off in range(entry, func_end - 4, 4):
            word = struct.unpack_from('<I', data, off)[0]
            op = (word >> 26) & 0x3F
            if op == 0x03:
                from_v = file_to_vaddr(off)
                target_idx = word & 0x3FFFFFF
                target_v = (from_v & 0xF0000000) | (target_idx << 2)
                target_file = vaddr_to_file(target_v)
                jal_targets.append((off, from_v, target_v, target_file))

        print(f"\n  JAL calls made ({len(jal_targets)}):")
        entry_set = set(entries)
        for off, from_v, target_v, target_file in jal_targets:
            tag = ' [FUNC]' if target_file in entry_set else ''
            print(f"    0x{from_v:08X} (file 0x{off:06X}) -> 0x{target_v:08X} (file 0x{target_file:06X}){tag}")

        # Callers
        callers = callers_map.get(entry, [])
        print(f"\n  Callers ({len(callers)}):")
        if callers:
            for cf_file, cf_v in callers:
                print(f"    0x{cf_v:08X} (file 0x{cf_file:06X})")
        else:
            print(f"    (none - entered via JALR/indirect or exception)")

        # Full disassembly
        print(f"\n  Disassembly:")
        instrs = disasm_range(data, entry, end)
        for off, v, word, mnem, info in instrs:
            mark = '  <-- TARGET' if off == file_off else ''
            print(f'    0x{v:08X} 0x{off:06X}: 0x{word:08X}  {mnem}{mark}')
        print()


if __name__ == '__main__':
    main()
