#!/usr/bin/env python3
"""Improved MIPS R5900 disassembler with branch target resolution and basic block tracing."""
import struct
import sys
from pathlib import Path


# MIPS opcodes (6-bit)
OPCODES = {
    0x00: 'R', 0x01: 'BCOND', 0x02: 'J', 0x03: 'JAL',
    0x04: 'BEQ', 0x05: 'BNE', 0x06: 'BLEZ', 0x07: 'BGTZ',
    0x08: 'ADDI', 0x09: 'ADDIU', 0x0A: 'SLTI', 0x0B: 'SLTIU',
    0x0C: 'ANDI', 0x0D: 'ORI', 0x0E: 'XORI', 0x0F: 'LUI',
    0x10: 'COP0', 0x11: 'COP1', 0x12: 'COP2', 0x13: 'COP3',
    0x20: 'LB', 0x21: 'LH', 0x22: 'LWL', 0x23: 'LW',
    0x24: 'LBU', 0x25: 'LHU', 0x26: 'LWR', 0x28: 'SB',
    0x29: 'SH', 0x2A: 'SWL', 0x2B: 'SW', 0x2E: 'SWR',
    0x30: 'TLB', 0x3F: 'CACHE',
}

# R-type funct codes
FUNCTS = {
    0x00: 'SLL', 0x02: 'SRL', 0x03: 'SRA', 0x04: 'SLLV',
    0x06: 'SRLV', 0x07: 'SRAV', 0x08: 'JR', 0x09: 'JALR',
    0x0C: 'SYSCALL', 0x0D: 'BREAK', 0x0E: 'SYNC',
    0x10: 'MFHI', 0x11: 'MTHI', 0x12: 'MFLO', 0x13: 'MTLO',
    0x18: 'MULT', 0x19: 'MULTU', 0x1A: 'DIV', 0x1B: 'DIVU',
    0x20: 'ADD', 0x21: 'ADDU', 0x22: 'SUB', 0x23: 'SUBU',
    0x24: 'AND', 0x25: 'OR', 0x26: 'XOR', 0x27: 'NOR',
    0x2A: 'SLT', 0x2B: 'SLTU',
}

# Branch condition codes (for bc1t/bc1f etc., but mainly for cop1)
BCOND = {0x00: 'BLTZ', 0x01: 'BGEZ', 0x02: 'BLTZL', 0x03: 'BGEZL',
         0x10: 'TGEI', 0x11: 'TGEIU', 0x12: 'TLTI', 0x13: 'TLTIU',
         0x14: 'TEQI', 0x16: 'TNEI', 0x18: 'BLTZAL', 0x19: 'BGEZAL',
         0x1A: 'BLTZALL', 0x1B: 'BGEZALL'}


def reg_name(n):
    """MIPS register name."""
    names = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']
    return names[n] if 0 <= n < 32 else f'${n}'


def decode_instruction(word, vaddr=None):
    """Decode a single MIPS instruction, resolving branch/jump targets."""
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    target = word & 0x3FFFFFF

    # Sign-extend immediate
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    info = {'op': op, 'word': word, 'vaddr': vaddr, 'imm': imm}

    if op == 0x00:  # R-type
        name = FUNCTS.get(funct, f'unk_funct_0x{funct:02X}')
        if name == 'SLL':
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{sa}'
        elif name in ('SRL', 'SRA'):
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{sa}'
        elif name == 'SLLV':
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{reg_name(rs)}'
        elif name == 'SRLV':
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{reg_name(rs)}'
        elif name == 'SRAV':
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{reg_name(rs)}'
        elif name == 'JR':
            info['mnemonic'] = f'{name} {reg_name(rs)}'
            info['branch'] = 'indirect'
            info['reg'] = rs
        elif name == 'JALR':
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rs)}'
            info['branch'] = 'indirect_call'
            info['reg'] = rs
        elif name == 'SYSCALL':
            info['mnemonic'] = name
        elif name == 'BREAK':
            info['mnemonic'] = name
        elif name == 'SYNC':
            info['mnemonic'] = name
        elif name in ('MFHI', 'MTHI', 'MFLO', 'MTLO'):
            if name == 'MFHI':
                info['mnemonic'] = f'{name} {reg_name(rd)}'
            elif name == 'MTHI':
                info['mnemonic'] = f'{name} {reg_name(rs)}'
            elif name == 'MFLO':
                info['mnemonic'] = f'{name} {reg_name(rd)}'
            else:
                info['mnemonic'] = f'{name} {reg_name(rs)}'
        elif name in ('MULT', 'MULTU', 'DIV', 'DIVU'):
            info['mnemonic'] = f'{name} {reg_name(rs)},{reg_name(rt)}'
        elif name in ('ADD', 'ADDU', 'SUB', 'SUBU', 'AND', 'OR', 'XOR', 'NOR', 'SLT', 'SLTU'):
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rs)},{reg_name(rt)}'
        else:
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rs)},{reg_name(rt)}'

    elif op == 0x01:  # Branch on condition / cop1
        bc = rt  # For bc1t/bc1f, rt is the condition; for BLTZ etc., rt is the subtype
        if rs == 0x00:  # BLTZ, BGEZ, etc.
            name = BCOND.get(rt, f'unk_bcond_0x{rt:02X}')
            offset = imm_signed * 4
            target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
            info['mnemonic'] = f'{name} {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else name
            info['branch'] = 'cond'
            info['target'] = target_vaddr
        elif rs == 0x10:  # Trap immediate
            name = BCOND.get(rt, f'unk_trap_0x{rt:02X}')
            info['mnemonic'] = f'{name} {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        else:
            name = BCOND.get(rt, f'unk_bcond_0x{rt:02X}')
            offset = imm_signed * 4
            target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
            info['mnemonic'] = f'{name} {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else name
            info['branch'] = 'cond'
            info['target'] = target_vaddr

    elif op == 0x02:  # J
        target_vaddr = (vaddr & 0xF0000000) | (target << 2)
        info['mnemonic'] = f'J 0x{target_vaddr:08X}'
        info['branch'] = 'direct'
        info['target'] = target_vaddr

    elif op == 0x03:  # JAL
        target_vaddr = (vaddr & 0xF0000000) | (target << 2)
        info['mnemonic'] = f'JAL 0x{target_vaddr:08X}'
        info['branch'] = 'direct_call'
        info['target'] = target_vaddr

    elif op == 0x04:  # BEQ
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BEQ {reg_name(rs)},{reg_name(rt)},0x{target_vaddr:08X}' if target_vaddr else f'BEQ {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr

    elif op == 0x05:  # BNE
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BNE {reg_name(rs)},{reg_name(rt)},0x{target_vaddr:08X}' if target_vaddr else f'BNE {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr

    elif op == 0x06:  # BLEZ
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BLEZ {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else f'BLEZ {reg_name(rs)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr

    elif op == 0x07:  # BGTZ
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BGTZ {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else f'BGTZ {reg_name(rs)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr

    elif op == 0x08:  # ADDI
        info['mnemonic'] = f'ADDI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x09:  # ADDIU
        info['mnemonic'] = f'ADDIU {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0A:  # SLTI
        info['mnemonic'] = f'SLTI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0B:  # SLTIU
        info['mnemonic'] = f'SLTIU {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0C:  # ANDI
        info['mnemonic'] = f'ANDI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0D:  # ORI
        info['mnemonic'] = f'ORI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0E:  # XORI
        info['mnemonic'] = f'XORI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x0F:  # LUI
        info['mnemonic'] = f'LUI {reg_name(rt)},0x{imm:04X}'

    elif op == 0x20:  # LB
        info['mnemonic'] = f'LB {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x21:  # LH
        info['mnemonic'] = f'LH {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x22:  # LWL
        info['mnemonic'] = f'LWL {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x23:  # LW
        info['mnemonic'] = f'LW {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x24:  # LBU
        info['mnemonic'] = f'LBU {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x25:  # LHU
        info['mnemonic'] = f'LHU {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x26:  # LWR
        info['mnemonic'] = f'LWR {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x28:  # SB
        info['mnemonic'] = f'SB {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x29:  # SH
        info['mnemonic'] = f'SH {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2A:  # SWL
        info['mnemonic'] = f'SWL {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2B:  # SW
        info['mnemonic'] = f'SW {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2E:  # SWR
        info['mnemonic'] = f'SWR {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x3F:  # CACHE
        info['mnemonic'] = f'CACHE {sa},0x{imm:04X}({reg_name(rs)})'
    else:
        info['mnemonic'] = f'unk_op_0x{op:02X} 0x{word:08X}'

    return info


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disassemble_range(data, start_file_off, end_file_off):
    """Disassemble a range of file offsets."""
    results = []
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        info['file_off'] = off
        results.append(info)
    return results


def trace_basic_blocks(data, start_file_off, max_blocks=50, max_instr_per_block=200):
    """Trace basic blocks starting from an offset, following branches."""
    visited = set()
    blocks = []
    worklist = [start_file_off]

    while worklist and len(blocks) < max_blocks:
        block_start = worklist.pop(0)
        if block_start in visited:
            continue
        visited.add(block_start)

        block_instrs = []
        off = block_start
        end = min(block_start + max_instr_per_block * 4, len(data) - 4)

        while off < end:
            word = struct.unpack_from('<I', data, off)[0]
            vaddr = file_to_vaddr(off)
            info = decode_instruction(word, vaddr)
            info['file_off'] = off
            block_instrs.append(info)

            # Check if this is a terminating instruction
            if info.get('branch') in ('direct', 'indirect'):
                # Unconditional jump - end block, add target to worklist
                target = info.get('target')
                if target:
                    target_file = vaddr_to_file(target)
                    if target_file not in visited and 0x80 <= target_file < len(data) - 4:
                        worklist.append(target_file)
                break
            elif info.get('branch') == 'direct_call':
                # JAL - fall through but note the call
                target = info.get('target')
                if target:
                    target_file = vaddr_to_file(target)
                    # Don't add to worklist (it's a call, we'll trace it separately)
                    pass
                # Fall through to next instruction
            elif info.get('branch') == 'cond':
                # Conditional branch - end block, add both fall-through and target
                target = info.get('target')
                if target:
                    target_file = vaddr_to_file(target)
                    if target_file not in visited and 0x80 <= target_file < len(data) - 4:
                        worklist.append(target_file)
                # Fall-through
                next_off = off + 4
                if next_off not in visited and next_off < end:
                    worklist.append(next_off)
                break
            elif info.get('branch') in ('indirect_call',):
                # JALR - indirect call, can't statically resolve
                break
            elif info.get('mnemonic', '').startswith('JR'):
                # JR - indirect jump, can't statically resolve
                break

            off += 4

        blocks.append({'start_file_off': block_start, 'start_vaddr': file_to_vaddr(block_start), 'instructions': block_instrs})

    return blocks


def format_disassembly(instrs, show_bytes=True, annotate_strings=None, annotate_addrs=None):
    """Format disassembly output with annotations."""
    lines = []
    annotate_strings = annotate_strings or {}
    annotate_addrs = annotate_addrs or {}

    for info in instrs:
        vaddr = info['vaddr']
        off = info['file_off']
        word = info['word']
        mnemonic = info['mnemonic']

        # Annotate if this instruction references a known string address
        annotation = ''
        if vaddr in annotate_addrs:
            annotation = f'  ; {annotate_addrs[vaddr]}'
        elif off in annotate_addrs:
            annotation = f'  ; {annotate_addrs[off]}'

        byte_str = f'0x{word:08X}' if show_bytes else ''
        lines.append(f'  0x{vaddr:08X} 0x{off:06X}: {byte_str:>10}  {mnemonic}{annotation}')

    return '\n'.join(lines)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x230260
    end = int(sys.argv[3], 0) if len(sys.argv) > 3 else start + 256

    data = Path(path).read_bytes()
    for info in disassemble_range(data, start, end):
        print(format_disassembly([info]))
