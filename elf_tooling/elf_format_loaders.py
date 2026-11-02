#!/usr/bin/env python3
"""ELF tooling for all file formats - comprehensive code reference tracer."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


def disasm_range(data, start_file_off, end_file_off, annotate=None):
    """Disassemble a range of file offsets with optional annotations."""
    annotate = annotate or {}
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        mnemonic = decode_instruction(word, vaddr)
        note = annotate.get(off, '')
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}{note}')


def find_gp_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    """Find $gp-relative references to target_vaddr."""
    target_lower = target_vaddr & 0xFFFF
    results = []
    for i in range(code_start, code_end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = file_to_vaddr(i)
        if op == 0x0D and rs == 28 and imm == target_lower:  # ori $rt, $gp, imm
            results.append(('ori-from-gp', vaddr, i))
        elif op in (0x23, 0x2B) and rs == 28 and imm == target_lower:  # lw/sw
            results.append(('gp-mem', vaddr, i))
        elif op == 0x09 and rs == 28 and imm == target_lower:  # addiu
            results.append(('addiu-from-gp', vaddr, i))
    return results


def find_raw_addr_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    """Find raw 32-bit address values in code section."""
    target_bytes = struct.pack('<I', target_vaddr)
    results = []
    for i in range(code_start, code_end - 4, 4):
        if data[i:i+4] == target_bytes:
            vaddr = file_to_vaddr(i)
            results.append(('raw-addr', vaddr, i))
    return results


def trace_format_loader(data, format_name, vaddr, max_instr=128):
    """Trace the code that loads a specific format."""
    print(f"\n{'='*70}")
    print(f"{format_name} at vaddr 0x{vaddr:08X}")
    print(f"{'='*70}\n")

    # Find all references
    gp_refs = find_gp_refs(data, vaddr)
    raw_refs = find_raw_addr_refs(data, vaddr)
    all_refs = gp_refs + raw_refs

    print(f"Found {len(all_refs)} code reference(s):\n")
    for kind, ref_vaddr, ref_off in all_refs:
        print(f"  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    # Disassemble around each reference
    for kind, ref_vaddr, ref_off in all_refs:
        print(f"\n  --- Code around {kind} at vaddr 0x{ref_vaddr:08X} ---")
        start = max(0x80, ref_off - 96)
        end = min(len(data) - 4, ref_off + 32)
        disasm_range(data, start, end)
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    # All format string vaddrs from the scan
    formats = {
        'PIX texture (%s.pix)': 0x004CC5B0,
        'PIX texture (%s.pix #2)': 0x004CC5D8,
        'MDL model (%s.mdl)': 0x004CC5A8,
        'PMT material (%s.pmt)': 0x004CC728,
        'CHT facial (%s.cht)': 0x004CA6B8,
        'ANI animation (%s.ani)': 0x004CFAF0,
        'PAS pose (%s.pas)': 0x004CFAC8,
        'EBZ effect (%s.ebz)': 0x004CEF28,
        'FON font (font/5-24-2.fon)': 0x004CD460,
    }

    for name, vaddr in formats.items():
        trace_format_loader(data, name, vaddr)
