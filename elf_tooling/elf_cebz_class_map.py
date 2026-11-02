#!/usr/bin/env python3
"""
ELF tooling: Targeted class/vtable mapper for known CEBZ classes.

Traces vtables for known CEBZ classes and maps their virtual functions.
Usage:
    python elf_cebz_class_map.py [elf]
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


CODE_START = 0x00100000
CODE_END = 0x00400700


def is_code_ptr(word):
    return CODE_START <= word < CODE_END


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
            entries.append((off, word))
        else:
            break
    return entries


def disasm_function(data, entry_vaddr, max_instr=8):
    """Disassemble first few instructions of a function."""
    f_off = vaddr_to_file(entry_vaddr)
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
        instrs.append((vaddr, off, word, mn))
        off += 4
        count += 1
        if mn in ('JR ra', 'jr $ra', 'jr ra'):
            break
    return instrs


def read_string_at(data, vaddr):
    """Read null-terminated ASCII string at vaddr."""
    f_off = vaddr_to_file(vaddr)
    if f_off < 0x80 or f_off >= len(data):
        return None
    chars = []
    while f_off < len(data) and 32 <= data[f_off] < 127:
        chars.append(chr(data[f_off]))
        f_off += 1
    return ''.join(chars) if chars else None


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("PS2 ELF CEBZ CLASS & VIRTUAL FUNCTION TABLE MAPPER")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print()

    # Known class base addresses and their vtable offsets (from prior research)
    classes = [
        ('CEBZBase',        0x004CEF40),
        ('CEBZEffectObj',   0x004CEF50),
        ('CEBZEffect',      0x004CF030),
        ('CEffectMgr',      0x004CA870),
        ('CEBZObject',      0x004C3C08),
        ('CEBZHandle',      0x004CEF30),
        ('CEBZData',        0x004CEF18),
    ]

    for class_name, class_vaddr in classes:
        class_file = vaddr_to_file(class_vaddr)
        print(f"\n{'=' * 72}")
        print(f"CLASS: {class_name}  (object at vaddr 0x{class_vaddr:08X})")
        print(f"{'=' * 72}")

        # Read class name string at object base
        name = read_string_at(data, class_vaddr)
        if name:
            print(f"  Class name string: '{name}'")

        # Dump first 64 bytes of class object
        print(f"  Object dump (first 64 bytes):")
        for off in range(class_file, min(class_file + 64, len(data)), 4):
            if off + 4 > len(data):
                break
            word = struct.unpack_from('<I', data, off)[0]
            vaddr = file_to_vaddr(off)
            is_code = is_code_ptr(word)
            marker = "  <-- CODE PTR (vtable?)" if is_code else ""
            print(f"    0x{vaddr:08X} (file 0x{off:06X}): 0x{word:08X}{marker}")

        # Look for vtable pointer at offset 0
        if class_file + 4 <= len(data):
            vtable_ptr = struct.unpack_from('<I', data, class_file)[0]
            print(f"\n  Offset 0 value: 0x{vtable_ptr:08X} (is_code_ptr={is_code_ptr(vtable_ptr)})")

            if is_code_ptr(vtable_ptr):
                print(f"  This is a direct code pointer - could be vtable or function")
            else:
                # Look for vtable pointer nearby (offsets 4, 8, 12, etc.)
                for offset in range(4, 64, 4):
                    if class_file + offset + 4 > len(data):
                        break
                    word = struct.unpack_from('<I', data, class_file + offset)[0]
                    if is_code_ptr(word):
                        print(f"  Offset {offset}: code pointer 0x{word:08X} (potential vtable)")
                        # Check if this vtable has multiple entries
                        entries = find_vtable_entries(data, word)
                        if len(entries) >= 2:
                            print(f"    -> VTABLE with {len(entries)} entries at 0x{word:08X}")
                            for j, (e_off, e_word) in enumerate(entries[:8]):
                                entry_file = vaddr_to_file(e_word)
                                instrs = disasm_function(data, e_word)
                                first_mn = instrs[0][3] if instrs else '(empty)'
                                print(f"      vfunc[{j}] 0x{e_word:08X} (file 0x{e_off:06X}): {first_mn}")
                        break

        # Also check if class object itself contains vtable at some offset
        # (some PS2 classes have vtable at offset 0, others at offset 0x30 like CEBZEffect)
        print(f"\n  Scanning for vtable within class object (offsets 0-64):")
        for offset in range(0, 64, 4):
            if class_file + offset + 4 > len(data):
                break
            word = struct.unpack_from('<I', data, class_file + offset)[0]
            if is_code_ptr(word):
                entries = find_vtable_entries(data, word)
                if len(entries) >= 3:
                    print(f"    Offset {offset}: vtable with {len(entries)} entries at 0x{word:08X}")
                    for j, (e_off, e_word) in enumerate(entries[:8]):
                        entry_file = vaddr_to_file(e_word)
                        instrs = disasm_function(data, e_word)
                        first_mn = instrs[0][3] if instrs else '(empty)'
                        print(f"      vfunc[{j}] 0x{e_word:08X} (file 0x{e_off:06X}): {first_mn}")


if __name__ == '__main__':
    main()
