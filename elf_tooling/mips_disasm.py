#!/usr/bin/env python3
"""
MIPS R5900 disassembler for PS2 ELF files.

Provides instruction decoding used by elf tooling scripts.
Supports MIPS R5900 (PS2 CPU) instruction set including COP0, COP1 (FPU),
COP2 (VU0 vector), and MIPS32 instructions.
"""
import struct
import sys
from pathlib import Path

MIPS_REGS = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']


def reg_name(n):
    """Convert register number to name."""
    if 0 <= n < 32:
        return MIPS_REGS[n]
    return f'r{n}'


class DisasmInfo:
    """Decoded instruction information."""
    def __init__(self, mnemonic, vaddr, file_off, word, **kwargs):
        self.opcode = mnemonic
        self.vaddr = vaddr
        self.file_off = file_off
        self.word = word
        self.mnemonic = mnemonic
        self.defs = kwargs.get('defs', [])
        self.uses = kwargs.get('uses', [])
        self.branch_target = kwargs.get('branch_target')


def decode_instruction(word, vaddr=None):
    """Decode a MIPS R5900 instruction word."""
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    if op == 0x00:  # R-type
        if funct == 0x08:  # JR
            return IRInstr('jr', vaddr, file_off, mnemonic='JR',
                          uses=[rv(rs)] if rv(rs) else [])
        elif funct == 0x09:  # JALR
            return [IRInstr('jalr', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs)] if rv(rs) else [])]
        elif funct == 0x0C:  # SYSCALL
            return [IRInstr('syscall', vaddr, file_off, mnemonic)]
        elif funct == 0x0D:  # BREAK
            return [IRInstr('break', vaddr, file_off, mnemonic)]
        elif funct == 0x20:  # ADD
            return [IRInstr('add', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x21:  # ADDU
            return [IRInstr('addu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x22:  # SUB
            return [IRInstr('sub', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x23:  # SUBU
            return [IRInstr('subu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x24:  # AND
            return [IRInstr('and', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x25:  # OR
            return [IRInstr('or', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x26:  # XOR
            return [IRInstr('xor', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x27:  # NOR
            return [IRInstr('nor', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2A:  # SLT
            return [IRInstr('slt', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2B:  # SLTU
            return [IRInstr('sltu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2C:  # DADD
            return [IRInstr('dadd', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2D:  # DADDU
            return [IRInstr('daddu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2E:  # DSUB
            return [IRInstr('dsub', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x2F:  # DSUBU
            return [IRInstr('dsubu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])]
        elif funct == 0x00:  # SLL
            return [IRInstr('sll', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])]
        elif funct == 0x02:  # SRL
            return [IRInstr('srl', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])]
        elif funct == 0x03:  # SRA
            return [IRInstr('sra', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])]
        elif funct == 0x10:  # MFHI
            rd_vreg = rv(rd)
            return [IRInstr('mfhi', vaddr, file_off, mnemonic,
                           defs=[rd_vreg] if rd_vreg else []])
        elif funct == 0x12:  # MFLO
            return [IRInstr('mflo', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else []])

    elif op == 0x04:  # BEQ
        return [IRInstr('beq', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))]
    elif op == 0x05:  # BNE
        return [IRInstr('bne', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))]
    elif op == 0x06:  # BLEZ
        return [IRInstr('blez', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))]
    elif op == 0x07:  # BGTZ
        return [IRInstr('bgtz', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))]
    elif op == 0x08:  # ADDI
        return [IRInstr('addi', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])]
    elif op == 0x09:  # ADDIU
        return [IRInstr('addiu', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])]
    elif op == 0x0A:  # SLTI
        return [IRInstr('slti', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])]
    elif op == 0x0B:  # SLTIU
        return [IRInstr('sltiu', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])]
    elif op == 0x0C:  # ANDI
        return [IRInstr('andi', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])]
    elif op == 0x0D:  # ORI
        return [IRInstr('ori', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])]
    elif op == 0x0E:  # XORI
        return [IRInstr('xori', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])]
    elif op == 0x0F:  # LUI
        return [IRInstr('lui', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('imm', imm << 16)])]
    elif op == 0x23:  # LW
        return [IRInstr('lw', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('mem', (rs, imm_signed))])]
    elif op == 0x2B:  # SW
        return [IRInstr('sw', vaddr, file_off, mnemonic,
                       uses=[rv(rt) if rv(rt) else None, IRValue('mem', (rs, imm_signed))])]
    elif op == 0x31:  # LWC1
        return [IRInstr('lwc1', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('mem', (rs, imm_signed))])]
    elif op == 0x39:  # SWC1
        return [IRInstr('swc1', vaddr, file_off, mnemonic,
                       uses=[rv(rt) if rv(rt) else None, IRValue('mem', (rs, imm_signed))])]

    # J-type
    elif op == 0x02:  # J
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        return [IRInstr('j', vaddr, file_off, mnemonic, branch_target=target)]
    elif op == 0x03:  # JAL
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        return [IRInstr('jal', vaddr, file_off, mnemonic,
                       defs=[rv(31)] if rv(31) else [],
                       branch_target=target)]

    # COP1
    elif op == 0x11:
        rs_cop1 = (word >> 21) & 0x1F
        if rs_cop1 == 0x00:  # MFC1
            return [IRInstr('mfc1', vaddr, file_off, mnemonic,
                           defs=[rv(rt)] if rv(rt) else [],
                           uses=[rv(fs) if rv(fs) else None])]
        elif rs_cop1 == 0x04:  # MTC1
            return [IRInstr('mtc1', vaddr, file_off, mnemonic,
                           uses=[rv(rt) if rv(rt) else None, rv(fs) if rv(fs) else None])]
        elif rs_cop1 == 0x10:  # COP1_S
            funct = word & 0x3F
            fs = (word >> 11) & 0x1F
            fd = (word >> 6) & 0x1F
            ft = rt
            if funct == 0x00:  # ADD.S
                return [IRInstr('add.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None, rv(ft) if rv(ft) else None])]
            elif funct == 0x01:  # SUB.S
                return [IRInstr('sub.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None, rv(ft) if rv(ft) else None])]
            elif funct == 0x02:  # MUL.S
                return [IRInstr('mul.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None, rv(ft) if rv(ft) else None])]
            elif funct == 0x03:  # DIV.S
                return [IRInstr('div.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None, rv(ft) if rv(ft) else None])]
            elif funct == 0x05:  # ABS.S
                return [IRInstr('abs.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None])]
            elif funct == 0x06:  # MOV.S
                return [IRInstr('mov.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None])]
            elif funct == 0x07:  # NEG.S
                return [IRInstr('neg.s', vaddr, file_off, mnemonic,
                               defs=[rv(fd)] if rv(fd) else [],
                               uses=[rv(fs) if rv(fs) else None])]

    # COP2 (VU0 vector)
    elif op == 0x12:
        if (word >> 25) == 0x25:  # COP2 vector
            if (word & 0x3C) == 0x3C:
                opcode = word & 0x7FF
            else:
                opcode = word & 0x3F
            return [IRInstr('cop2_vec', vaddr, file_off, f'cop2_vec opcode=0x{opcode:03X}')]
        else:
            return [IRInstr('cop2', vaddr, file_off, f'cop2 rs={rs}')]

    return None


def reg_name(n):
    """Return MIPS register name for register number n."""
    if 0 <= n < 32:
        return MIPS_REGS[n]
    return f'r{n}'


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mips_disasm.py <hex_word>")
        sys.exit(1)
    word = int(sys.argv[1], 16)
    result = decode_instruction(word, 0x100000)
    if result:
        for info in result:
            print(f"{info.vaddr:08X}: {info.mnemonic}")
        else:
            print(f"0x{vaddr:08X}: unk_op 0x{word:08X}")
