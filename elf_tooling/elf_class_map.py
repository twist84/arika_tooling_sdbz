#!/usr/bin/env python3
"""
ELF tooling: Class & Virtual Function Table mapper for PS2 ELF.

Finds class name strings, then locates their vtables (object's first field
points to vtable) and maps each virtual function.

Usage:
    python elf_class_map.py [elf]

Defaults:
    elf   = source_data/SLUS_214.42
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr


CODE_START = 0x00100000
CODE_END = 0x00400700


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def is_code_ptr(word):
    return CODE_START <= word < CODE_END


def find_all_strings(data, min_len=3, start=0x80, end=None):
    """Return list of (file_off, string) for ASCII strings."""
    if end is None:
        end = len(data)
    results = []
    i = start
    while i < end:
        b = data[i]
        if 32 <= b < 127:
            start_off = i
            chars = []
            while i < end and 32 <= data[i] < 127:
                chars.append(chr(data[i]))
                i += 1
            s = ''.join(chars)
            if len(s) >= min_len:
                results.append((start_off, s))
        else:
            i += 1
    return results


def is_class_name(s):
    """Heuristic: string looks like a C++ class name."""
    if len(s) < 3 or len(s) > 40:
        return False
    if not s[0].isalpha():
        return False
    # Must contain only alphanumeric and underscore
    if not all(c.isalnum() or c == '_' for c in s):
        return False
    # Must have at least one letter
    if not any(c.isalpha() for c in s):
        return False
    # Exclude common non-class strings
    exclude = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'what',
               'ELF', 'SCE', 'GCC', 'SN/', 'SKG', 'ADX', 'PsII', 'Append'}
    if s in exclude:
        return False
    return True


def find_vtable_entries(data, vtable_vaddr, max_entries=32):
    """Read consecutive code pointers starting at vtable_vaddr."""
    f_off = vaddr_to_file(vtable_vaddr)
    entries = []
    for j in range(max_entries):
        off = f_off + j * 4
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        if is_code_ptr(word):
            entries.append(word)
        else:
            break
    return entries


def disasm_function(data, entry_vaddr, max_instr=6):
    """Disassemble first few instructions of a function."""
    f_off = entry_vaddr - 0x100000 + 0x80
    if f_off < 0x80 or f_off + 4 > len(data):
        return []
    instrs = []
    off = f_off
    count = 0
    while off < len(data) - 4 and count < max_instr:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mn = info.get('mnemonic', '')
        instrs.append(mn)
        off += 4
        count += 1
        if mn in ('JR ra', 'jr $ra', 'jr ra'):
            break
    return instrs


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("PS2 ELF CLASS & VIRTUAL FUNCTION TABLE MAPPER")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print()

    # Find all strings
    strings = find_all_strings(data)
    class_names = [(off, s) for off, s in strings if is_class_name(s)]
    print(f"Total strings: {len(strings)}, Class-like names: {len(class_names)}")
    print()

    # Find class names and their vtables
    classes_found = []
    for str_off, name in class_names:
        str_vaddr = file_to_vaddr(str_off)

        # Look near this string for a vtable pointer (code pointer in nearby data)
        # Class objects typically have vtable pointer at offset 0, name somewhere in object
        # Scan +/- 0x200 bytes around the string for code pointers
        scan_start = max(str_off - 0x200, 0x80)
        scan_end = min(str_off + 0x200, len(data) - 4)

        vtable_ptrs = []
        for scan_off in range(scan_start, scan_end, 4):
            if scan_off + 4 > len(data):
                break
            word = struct.unpack_from('<I', data, scan_off)[0]
            if is_code_ptr(word):
                vtable_ptrs.append((scan_off, word))

        if not vtable_ptrs:
            continue

        # For each candidate vtable pointer, verify it points to an array of code pointers
        for ptr_off, vtable_ptr in vtable_ptrs:
            entries = find_vtable_entries(data, vtable_ptr)
            if len(entries) >= 3:
                classes_found.append({
                    'name': name,
                    'name_file_off': str_off,
                    'name_vaddr': str_vaddr,
                    'vtable_ptr_file_off': ptr_off,
                    'vtable_ptr_value': vtable_ptr,
                    'vtable_vaddr': vtable_ptr,
                    'num_entries': len(entries),
                    'entries': entries,
                })
                break  # Found a vtable for this class name

    # Deduplicate by vtable address
    seen_vtables = set()
    unique_classes = []
    for c in classes_found:
        if c['vtable_vaddr'] not in seen_vtables:
            seen_vtables.add(c['vtable_vaddr'])
            unique_classes.append(c)

    print(f"Classes with vtables found: {len(unique_classes)}")
    print()

    for i, cls in enumerate(unique_classes):
        print(f"--- Class #{i + 1}: {cls['name']} ---")
        print(f"  Name at: file 0x{cls['name_file_off']:06X} (vaddr 0x{cls['name_vaddr']:08X})")
        print(f"  VTable pointer at: file 0x{cls['vtable_ptr_file_off']:06X}")
        print(f"  VTable address: 0x{cls['vtable_vaddr']:08X}")
        print(f"  Virtual functions: {cls['num_entries']}")
        print()

        for j, entry in enumerate(cls['entries']):
            entry_file = entry - 0x100000 + 0x80
            instrs = disasm_function(data, entry, max_instr=5)
            first_mn = instrs[0] if instrs else '(empty)'
            rest = ' | '.join(instrs[1:3]) if len(instrs) > 1 else ''
            print(f"    vfunc[{j:2d}] 0x{entry:08X} (file 0x{entry_file:06X}): {first_mn}")
            if rest:
                print(f"                 {rest}")
        print()


if __name__ == '__main__':
    main()
