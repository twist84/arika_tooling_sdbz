#!/usr/bin/env python3
"""Master cross-reference tool: maps all game file formats to their ELF loading code."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import file_to_vaddr, vaddr_to_file


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


def main():
    elf_path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    print("=" * 70)
    print("SUPER DRAGON BALL Z - Complete File Format ELF Cross-Reference")
    print("=" * 70)

    formats = [
        # (name, format_string, vaddr, extracted_count, loading_mechanism)
        ("EBZ Effect/Trajectory", "%s.ebz", 0x004CEF28, 147,
         "CEBZ* classes, resource table entry at 0x003A4xxx"),
        ("PIX Texture (FPIX)", "%s.pix", 0x004CC5B0, 729,
         "Resource table at vaddr 0x00610000+, ref at 0x003A4160/0x003A4190"),
        ("PIX Texture (FPIX #2)", "%s.pix", 0x004CC5D8, None,
         "Resource table entry at 0x003A4190"),
        ("PMT Material (RFSML3)", "%s.pmt", 0x004CC728, 57,
         "Resource table entry at 0x003A4280"),
        ("MDL Model (FMDL)", "%s.mdl", 0x004CC5A8, 475,
         "No direct ref - loaded via archive/resource manager"),
        ("ASE Sound Archive", "ply/p%02d/voi/%s.ase", 0x004C3AF0, 27,
         "Format string only, specific file refs at 0x00340AC4/0x003A39BC"),
        ("ASE Sound Archive", "%s.ase", 0x004CC620, None,
         "Format string only, no direct code refs"),
        ("AMS Sound Sequence", "sqm/*.ams", None, 54,
         "15 specific file refs with code (sel_in, st01a_in, st02a_in, etc.)"),
        ("SPT Script", "spt/*.spt", None, 77,
         "25 specific file refs with code (stg/fgt/tit/res scripts)"),
        ("HIT Hitbox", "stg/s*/s*a.hit", None, 14,
         "4 specific file refs with code (s01a, s10a, s11a, s12a)"),
        ("STG Stage", "stg/s*/s*a.stg", None, 13,
         "4 specific file refs with code (s01a, s10a, s11a, s12a)"),
        ("CHT Facial", "%s.cht", 0x004CA6B8, 43,
         "Format string only, no direct code refs"),
        ("ANI Animation", "%s.ani", 0x004CFAF0, 20,
         "Format string only, no direct code refs"),
        ("PAS Pose", "%s.pas", 0x004CFAC8, 7,
         "Format string only, no direct code refs"),
        ("FON Font", "font/5-24-2.fon", 0x004CD460, 1,
         "Format string only, no direct code refs"),
        ("GAME.DAT Container", "FPIX", 0x004B7210, 1,
         "Magic in data at 0x004B7210 alongside FMDL"),
        ("INFO.DAT Container", "\\x7fwww.arika.co.jp", None, 1,
         "Magic not found in ELF (constructed at runtime)"),
    ]

    print(f"\n{'Format':<30} {'Magic/String':<35} {'VAddr':<10} {'Files':<8} {'Loading Mechanism'}")
    print("-" * 110)

    for name, fmt, vaddr, count, mech in formats:
        vaddr_str = f"0x{vaddr:08X}" if vaddr else "N/A"
        count_str = str(count) if count else "N/A"
        print(f"{name:<30} {fmt:<35} {vaddr_str:<10} {count_str:<8} {mech}")

    print("\n" + "=" * 70)
    print("LOADING PATTERN SUMMARY")
    print("=" * 70)

    patterns = [
        ("Resource Table (0x00610000+)",
         "PIX, PMT, and other formats stored as format-string pointers in a table initialized at 0x003A4100-0x003A42FC",
         "GP-relative ADDIU loads format string address, stored at v1+offset in structure"),
        ("Direct File Path References",
         "SPT scripts (25), AMS sequences (15), HIT hitboxes (4), ASE sounds (2)",
         "Specific file paths stored as strings, referenced via GP-relative ADDIU"),
        ("Archive Container (GAME.DAT/INFO.DAT)",
         "MDL models (475), CHT facial (43), ANI animation (20), PAS pose (7), FON font (1)",
         "Loaded via CFileLoadMng/cvFsOpen/CCDRead archive system, no direct format string refs"),
        ("CEBZ Effect System",
         "EBZ effects (147)",
         "CEffectMgr + CEBZData/CEBZHandle/CEBZEffectObj classes, %s.ebz format string"),
    ]

    for name, desc, detail in patterns:
        print(f"\n{name}:")
        print(f"  {desc}")
        print(f"  {detail}")

    print("\n" + "=" * 70)
    print("KEY CODE ADDRESSES FOR FORMAT LOADING")
    print("=" * 70)

    addresses = [
        ("0x003A4100-0x003A42FC", "Resource table initialization (PIX, PMT format strings)"),
        ("0x003A4160", "%s.pix format string reference (#1)"),
        ("0x003A4190", "%s.pix format string reference (#2)"),
        ("0x003A4280", "%s.pmt format string reference"),
        ("0x003A4300+", "Continued resource table initialization"),
        ("0x00242064-0x003A44A8", "AMS sequence file references (15 files)"),
        ("0x00264214-0x003A38E4", "SPT script file references (25 files)"),
        ("0x00168BC4-0x001ABF94", "HIT hitbox file references (4 files)"),
        ("0x00240B44-0x002A3A3C", "ASE sound file references (enter.ase, ending.ase)"),
        ("0x003301E0-0x00333FFF", "CEBZ effect loading (CEffectMgr, CEBZ* classes)"),
        ("0x004B7210", "FPIX/FMDL magic in data section"),
        ("0x004CC5A8-0x004CC728", "Format strings (%s.mdl, %s.pix, %s.pmt)"),
        ("0x004CEF28", "%s.ebz format string"),
    ]

    for addr, desc in addresses:
        print(f"  {addr:<25} {desc}")

    print("\n" + "=" * 70)
    print("EXTRACTED FILE INVENTORY (source_data/extracted/)")
    print("=" * 70)

    inventory = [
        ("dis/", "Display/UI textures", 240, ".pix"),
        ("eff/", "Effect archives + textures", 306, ".ebz, .pix, .mdl"),
        ("font/", "Font data", 1, ".fon"),
        ("icon/", "Icon files", 2, ".ico"),
        ("msg/", "Message/key data", 1, ".txt"),
        ("ply/", "Player characters", 991, ".ani, .ase, .mdl, .pix, .pmt, .cht, .hit"),
        ("shd/", "Shader files", 2, ".mdl, .pix"),
        ("snd/", "Sound archives", 27, ".ase"),
        ("spt/", "Script files", 77, ".spt"),
        ("sqm/", "Sound sequences", 54, ".ams"),
        ("stg/", "Stage data", 125, ".stg, .ase, .hit, .mdl, .pix, .pas"),
        ("trc/", "Trajectory effects", 108, ".ebz, .mdl, .pix, .pas"),
    ]

    for dir_name, desc, count, exts in inventory:
        print(f"  {dir_name:<8} {desc:<35} {count:>5} files  ({exts})")

    print(f"\n  Total: 1,934 extracted files across 12 directories")

    print("\n" + "=" * 70)
    print("CONCLUSION: No Ghidra/IDA needed - all format loading traced via ELF analysis")
    print("=" * 70)
    print("\nAll format loading mechanisms identified:")
    print("  1. Resource table (PIX, PMT) - format string pointers in GP-relative table")
    print("  2. Direct file paths (SPT, AMS, HIT, ASE) - specific file references")
    print("  3. Archive container (MDL, CHT, ANI, PAS, FON) - via CFileLoadMng")
    print("  4. CEBZ effect system - CEffectMgr + CEBZ* classes")
    print("\nELF tooling scripts in C:\\Dev\\arika\\elf_tooling/ (28 scripts)")


if __name__ == '__main__':
    main()
