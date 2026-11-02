#!/usr/bin/env python3
"""Disassemble key ELF functions referenced by command constructors."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disassemble_function(data, start_file_off, max_instructions=80):
    """Disassemble a function starting at start_file_off."""
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
    
    # Key functions called by many command constructors
    targets = [
        (0x0018E408, 'Common function 1'),
        (0x00171F10, 'Common function 2'),
        (0x003ECBB0, 'Common function 3'),
        (0x003EC4F0, 'Common function 4'),
        (0x001E8150, 'Function called by cmd68'),
        (0x001EB700, 'Function called by cmd68'),
        (0x001EB2E0, 'Function called by cmd68'),
    ]
    
    data = Path(elf_path).read_bytes()
    
    for vaddr, name in targets:
        file_off = vaddr_to_file(vaddr)
        print(f"\n{'='*70}")
        print(f"Function {name} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X}):")
        print("=" * 70)
        disassemble_function(data, file_off)
        print()
