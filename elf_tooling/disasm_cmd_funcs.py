#!/usr/bin/env python3
"""Disassemble additional key ELF functions referenced by command constructors."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disassemble_function(data, start_file_off, max_instructions=60):
    off = start_file_off
    count = 0
    while off < len(data) - 4 and count < max_instructions:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mnemonic = info.get('mnemonic', f'unk_op_0x{word>>26:02X}')
        print(f'  0x{vaddr:08X} 0x{off:06X}: {mnemonic}')
        if info.get('branch') == 'indirect' and info.get('reg') == 31:
            break
        off += 4
        count += 1


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    
    targets = [
        (0x00185E78, 'cmd29/cmd39 target 1'),
        (0x002CEA20, 'cmd29/cmd39 target 2'),
        (0x0041EBA0, 'cmd28/cmd38 target 1'),
        (0x0032B840, 'cmd16/cmd20/cmd93 target 2'),
        (0x00185CB0, 'cmd0/cmd3/etc target'),
    ]
    
    for vaddr, name in targets:
        file_off = vaddr_to_file(vaddr)
        print(f"\n{'='*70}")
        print(f"{name} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X}):")
        print("=" * 70)
        disassemble_function(data, file_off)
        print()
