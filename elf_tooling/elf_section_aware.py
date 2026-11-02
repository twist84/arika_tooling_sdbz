#!/usr/bin/env python3
"""
ELF tooling: Section/program-header-aware ELF analysis.

Existing elf tools hardcode code_start=0x80, code_end=0x400700. This tool parses
the ELF program headers (PT_LOAD segments) to discover the *actual* executable
and data ranges, then re-runs symbol reference scanning within those real bounds
and reports any references the hardcoded window misses.

Output:
  * ELF header summary (entry, phoff, phnum, endianness)
  * PT_LOAD segment map (vaddr, filesz, memsz, flags, code/data classification)
  * Computed code ranges (PF_X set) and data ranges (PF_R set)
  * Reference scan for known symbols within real code bounds
  * Diff vs hardcoded window: references found outside 0x80-0x400700
"""
import struct
import sys
from pathlib import Path


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def sign16(n):
    return n - 0x10000 if n & 0x8000 else n


def parse_elf_headers(data):
    """Return (endian, entry, phoff, phentsize, phnum, segments)."""
    if data[0:4] != b'\x7fELF':
        raise ValueError("not an ELF file")
    ei_class = data[4]
    ei_data = data[5]
    endian = '<' if ei_data == 1 else '>'
    if ei_class != 1:
        raise ValueError(f"unsupported ELF class {ei_class} (expected 32-bit)")
    e_entry = struct.unpack_from(f'{endian}I', data, 0x18)[0]
    e_phoff = struct.unpack_from(f'{endian}I', data, 0x1C)[0]
    e_phentsize = struct.unpack_from(f'{endian}H', data, 0x2A)[0]
    e_phnum = struct.unpack_from(f'{endian}H', data, 0x2C)[0]

    segments = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from(f'{endian}I', data, off)[0]
        p_offset = struct.unpack_from(f'{endian}I', data, off + 4)[0]
        p_vaddr = struct.unpack_from(f'{endian}I', data, off + 8)[0]
        p_paddr = struct.unpack_from(f'{endian}I', data, off + 0xC)[0]
        p_filesz = struct.unpack_from(f'{endian}I', data, off + 0x10)[0]
        p_memsz = struct.unpack_from(f'{endian}I', data, off + 0x14)[0]
        p_flags = struct.unpack_from(f'{endian}I', data, off + 0x18)[0]
        p_align = struct.unpack_from(f'{endian}I', data, off + 0x1C)[0]
        is_exec = bool(p_flags & 0x1)
        is_write = bool(p_flags & 0x2)
        is_read = bool(p_flags & 0x4)
        segments.append({
            'idx': i, 'type': p_type, 'offset': p_offset, 'vaddr': p_vaddr,
            'paddr': p_paddr, 'filesz': p_filesz, 'memsz': p_memsz,
            'flags': p_flags, 'align': p_align,
            'exec': is_exec, 'write': is_write, 'read': is_read,
        })
    return endian, e_entry, e_phoff, e_phentsize, e_phnum, segments


def find_refs_to_addr(data, target_vaddr, code_start_file, code_end_file):
    """Find all code references to target_vaddr within [code_start_file, code_end_file)."""
    target_upper = (target_vaddr >> 16) & 0xFFFF
    target_lower = target_vaddr & 0xFFFF
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        if i + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        imm_signed = sign16(imm)
        vaddr = file_to_vaddr(i)

        if op == 0x0F:  # lui
            if imm == target_upper and i + 4 < len(data):
                w2 = struct.unpack_from('<I', data, i + 4)[0]
                op2 = (w2 >> 26) & 0x3F
                if op2 == 0x0D:
                    rt2 = (w2 >> 16) & 0x1F
                    rs2 = (w2 >> 21) & 0x1F
                    imm2 = w2 & 0xFFFF
                    if rt2 == rt and rs2 == rt and imm2 == target_lower:
                        results.append(('lui+ori', vaddr, i, target_vaddr))
        elif op == 0x0D:  # ori
            if rs == 28 and imm == target_lower:
                results.append(('ori-from-gp', vaddr, i, target_vaddr))
        elif op in (0x23, 0x2B):  # lw / sw
            if rs == 28 and imm == target_lower:
                results.append(('gp-mem', vaddr, i, target_vaddr))
        elif op == 0x09:  # addiu
            if rs == 28 and imm == target_lower:
                results.append(('addiu-from-gp', vaddr, i, target_vaddr))
    return results


def find_raw_value_hits(data, target_vaddr, code_start_file, code_end_file):
    """Find raw 32-bit little-endian copies of target_vaddr within code bounds."""
    target_bytes = struct.pack('<I', target_vaddr)
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        if data[i:i + 4] == target_bytes:
            results.append((file_to_vaddr(i), i))
    return results


def find_jal_targets(data, target_vaddr, code_start_file, code_end_file):
    """Find JAL instructions whose absolute target is target_vaddr within bounds."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        if i + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            from_vaddr = file_to_vaddr(i)
            target_idx = word & 0x3FFFFFF
            target = (from_vaddr & 0xF0000000) | (target_idx << 2)
            if target == target_vaddr:
                results.append((from_vaddr, i))
    return results


def collect_refs(data, symbol, vaddr, cstart, cend):
    refs = []
    for kind, rv, off, _ in find_refs_to_addr(data, vaddr, cstart, cend):
        refs.append((kind, rv, off))
    for rv, off in find_raw_value_hits(data, vaddr, cstart, cend):
        refs.append(('raw-value', rv, off))
    for fv, off in find_jal_targets(data, vaddr, cstart, cend):
        refs.append(('jal-target', fv, off))
    refs.sort(key=lambda r: r[2])
    return refs


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    endian, entry, phoff, phentsize, phnum, segments = parse_elf_headers(data)

    print("=" * 72)
    print("ELF PROGRAM-HEADER-AWARE ANALYSIS")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"  endian={'little' if endian == '<' else 'big'}  entry=0x{entry:08X}")
    print(f"  phoff=0x{phoff:X}  phentsize={phentsize}  phnum={phnum}")
    print()

    exec_segs = [s for s in segments if s['type'] == 1 and s['exec']]
    data_segs = [s for s in segments if s['type'] == 1 and s['read'] and not s['exec']]

    print("=== PT_LOAD segments ===")
    for s in segments:
        kind = []
        if s['exec']:
            kind.append('CODE')
        if s['read']:
            kind.append('DATA')
        if s['write']:
            kind.append('WRITABLE')
        kstr = '+'.join(kind) if kind else 'OTHER'
        print(f"  [{s['idx']:2d}] type=0x{s['type']:02X} off=0x{s['offset']:06X} vaddr=0x{s['vaddr']:08X}")
        print(f"       filesz=0x{s['filesz']:06X} memsz=0x{s['memsz']:06X} flags=0x{s['flags']:02X} ({kstr}) align=0x{s['align']:X}")
    print()

    # Compute real code file range (union of executable PT_LOAD segments)
    if exec_segs:
        real_code_start = min(s['offset'] for s in exec_segs)
        real_code_end = max(s['offset'] + s['filesz'] for s in exec_segs)
    else:
        real_code_start, real_code_end = 0x80, 0x400700

    print("=== Computed code/file ranges ===")
    print(f"  Real executable code file range: 0x{real_code_start:06X} - 0x{real_code_end:06X} "
          f"(size 0x{real_code_end - real_code_start:06X})")
    print(f"  Hardcoded (legacy) window:       0x{0x80:06X} - 0x{0x400700:06X} "
          f"(size 0x{0x400700 - 0x80:06X})")
    print()

    # Known symbols
    symbols = [
        ('Entry point', 0x00100008),
        ('CEffectMgr', 0x004CA870),
        ('CEBZData', 0x004CEF18),
        ('CEBZHandle', 0x004CEF30),
        ('CEBZBase', 0x004CEF40),
        ('CEBZEffectObj', 0x004CEF50),
        ('CEBZEffect', 0x004CF030),
        ('CEBZObject', 0x004C3C08),
        ('%s.ebz', 0x004CEF28),
        ('eff/e%c%c/%s', 0x004C3A88),
        ('trc/01/efin0001p0101', 0x004CF0A0),
    ]

    print(f"=== Reference scan within REAL code bounds "
          f"(0x{real_code_start:06X}-0x{real_code_end:06X}) ===")
    real_total = 0
    for name, vaddr in symbols:
        refs = collect_refs(data, name, vaddr, real_code_start, real_code_end)
        real_total += len(refs)
        print(f"  {name:<24} 0x{vaddr:08X}: {len(refs)} ref(s)")
        for kind, rv, off in refs[:6]:
            print(f"    {kind:<14} at vaddr 0x{rv:08X} (file 0x{off:06X})")
        if len(refs) > 6:
            print(f"    ... and {len(refs) - 6} more")
    print(f"  Total real-bounds refs: {real_total}")
    print()

    # Legacy scan within hardcoded window
    print(f"=== Reference scan within LEGACY hardcoded window "
          f"(0x{0x80:06X}-0x{0x400700:06X}) ===")
    legacy_total = 0
    legacy_refs = {}
    for name, vaddr in symbols:
        refs = collect_refs(data, name, vaddr, 0x80, 0x400700)
        legacy_refs[name] = refs
        legacy_total += len(refs)
    print(f"  Total legacy-bounds refs: {legacy_total}")
    print()

    # Diff: refs in real bounds but NOT in legacy
    print("=== References missed by legacy hardcoded window ===")
    missed = 0
    for name, vaddr in symbols:
        real_refs = collect_refs(data, name, vaddr, real_code_start, real_code_end)
        legacy_off = {off for _, _, off in legacy_refs[name]}
        newly = [r for r in real_refs if r[2] not in legacy_off]
        if newly:
            missed += len(newly)
            print(f"  {name:<24} 0x{vaddr:08X}: {len(newly)} newly found")
            for kind, rv, off in newly[:8]:
                print(f"    {kind:<14} at vaddr 0x{rv:08X} (file 0x{off:06X})")
    if missed == 0:
        print("  (none - legacy window already covers all references)")
    print()

    # Diff: refs in legacy window but NOT in real bounds (false positives from legacy)
    print("=== References in legacy window but outside real code bounds ===")
    extra = 0
    real_off_sets = {}
    for name, vaddr in symbols:
        real_refs = collect_refs(data, name, vaddr, real_code_start, real_code_end)
        real_off_sets[name] = {off for _, _, off in real_refs}
    for name, vaddr in symbols:
        for kind, rv, off in legacy_refs[name]:
            if off not in real_off_sets[name]:
                extra += 1
                print(f"  {name:<24} 0x{vaddr:08X}: {kind} at vaddr 0x{rv:08X} (file 0x{off:06X})")
    if extra == 0:
        print("  (none)")
    print()

    print("=== Conclusion ===")
    print(f"  Real code range covers {real_code_end - real_code_start} bytes of file.")
    print(f"  Legacy window covers {0x400700 - 0x80} bytes.")
    print(f"  New refs found by real bounds: {missed}")
    print(f"  Legacy-only (outside real code) refs: {extra}")


if __name__ == '__main__':
    main()
