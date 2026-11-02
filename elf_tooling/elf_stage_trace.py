#!/usr/bin/env python3
"""
ELF tooling: Deep trace of STG stage -> .ebz effect linkage.

Traces how STG EFFECT root nodes (ef00, ef01, etc.) reference .ebz effect files,
and how SPT script commands trigger effect spawning through CEffectMgr.
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
    """Find $gp-relative references to target_vaddr."""
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
    """Find raw 32-bit address values in code section."""
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


def trace_stg_effect_linkage(data):
    """
    Trace how STG EFFECT root nodes reference .ebz files.
    
    The STG scene graph has EFFECT root with efXX child nodes.
    Each efXX node corresponds to an effect that gets spawned from an .ebz file.
    """
    print("=" * 70)
    print("STG EFFECT -> .ebz LINKAGE TRACE")
    print("=" * 70)

    # Effect name strings found in ELF data section
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

    print("\n--- STG Effect name references (ef00-ef39) ---")
    found_any = False
    for name, vaddr in effect_names:
        gp_refs = find_gp_refs(data, vaddr)
        raw_refs = find_raw_addr_refs(data, vaddr)
        if gp_refs or raw_refs:
            found_any = True
            file_off = vaddr_to_file(vaddr)
            print(f"\n  {name} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X}):")
            print(f"    gp-refs: {len(gp_refs)}, raw-refs: {len(raw_refs)}")
            for kind, ref_vaddr, ref_off in gp_refs[:3]:
                print(f"      {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
    
    if not found_any:
        print("  No direct gp-relative references found (names may be constructed at runtime)")
    
    # Look for the effect name table
    print("\n--- Effect name table search ---")
    # Look for sequential ef00, ef01, ef02... pattern in data
    for start in range(0x80, 0x400700 - 40, 4):
        match = True
        for i in range(10):
            chk_off = start + i * 8
            if chk_off + 8 > len(data):
                match = False
                break
            # Check for "efNN\0" pattern
            name_bytes = data[chk_off+4:chk_off+8]
            if len(name_bytes) < 4:
                match = False
                break
            if name_bytes[0:2] != b'ef' or not name_bytes[2:4].isdigit() or name_bytes[3] != 0:
                match = False
                break
            # Check for preceding u32 value
            if chk_off >= 4:
                prev_val = struct.unpack_from('<I', data, chk_off-4)[0]
                # Could be an index or pointer
        
        if match:
            vaddr = file_to_vaddr(start)
            print(f"  Effect table at file 0x{start:06X} (vaddr 0x{vaddr:08X}):")
            for i in range(min(10, (0x400700 - start) // 8)):
                chk_off = start + i * 8
                if chk_off + 8 > len(data):
                    break
                name_bytes = data[chk_off+4:chk_off+8]
                prev_val = struct.unpack_from('<I', data, chk_off-4)[0] if chk_off >= 4 else 0
                name_str = name_bytes.decode('ascii', errors='replace')
                print(f"    [{i}] val=0x{prev_val:08X} name={name_str}")
            break


def trace_cebz_loading_chain(data):
    """
    Trace the CEBZ effect loading chain from STG effect nodes through CEffectMgr.
    
    The chain is:
    STG EFFECT root -> efXX nodes -> CEffectMgr -> CEBZData -> CEBZHandle -> CEBZEffectObj
    """
    print("\n" + "=" * 70)
    print("CEBZ EFFECT LOADING CHAIN")
    print("=" * 70)

    # Key addresses from earlier analysis
    cebz_block_vaddr = 0x004FE628  # CEBZ class info block
    ceffect_mgr_vaddr = 0x004CA870  # CEffectMgr class
    cebz_data_vaddr = 0x004CEF18   # CEBZData class name
    ceffect_mgr_data_vaddr = 0x004CA870  # CEffectMgr class name
    ebz_fmt_vaddr = 0x004CEF28     # %s.ebz format string
    
    print(f"\n--- CEBZ class info block at vaddr 0x{cebz_block_vaddr:08X} ---")
    # Dump key fields
    block_off = vaddr_to_file(cebz_block_vaddr)
    for i in range(0, 0x60, 4):
        off = block_off + i
        if off + 4 > len(data):
            break
        val = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        # Try to interpret as string pointer
        str_file = vaddr_to_file(val)
        str_val = ''
        if 0x80 <= str_file < len(data) - 1:
            end = data.find(b'\x00', str_file)
            if end == -1:
                end = len(data)
            s = data[str_file:end].decode('ascii', errors='replace')
            if len(s) >= 2 and all(32 <= b < 127 or b == 0 for b in data[str_file:end]):
                str_val = f' -> "{s}"'
        print(f"  0x{off:06X} (v 0x{vaddr:08X}): 0x{val:08X}{str_val}")

    print(f"\n--- CEBZ loading code disassembly ---")
    # The main loading code at 0x003301E0
    start_off = vaddr_to_file(0x003301E0)
    end_off = vaddr_to_file(0x00330300)
    lines = disasm_range(data, start_off, end_off, max_lines=48)
    for line in lines:
        print(line)

    # Look for JAL targets in this range
    print(f"\n--- JAL targets in CEBZ loading code ---")
    for off in range(start_off, end_off - 4, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            file_tgt = vaddr_to_file(target_vaddr)
            print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> target vaddr 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")


def trace_model_texture_linkage(data):
    """
    Trace how MDL models reference PIX textures and PMT materials.
    """
    print("\n" + "=" * 70)
    print("MODEL (.mdl) -> TEXTURE (.pix) / MATERIAL (.pmt) LINKAGE")
    print("=" * 70)

    # .mdl format string
    mdl_fmt_vaddr = 0x004CC5A8
    pix_fmt_vaddr = 0x004CC5B0
    pmt_fmt_vaddr = 0x004CC728
    
    print(f"\n--- Format strings ---")
    for name, vaddr in [('%s.mdl', mdl_fmt_vaddr), ('%s.pix', pix_fmt_vaddr), ('%s.pmt', pmt_fmt_vaddr)]:
        gp_refs = find_gp_refs(data, vaddr)
        print(f"  {name} at vaddr 0x{vaddr:08X}: {len(gp_refs)} gp-refs")
        for kind, ref_vaddr, ref_off in gp_refs[:3]:
            print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    # Look for FMDL magic references in code
    fmdl_magic_vaddr = 0x004B7210
    print(f"\n--- FMDL magic (0x{0x464D4C:08X}) at vaddr 0x{fmdl_magic_vaddr:08X} ---")
    gp_refs = find_gp_refs(data, fmdl_magic_vaddr)
    print(f"  $gp-relative refs: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs[:5]:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")


def generate_linkage_report(data):
    """Generate a comprehensive linkage report."""
    print("\n" + "=" * 70)
    print("FORMAT INTERACTION LINKAGE REPORT")
    print("=" * 70)

    report = {
        'elf_file': 'SLUS_214.42',
        'interaction_chains': {
            'STG_stage -> .ebz_effect': {
                'path': 'STG file -> EFFECT root -> efXX node -> CEffectMgr -> CEBZData -> .ebz file',
                'key_code': '0x003301E0-0x00330300 (CEBZ loading)',
                'key_data': '0x004FE628 (CEBZ class info block), 0x004CEF28 (%s.ebz format)',
                'description': 'STG stage files contain EFFECT root with efXX nodes. Each efXX node references an effect that gets loaded from a .ebz file via CEffectMgr.',
            },
            'STG_stage -> .hit_collision': {
                'path': 'STG file -> STAGE root -> collision nodes -> .hit file',
                'key_code': 'STG file parse code',
                'key_data': '0x004C8860 (s01a.hit), 0x004C9520 (s10a.hit), etc.',
                'description': 'STG stage files contain collision geometry references to .hit files.',
            },
            'STG_stage -> .mdl_model': {
                'path': 'STG file -> STAGE root -> model nodes -> .mdl file',
                'key_code': 'STG file parse code',
                'key_data': '0x004CC5A8 (%s.mdl format string)',
                'description': 'STG stage files reference .mdl model files for stage geometry.',
            },
            'MDL_model -> .pix_texture': {
                'path': 'MDL file -> material slots -> .pix texture files',
                'key_code': '0x003A4160-0x003A4190 (resource table init)',
                'key_data': '0x004CC5B0 (%s.pix format string)',
                'description': 'MDL model files reference texture files (.pix) via material slots.',
            },
            'MDL_model -> .pmt_material': {
                'path': 'MDL file -> material definitions -> .pmt files',
                'key_code': '0x003A4280 (resource table init)',
                'key_data': '0x004CC728 (%s.pmt format string)',
                'description': 'MDL model files reference material files (.pmt) via material definitions.',
            },
            'MDL_model -> .ani_animation': {
                'path': 'MDL file -> animation references -> .ani files',
                'key_code': '0x004CFAF0 (%s.ani format string)',
                'key_data': '0x004CFAF0 (%s.ani format string)',
                'description': 'MDL model files reference animation files (.ani) for skeletal animation.',
            },
            'STG_stage -> .ase_audio': {
                'path': 'STG stage -> audio nodes -> .ase sound bank files',
                'key_code': '0x00340AC4 (enter.ase), 0x003A39BC (ending.ase)',
                'key_data': '0x004DAC70 (enter.ase), 0x004DB8B0 (ending.ase)',
                'description': 'STG stage files reference audio bank files (.ase) for stage audio.',
            },
            'STG_stage -> .ams_music': {
                'path': 'STG stage -> music nodes -> .ams sequence files',
                'key_code': '0x00242064-0x003A44A8 (AMS references)',
                'key_data': '0x00499280 (sel_in.ams), 0x004992A4 (sel_lp.ams), etc.',
                'description': 'STG stage files reference sound sequence files (.ams) for stage music.',
            },
            'SPT_script -> .ebz_effect': {
                'path': 'SPT script -> effect command -> CEffectMgr -> .ebz file',
                'key_code': 'SPT command handlers call CEffectMgr',
                'key_data': 'SPT commands 29-30 (set_character_pose, set_character_pose_variant)',
                'description': 'SPT scripts can trigger effect spawning through commands that reference .ebz files.',
            }
        },
        'runtime_object_model': {
            'CEffectMgr': 'Singleton effect manager. Loads .ebz files, creates CEBZEffectObj instances.',
            'CEBZData': 'Parsed .ebz file data (header, ref table, entries).',
            'CEBZHandle': 'Handle to a loaded .ebz effect.',
            'CEBZEffectObj': 'Runtime effect instance with transform, animation state.',
            'CEBZEffMatrix': 'Effect transformation matrix.',
            'CEBZEffectEle': 'Effect element (particle, sprite, etc).',
            'CEBZEffectGen': 'Effect generator.',
            'CEBZEffectBase': 'Base effect class.',
        },
        'file_loading_chain': {
            'GAME.DAT/INFO.DAT': 'Archives containing all asset files.',
            'CFileLoadMng': 'File loading manager for archives.',
            'cvFsOpen': 'Open file in archive.',
            'CCDRead': 'Read data from archive file.',
        }
    }

    import json
    print(json.dumps(report, indent=2))

    output_path = Path('C:/Dev/arika/stage_effect_linkage_report.json')
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {output_path}")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    trace_stg_effect_linkage(data)
    trace_cebz_loading_chain(data)
    trace_model_texture_linkage(data)
    generate_linkage_report(data)
