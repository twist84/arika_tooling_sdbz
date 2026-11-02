#!/usr/bin/env python3
"""
ELF tooling: Trace STG efXX → .ebz file mapping and CEBZ entry processing.

Investigates how effect names (ef00-ef39) resolve to .ebz file paths,
and how CEBZ entries are processed per-effect at runtime.
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


def disasm_instruction(word, vaddr):
    info = decode_instruction(word, vaddr)
    return info.get('mnemonic', f'unk_op_0x{word>>26:02X} 0x{word:08X}')


def find_strings(data, min_len=3):
    strings = []
    i = 0x80
    while i < len(data):
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            if i - start >= min_len:
                s = data[start:i].decode('ascii')
                vaddr = file_to_vaddr(start)
                strings.append((start, vaddr, s))
        else:
            i += 1
    return strings


def disasm_range(data, start_file_off, end_file_off, max_lines=200):
    lines = []
    off = start_file_off
    count = 0
    while off < len(data) - 4 and count < max_lines:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        mnemonic = disasm_instruction(word, vaddr)
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


def find_lui_ori_pairs(data, start_off, end_off):
    pairs = []
    i = start_off
    while i < end_off - 4:
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x0F:  # LUI
            rt = (word >> 16) & 0x1F
            imm = word & 0xFFFF
            if i + 4 < len(data):
                w2 = struct.unpack_from('<I', data, i + 4)[0]
                op2 = (w2 >> 26) & 0x3F
                if op2 == 0x0D:  # ORI
                    rt2 = (w2 >> 16) & 0x1F
                    rs2 = (w2 >> 21) & 0x1F
                    imm2 = w2 & 0xFFFF
                    if rt2 == rt and rs2 == rt:
                        full_addr = (imm << 16) | imm2
                        vaddr = file_to_vaddr(i)
                        pairs.append((vaddr, i, rt, imm, imm2, full_addr))
                        i += 8
                        continue
        i += 4
    return pairs


def trace_effect_name_table(data):
    """Dump the effect name table at 0x004C4E60-0x004C4F98."""
    print("=" * 70)
    print("STG EFFECT NAME TABLE (ef00-ef39)")
    print("=" * 70)
    start_off = vaddr_to_file(0x004C4E60)
    end_off = vaddr_to_file(0x004C4FA0)
    for off in range(start_off, min(end_off, len(data) - 8), 8):
        val = struct.unpack_from('<I', data, off)[0]
        name_bytes = data[off+4:off+8]
        if len(name_bytes) < 4:
            break
        name_str = name_bytes.decode('ascii', errors='replace')
        vaddr = file_to_vaddr(off)
        print(f"  0x{off:06X} (v 0x{vaddr:08X}): u32=0x{val:08X} name={name_str}")


def trace_effect_name_usage(data):
    """Find all code that references effect names and trace usage."""
    print("\n" + "=" * 70)
    print("EFXX NAME USAGE TRACE")
    print("=" * 70)
    effect_names = [
        ('ef00', 0x004C4E60), ('ef01', 0x004C4E68), ('ef02', 0x004C4E70),
        ('ef03', 0x004C4E78), ('ef04', 0x004C4E80), ('ef05', 0x004C4E88),
        ('ef06', 0x004C4E90), ('ef07', 0x004C4E98), ('ef08', 0x004C4EA0),
        ('ef09', 0x004C4EA8), ('ef10', 0x004C4EB0), ('ef11', 0x004C4EB8),
        ('ef12', 0x004C4EC0), ('ef13', 0x004C4EC8), ('ef14', 0x004C4ED0),
        ('ef15', 0x004C4ED8), ('ef16', 0x004C4EE0), ('ef17', 0x004C4EE8),
        ('ef18', 0x004C4EF0), ('ef19', 0x004C4EF8), ('ef20', 0x004C4F00),
        ('ef21', 0x004C4F08), ('ef22', 0x004C4F10), ('ef23', 0x004C4F18),
        ('ef24', 0x004C4F20), ('ef25', 0x004C4F28), ('ef26', 0x004C4F30),
        ('ef27', 0x004C4F38), ('ef28', 0x004C4F40), ('ef29', 0x004C4F48),
        ('ef30', 0x004C4F50), ('ef31', 0x004C4F58), ('ef32', 0x004C4F60),
        ('ef33', 0x004C4F68), ('ef34', 0x004C4F70), ('ef35', 0x004C4F78),
        ('ef36', 0x004C4F80), ('ef37', 0x004C4F88), ('ef38', 0x004C4F90),
        ('ef39', 0x004C4F98),
    ]
    found_any = False
    for name, vaddr in effect_names:
        file_off = vaddr_to_file(vaddr)
        raw_refs = find_raw_addr_refs(data, vaddr)
        if raw_refs:
            found_any = True
            print(f"\n  {name} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X}):")
            print(f"    raw-refs: {len(raw_refs)}")
            for kind, ref_vaddr, ref_off in raw_refs[:3]:
                print(f"      {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
    if not found_any:
        print("  No direct references found (names constructed at runtime)")


def trace_ebz_file_path_construction(data):
    """Trace how .ebz file paths are constructed from effect names."""
    print("\n" + "=" * 70)
    print("EBZ FILE PATH CONSTRUCTION TRACE")
    print("=" * 70)
    for name, vaddr in [("eff/e%c%c/%s", 0x004C3AF0), ("%s.ebz", 0x004CEF28)]:
        print(f"\n--- {name} at vaddr 0x{vaddr:08X} ---")
        gp_refs = find_gp_refs(data, vaddr)
        raw_refs = find_raw_addr_refs(data, vaddr)
        print(f"  $gp-relative refs: {len(gp_refs)}, raw-refs: {len(raw_refs)}")
        for kind, ref_vaddr, ref_off in gp_refs[:5]:
            print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
        for kind, ref_vaddr, ref_off in raw_refs[:5]:
            print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")


def trace_cebz_entry_processing(data):
    """Trace how CEBZ entries are processed per-effect."""
    print("\n" + "=" * 70)
    print("CEBZ ENTRY PROCESSING PER-EFFECT TRACE")
    print("=" * 70)
    start_off = vaddr_to_file(0x003301E0)
    end_off = vaddr_to_file(0x00330400)
    print(f"\n--- CEBZ loading code (vaddr 0x003301E0-0x00330400) ---")
    lines = disasm_range(data, start_off, end_off, max_lines=100)
    for line in lines:
        print(line)
    print(f"\n--- JAL targets in CEBZ loading code ---")
    jal_targets = find_jals_in_range(data, start_off, end_off)
    for vaddr, off, target_vaddr, file_tgt in jal_targets:
        print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> target vaddr 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")


def trace_mdl_pix_binding(data):
    """Trace how .mdl models bind to .pix textures at runtime."""
    print("\n" + "=" * 70)
    print("MODEL (.mdl) -> TEXTURE (.pix) BINDING TRACE")
    print("=" * 70)
    pix_fmt_vaddr = 0x004CC5B0
    print(f"\n--- %s.pix format string at vaddr 0x{pix_fmt_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, pix_fmt_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:10]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
    print(f"\n--- LUI/ORI address construction near pix refs ---")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        for back in range(0, 32, 4):
            chk_off = ref_off - back
            if chk_off < 0x80:
                break
            word = struct.unpack_from('<I', data, chk_off)[0]
            op = (word >> 26) & 0x3F
            if op == 0x0F:  # LUI
                rt = (word >> 16) & 0x1F
                imm = word & 0xFFFF
                if chk_off + 4 < len(data):
                    w2 = struct.unpack_from('<I', data, chk_off + 4)[0]
                    op2 = (w2 >> 26) & 0x3F
                    if op2 == 0x0D and ((w2 >> 16) & 0x1F) == rt and ((w2 >> 21) & 0x1F) == rt:
                        imm2 = w2 & 0xFFFF
                        full_addr = (imm << 16) | imm2
                        chk_vaddr = file_to_vaddr(chk_off)
                        print(f"    LUI/ORI at vaddr 0x{chk_vaddr:08X}: ${rt}=0x{imm:04X} ${rt}=0x{imm2:04X} -> 0x{full_addr:08X}")


def trace_effect_update_loop(data):
    """Trace the main effect update/destroy loop."""
    print("\n" + "=" * 70)
    print("EFFECT UPDATE/DESTROY LOOP TRACE")
    print("=" * 70)
    cezb_effect_obj_vaddr = 0x004CEF50
    print(f"\n--- CEBZEffectObj class at vaddr 0x{cezb_effect_obj_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, cezb_effect_obj_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
    ceffect_mgr_vaddr = 0x004CA870
    print(f"\n--- CEffectMgr class at vaddr 0x{ceffect_mgr_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, ceffect_mgr_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    trace_effect_name_table(data)
    trace_effect_name_usage(data)
    trace_ebz_file_path_construction(data)
    trace_cebz_entry_processing(data)
    trace_mdl_pix_binding(data)
    trace_effect_update_loop(data)


if __name__ == '__main__':
    main()
