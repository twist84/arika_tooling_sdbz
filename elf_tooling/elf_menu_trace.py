#!/usr/bin/env python3
"""
ELF tooling: Deep trace of menu -> effect spawning pipeline.

Investigates how menu classes (CMenuMainMenu, CMenuOption, etc.) trigger
.ebz effect loading via CEffectMgr, and how menu textures/audio are loaded.
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


def trace_menu_class_code(data):
    """
    Trace code around menu class references to understand how menus load
    assets and trigger effect spawning.
    """
    print("=" * 70)
    print("MENU CLASS CODE TRACE")
    print("=" * 70)

    # Key menu class vaddrs
    menu_classes = {
        'CMenuFuncMgr': 0x003CDEA0,
        'CMenuMainMenu': 0x003CEE50,
        'CMenuOption': 0x003CDF70,
        'CMenuPause': 0x003CDFA0,
        'CAppMenuMain': 0x003DBF10,
        'CAppTitleMain': 0x003DB8B0,
    }

    for name, vaddr in menu_classes.items():
        print(f"\n--- {name} at vaddr 0x{vaddr:08X} (file 0x{vaddr_to_file(vaddr):06X}) ---")
        # Disassemble code around the reference to this class
        gp_refs = find_gp_refs(data, vaddr)
        for kind, ref_vaddr, ref_off in gp_refs[:3]:
            print(f"\n  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X}):")
            start_off = max(ref_off - 24, 0x80)
            end_off = min(ref_off + 24, len(data) - 4)
            lines = disasm_range(data, start_off, end_off, max_lines=12)
            for line in lines:
                print(line)
            print()


def trace_menu_file_loading(data):
    """
    Trace how menu files (.stg) are loaded and what assets they reference.
    """
    print("\n" + "=" * 70)
    print("MENU STAGE LOADING TRACE")
    print("=" * 70)

    # Menu stage file paths
    menu_stg_files = ['dis/main_menu', 'dis/result', 'dis/option']

    for name, vaddr in [('dis/main_menu', 0x003CEDF8), ('dis/result', 0x003CE3E0)]:
        print(f"\n--- {name} at vaddr 0x{vaddr:08X} (file 0x{vaddr_to_file(vaddr):06X}) ---")
        gp_refs = find_gp_refs(data, vaddr)
        raw_refs = find_raw_addr_refs(data, vaddr)
        print(f"  gp-refs: {len(gp_refs)}, raw-refs: {len(raw_refs)}")
        for kind, ref_vaddr, ref_off in gp_refs[:5]:
            print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
            # Disassemble around each reference
            start_off = max(ref_off - 16, 0x80)
            end_off = min(ref_off + 16, len(data) - 4)
            lines = disasm_range(data, start_off, end_off, max_lines=8)
            for line in lines:
                print(f"    {line}")


def trace_cebz_from_menu(data):
    """
    Trace how menu code triggers CEBZ effect loading.
    """
    print("\n" + "=" * 70)
    print("MENU -> CEBZ EFFECT LINKAGE TRACE")
    print("=" * 70)

    # The CEBZ loading code at 0x003301E0
    print(f"\n--- CEBZ loading code (vaddr 0x003301E0-0x00330300) ---")
    start_off = vaddr_to_file(0x003301E0)
    end_off = vaddr_to_file(0x00330300)
    lines = disasm_range(data, start_off, end_off, max_lines=64)
    for line in lines:
        print(line)

    # JAL targets
    print(f"\n--- JAL targets called from CEBZ loading code ---")
    jal_targets = find_jals_in_range(data, start_off, end_off)
    for vaddr, off, target_vaddr, file_tgt in jal_targets:
        print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> target vaddr 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")


def trace_menu_audio(data):
    """
    Trace how menu audio (.ase/.ams) files are loaded.
    """
    print("\n" + "=" * 70)
    print("MENU AUDIO (.ase/.ams) LOADING TRACE")
    print("=" * 70)

    # Menu audio files
    audio_files = [
        ('sqm/menu_in.ams', 0x0039B880),
        ('sqm/menu_lp.ams', 0x0039B8A4),
    ]

    for name, vaddr in audio_files:
        print(f"\n  {name} at vaddr 0x{vaddr:08X} (file 0x{vaddr_to_file(vaddr):06X})")
        gp_refs = find_gp_refs(data, vaddr)
        print(f"    gp-refs: {len(gp_refs)}")
        for kind, ref_vaddr, ref_off in gp_refs[:5]:
            print(f"      {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")


def generate_menu_report(data):
    """Generate comprehensive menu interaction report."""
    print("\n" + "=" * 70)
    print("MENU FORMAT INTERACTION REPORT")
    print("=" * 70)

    import json
    report = {
        'elf_file': 'SLUS_214.42',
        'menu_files': {
            'dis/main_menu': {'vaddr': 0x003CEDF8, 'type': 'stage'},
            'dis/result': {'vaddr': 0x003CE3E0, 'type': 'stage'},
            'sqm/menu_in.ams': {'vaddr': 0x0039B880, 'type': 'audio'},
            'sqm/menu_lp.ams': {'vaddr': 0x0039B8A4, 'type': 'audio'},
        },
        'menu_classes': [
            'CEffectMgr', 'CMenuFuncMgr', 'CMenuFuncBase', 'CMenuKeyConfig',
            'CMenuOption', 'CMenuSelBase', 'CMenuPause', 'CMenuListBase',
            'CMenuGameOption', 'CMenuSoundSet', 'CMenuMsgBase',
            'CMenuCommandL', 'CMenuPauseTra', 'CMenuObst', 'CMenuVsStatus',
            'CMenuDisplayS', 'CMenuContinue', 'CMenuMemoryCa',
            'CMenuPauseCon', 'CMenuVsResult', 'CMenuSurvBoss',
            'CMenuShenCate', 'CMenuTextBase', 'CMenuShenMain',
            'CMenuShenNewW', 'CMenuShenWish', 'CMenuMainMenu',
            'CAppTitleMain', 'CAppMenuMain',
        ],
        'interaction_chains': {
            'STG_menu -> .ebz_effect': {
                'path': 'STG stage -> EFFECT root -> efXX node -> CEffectMgr -> CEBZData -> .ebz file',
                'key_code': '0x003301E0-0x00330300 (CEBZ loading)',
                'key_data': '0x004FE628 (CEBZ class info block), 0x004CEF28 (%s.ebz format)',
            },
            'STG_menu -> .pix_texture': {
                'path': 'STG stage -> texture nodes -> .pix file',
                'key_code': '0x003A4160 (%s.pix format ref)',
                'key_data': '0x004CC5B0 (%s.pix format string)',
            },
            'STG_menu -> .ase/.ams_audio': {
                'path': 'STG stage -> audio nodes -> .ase/.ams files',
                'key_code': '0x00340AC4 (enter.ase), 0x003A39BC (ending.ase)',
                'key_data': '0x0039B880 (sqm/menu_in.ams), 0x0039B8A4 (sqm/menu_lp.ams)',
            },
        },
        'runtime_object_model': {
            'CEffectMgr': 'Effect manager - loads .ebz files, creates CEBZEffectObj instances',
            'CEBZData': 'Parsed .ebz file data',
            'CEBZEffectObj': 'Runtime effect instance',
            'CMenuFuncMgr': 'Menu function manager',
            'CMenuMainMenu': 'Main menu manager',
            'CAppMenuMain': 'App menu main state',
        },
    }

    print(json.dumps(report, indent=2))

    output_path = Path('C:/Dev/arika/menu_interaction_report.json')
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {output_path}")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    trace_menu_class_code(data)
    trace_menu_file_loading(data)
    trace_menu_audio(data)
    trace_cebz_from_menu(data)
    generate_menu_report(data)
