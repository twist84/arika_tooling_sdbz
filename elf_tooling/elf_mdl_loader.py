#!/usr/bin/env python3
"""ELF tooling for .mdl/.FMDL model format - trace model loading code."""
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


def find_raw_addr_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    target_bytes = struct.pack('<I', target_vaddr)
    results = []
    for i in range(code_start, code_end - 4, 4):
        if data[i:i+4] == target_bytes:
            vaddr = file_to_vaddr(i)
            results.append(('raw-addr', vaddr, i))
    return results


def find_string_in_data(data, search):
    """Find all occurrences of a string in the ELF data section."""
    results = []
    idx = 0
    while True:
        idx = data.find(search, idx)
        if idx == -1:
            break
        results.append(idx)
        idx += 1
    return results


def trace_mdl(data):
    """Trace MDL model format usage in ELF."""
    print("=" * 70)
    print("FMDL Model Format (.mdl) - ELF Analysis")
    print("=" * 70)

    # The %s.mdl format string
    mdl_str_vaddr = 0x004CC5A8
    mdl_str_file = vaddr_to_file(mdl_str_vaddr)

    print(f"\n--- Format string '%s.mdl' at vaddr 0x{mdl_str_vaddr:08X} (file 0x{mdl_str_file:06X}) ---")
    gp_refs = find_gp_refs(data, mdl_str_vaddr)
    raw_refs = find_raw_addr_refs(data, mdl_str_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    print(f"  Raw address refs: {len(raw_refs)}")

    # Look for FMDL magic in data section
    fmdl_positions = find_string_in_data(data, b'FMDL')
    print(f"\n--- FMDL magic in ELF data ({len(fmdl_positions)} occurrence(s)) ---")
    for pos in fmdl_positions[:10]:
        vaddr = file_to_vaddr(pos)
        start = max(0x80, pos - 16)
        end = min(len(data), pos + 16)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"  file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")

    # Look for .mdl extension strings
    mdl_ext_positions = find_string_in_data(data, b'.mdl')
    print(f"\n--- .mdl extension in ELF data ({len(mdl_ext_positions)} occurrence(s)) ---")
    for pos in mdl_ext_positions[:20]:
        vaddr = file_to_vaddr(pos)
        start = max(0x80, pos - 16)
        end = min(len(data), pos + 16)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"  file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")

    # Check the resource table at 0x00610000+ for MDL entries
    print(f"\n--- Resource table entries pointing to MDL-related strings ---")
    table_start_file = vaddr_to_file(0x00610000)
    for i in range(0, 0x400, 4):
        off = table_start_file + i
        if off + 4 > len(data):
            break
        ptr = struct.unpack_from('<I', data, off)[0]
        str_file = vaddr_to_file(ptr)
        if 0x80 <= str_file < len(data) - 4:
            # Check if this points near the %s.mdl string
            if abs(str_file - mdl_str_file) < 0x100:
                end = data.find(b'\x00', str_file)
                if end == -1:
                    end = len(data)
                s = data[str_file:end].decode('ascii', errors='replace')
                print(f"  table[+0x{i:04X}] vaddr 0x{0x00610000+i:08X}: ptr=0x{ptr:08X} -> '{s}'")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    trace_mdl(data)
