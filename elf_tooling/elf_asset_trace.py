#!/usr/bin/env python3
"""
ELF tooling: Trace .mdl model -> .pix texture binding at runtime.

Traces how MDL models reference PIX textures through material slots,
and how the texture loading code works.
"""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


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


def disasm_range(data, start_file_off, end_file_off, max_lines=200):
    lines = []
    off = start_file_off
    count = 0
    while off < len(data) - 4 and count < max_lines:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mnemonic = info.get('mnemonic', f'unk_op_0x{word>>26:02X} 0x{word:08X}')
        lines.append(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')
        off += 4
        count += 1
    return lines


def find_jals_in_range(data, start_off, end_off):
    jals = []
    for off in range(start_off, end_off - 4, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            file_tgt = vaddr_to_file(target_vaddr)
            jals.append((vaddr, off, target_vaddr, file_tgt))
    return jals


def trace_mdl_pix_binding(data):
    """
    Trace how .mdl models bind to .pix textures at runtime.
    
    Looks at:
    1. The %s.pix format string at 0x004CC5B0
    2. Code that references this format string
    3. How texture names are constructed and loaded
    """
    print("=" * 70)
    print("MODEL (.mdl) -> TEXTURE (.pix) BINDING TRACE")
    print("=" * 70)

    pix_fmt_vaddr = 0x004CC5B0
    print(f"\n--- %s.pix format string at vaddr 0x{pix_fmt_vaddr:08X} ---")
    file_off = vaddr_to_file(pix_fmt_vaddr)
    gp_refs = find_gp_refs(data, pix_fmt_vaddr)
    raw_refs = find_raw_addr_refs(data, pix_fmt_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:10]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
    for kind, ref_vaddr, ref_off in raw_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    # Disassemble code around the pix format string reference at 0x003A4160
    print(f"\n--- Disassembly around %s.pix reference at 0x003A4160 ---")
    ref_off = vaddr_to_file(0x003A4160)
    start_off = max(ref_off - 64, 0x80)
    end_off = min(ref_off + 64, len(data) - 4)
    lines = disasm_range(data, start_off, end_off, max_lines=32)
    for line in lines:
        print(line)

    # Look for FMDL magic references
    print(f"\n--- FMDL magic (0x464D4C) references in code ---")
    idx = 0
    count = 0
    while True:
        idx = data.find(b'FMDL', idx)
        if idx == -1:
            break
        vaddr = file_to_vaddr(idx)
        print(f"    file 0x{idx:06X} (vaddr 0x{vaddr:08X})")
        idx += 1
        count += 1
        if count >= 10:
            break


def trace_mdl_model_loading(data):
    """
    Trace how .mdl models are loaded and how materials/textures are bound.
    """
    print("\n" + "=" * 70)
    print("MODEL (.mdl) LOADING TRACE")
    print("=" * 70)

    # Look for the FMDL magic in code section (referenced as immediate)
    fmdl_magic = 0x464D4C
    print(f"\n--- FMDL magic (0x{fmdl_magic:08X}) as immediate in code ---")
    target_bytes = struct.pack('<I', fmdl_magic)
    count = 0
    for i in range(0x80, 0x400700 - 4, 4):
        if data[i:i+4] == target_bytes:
            vaddr = file_to_vaddr(i)
            print(f"    file 0x{i:06X} (vaddr 0x{vaddr:08X})")
            # Disassemble surrounding code
            start_off = max(i - 16, 0x80)
            end_off = min(i + 20, len(data) - 4)
            for off2 in range(start_off, end_off, 4):
                w2 = struct.unpack_from('<I', data, off2)[0]
                v2addr = file_to_vaddr(off2)
                info = decode_instruction(w2, v2addr)
                mnemonic = info.get('mnemonic', f'unk_op_0x{w2>>26:02X}')
                print(f"      0x{v2addr:08X} 0x{off2:06X}: 0x{w2:08X}  {mnemonic}")
            print()
            count += 1
            if count >= 10:
                break


def trace_effect_update_loop(data):
    """
    Trace the main effect update/destroy loop.
    Looks for code that iterates over CEBZEffectObj instances.
    """
    print("\n" + "=" * 70)
    print("EFFECT UPDATE/DESTROY LOOP TRACE")
    print("=" * 70)

    # CEBZEffectObj class at 0x004CEF50
    cezb_effect_obj_vaddr = 0x004CEF50
    print(f"\n--- CEBZEffectObj class at vaddr 0x{cezb_effect_obj_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, cezb_effect_obj_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    # CEffectMgr singleton
    ceffect_mgr_vaddr = 0x004CA870
    print(f"\n--- CEffectMgr class at vaddr 0x{ceffect_mgr_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, ceffect_mgr_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    # Look for effect update loop patterns
    # Common pattern: loop counter, load from object array, call update
    print(f"\n--- Searching for effect update loop patterns ---")
    # Look for loops that iterate over an array of objects
    # Pattern: addiu sp,sp,negative (function prologue), then loop with counter
    for off in range(0x80, 0x400700 - 32, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x09:  # addiu
            rs = (word >> 21) & 0x1F
            rt = (word >> 16) & 0x1F
            imm = word & 0xFFFF
            if rs == 29 and rt == 29 and (imm & 0x8000):  # addiu sp,sp,-N
                # Check next instruction is sw $ra,N(sp)
                w2 = struct.unpack_from('<I', data, off + 4)[0]
                op2 = (w2 >> 26) & 0x3F
                if op2 == 0x2B:  # sw
                    rs2 = (w2 >> 21) & 0x1F
                    rt2 = (w2 >> 16) & 0x1F
                    if rs2 == 29 and rt2 == 31:  # sw $ra,N(sp)
                        vaddr = file_to_vaddr(off)
                        # Found a function prologue - check if it has JAL to CEBZ-related code
                        print(f"\n  Function prologue at vaddr 0x{vaddr:08X} (file 0x{off:06X}):")
                        lines = disasm_range(data, off, min(off + 64, len(data) - 4), max_lines=16)
                        for line in lines:
                            print(line)
                        print()


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    trace_mdl_pix_binding(data)
    trace_mdl_model_loading(data)
    trace_effect_update_loop(data)


if __name__ == '__main__':
    main()
