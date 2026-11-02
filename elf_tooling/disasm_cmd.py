#!/usr/bin/env python3
"""Disassemble a command constructor function to understand its structure."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disassemble_function(data, start_file_off, max_instructions=100):
    """Disassemble a function starting at start_file_off."""
    off = start_file_off
    count = 0
    
    while off < len(data) - 4 and count < max_instructions:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mnemonic = info.get('mnemonic', f'unk_op_0x{word>>26:02X}')
        
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')
        
        # Stop at JR $RA
        if info.get('branch') == 'indirect' and info.get('reg') == 31:
            break
            
        off += 4
        count += 1


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    cmd_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x002C1830
    
    data = Path(elf_path).read_bytes()
    file_off = vaddr_to_file(cmd_vaddr)
    
    print(f"Disassembling command constructor at vaddr 0x{cmd_vaddr:08X} (file 0x{file_off:06X}):")
    print("=" * 70)
    disassemble_function(data, file_off)
