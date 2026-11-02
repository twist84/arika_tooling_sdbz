#!/usr/bin/env python3
"""
ELF tooling: MIPS R5900 to IR (Intermediate Representation) lifter.

Lifts MIPS instructions into a structured IR with explicit:
- Virtual register numbering (t0, t1, ...) mapped from physical registers
- Def/use chains for SSA construction
- Side effects (memory loads/stores, register writes)
- Branch conditions
- Memory access annotations

This is the foundation for decompilation: IR → SSA → CFG structuring → C emission.

Usage:
    python elf_ir_lifter.py [elf] [start_vaddr] [end_vaddr]

Defaults:
    elf    = source_data/SLUS_214.42
    start  = 0x0018C518 (main loop)
    end    = start + 0x400
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


CODE_START = 0x80
CODE_END = 0x400700

# MIPS register names
MIPS_REGS = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']


def reg_name(n):
    return MIPS_REGS[n] if 0 <= n < 32 else f'${n}'


class IRValue:
    """An IR value: either a virtual register, a constant, or memory."""
    def __init__(self, kind, value):
        self.kind = kind   # 'vreg', 'imm', 'mem', 'label'
        self.value = value # int for imm/vreg, str for label, tuple for mem (base, offset)

    def __repr__(self):
        if self.kind == 'vreg':
            return f't{self.value}'
        if self.kind == 'imm':
            return f'0x{self.value:08X}'
        if self.kind == 'mem':
            base, off = self.value
            return f'mem[{reg_name(base)}+0x{off:04X}]'
        if self.kind == 'label':
            return self.value
        return f'?{self.value}?'

    def is_reg(self):
        return self.kind == 'vreg'

    def is_imm(self):
        return self.kind == 'imm'


class IRInstr:
    """An IR instruction with explicit defs and uses."""
    def __init__(self, opcode, vaddr, file_off, mnemonic, defs=None, uses=None, branch_target=None):
        self.opcode = opcode        # IR opcode (add, lw, sw, beq, jalr, etc.)
        self.vaddr = vaddr
        self.file_off = file_off
        self.mnemonic = mnemonic    # Original MIPS mnemonic
        self.defs = defs or []      # List of IRValue (registers defined)
        self.uses = uses or []      # List of IRValue (registers/memory used)
        self.branch_target = branch_target  # vaddr if this is a branch/jump

    def __repr__(self):
        defs_str = ', '.join(str(d) for d in self.defs)
        uses_str = ', '.join(str(u) for u in self.uses)
        target = f' -> {self.branch_target:08X}' if self.branch_target else ''
        return f'{self.opcode} {defs_str} := {uses_str}{target}'


class IRFunction:
    """A lifted IR function."""
    def __init__(self, start_vaddr, end_vaddr):
        self.start_vaddr = start_vaddr
        self.end_vaddr = end_vaddr
        self.instructions = []  # List of IRInstr
        self.next_vreg = 0      # Next virtual register number
        self.reg_map = {}       # physical reg number -> vreg number

    def new_vreg(self):
        self.next_vreg += 1
        return self.next_vreg - 1

    def get_vreg(self, n):
        """Map physical register to virtual register.
        $zero (n==0) returns None (treated as constant 0).
        Same physical register always returns the same vreg.
        """
        if n == 0:
            return None  # $zero is constant 0
        if n not in self.reg_map:
            self.reg_map[n] = self.new_vreg()
        return self.reg_map[n]

    def add_instr(self, opcode, vaddr, file_off, mnemonic, defs=None, uses=None, branch_target=None):
        # Filter out None vregs (from $zero, which is constant 0)
        defs = [d for d in (defs or []) if d is not None]
        uses = [u for u in (uses or []) if u is not None]
        instr = IRInstr(opcode, vaddr, file_off, mnemonic, defs, uses, branch_target)
        self.instructions.append(instr)
        return instr

    def __repr__(self):
        lines = [f'; IR function @ 0x{self.start_vaddr:08X}-0x{self.end_vaddr:08X}']
        for i, instr in enumerate(self.instructions):
            lines.append(f'  {i:3d}: {instr}')
        return '\n'.join(lines)


def rv(ir, n):
    """Get an IRValue for physical register n, or None if $zero (constant 0)."""
    v = ir.get_vreg(n)
    return IRValue('vreg', v) if v is not None else None


def lift_instruction(word, vaddr, file_off, ir):
    """
    Lift a single MIPS instruction into one or more IR instructions.
    Returns the IRInstr(s) created.
    """
    info = decode_instruction(word, vaddr)
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    instrs = []

    # R-type instructions
    if op == 0x00:
        if funct == 0x00 and rs == 0 and rt == 0 and rd == 0 and sa == 0:
            # SLL zero, zero, 0 - NOP
            instrs.append(IRInstr('nop', vaddr, file_off, 'nop'))
        elif funct == 0x08:  # JR
            instrs.append(IRInstr('jr', vaddr, file_off, 'jr',
                                  uses=[rv(ir, rs)]))
        elif funct == 0x09:  # JALR
            instrs.append(IRInstr('jalr', vaddr, file_off, 'jalr',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs)]))
        elif funct == 0x0C:  # SYSCALL
            instrs.append(IRInstr('syscall', vaddr, file_off, 'syscall'))
        elif funct == 0x0D:  # BREAK
            instrs.append(IRInstr('break', vaddr, file_off, 'break'))
        elif funct == 0x20:  # ADD
            instrs.append(IRInstr('add', vaddr, file_off, 'add',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x21:  # ADDU
            instrs.append(IRInstr('addu', vaddr, file_off, 'addu',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x22:  # SUB
            instrs.append(IRInstr('sub', vaddr, file_off, 'sub',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x23:  # SUBU
            instrs.append(IRInstr('subu', vaddr, file_off, 'subu',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x24:  # AND
            instrs.append(IRInstr('and', vaddr, file_off, 'and',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x25:  # OR
            instrs.append(IRInstr('or', vaddr, file_off, 'or',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x26:  # XOR
            instrs.append(IRInstr('xor', vaddr, file_off, 'xor',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x27:  # NOR
            instrs.append(IRInstr('nor', vaddr, file_off, 'nor',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2A:  # SLT
            instrs.append(IRInstr('slt', vaddr, file_off, 'slt',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2B:  # SLTU
            instrs.append(IRInstr('sltu', vaddr, file_off, 'sltu',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2C:  # DADD
            instrs.append(IRInstr('dadd', vaddr, file_off, 'dadd',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2D:  # DADDU
            instrs.append(IRInstr('daddu', vaddr, file_off, 'daddu',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2E:  # DSUB
            instrs.append(IRInstr('dsub', vaddr, file_off, 'dsub',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x2F:  # DSUBU
            instrs.append(IRInstr('dsubu', vaddr, file_off, 'dsubu',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x00:  # SLL
            instrs.append(IRInstr('sll', vaddr, file_off, 'sll',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rt), IRValue('imm', sa)]))
        elif funct == 0x02:  # SRL
            instrs.append(IRInstr('srl', vaddr, file_off, 'srl',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rt), IRValue('imm', sa)]))
        elif funct == 0x03:  # SRA
            instrs.append(IRInstr('sra', vaddr, file_off, 'sra',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rt), IRValue('imm', sa)]))
        elif funct == 0x18:  # MULT
            instrs.append(IRInstr('mult', vaddr, file_off, 'mult',
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x19:  # MULTU
            instrs.append(IRInstr('multu', vaddr, file_off, 'multu',
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x1A:  # DIV
            instrs.append(IRInstr('div', vaddr, file_off, 'div',
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x1B:  # DIVU
            instrs.append(IRInstr('divu', vaddr, file_off, 'divu',
                                  uses=[rv(ir, rs), rv(ir, rt)]))
        elif funct == 0x10:  # MFHI
            instrs.append(IRInstr('mfhi', vaddr, file_off, 'mfhi',
                                  defs=[rv(ir, rd)]))
        elif funct == 0x12:  # MFLO
            instrs.append(IRInstr('mflo', vaddr, file_off, 'mflo',
                                  defs=[rv(ir, rd)]))
        elif funct == 0x11:  # MTHI
            instrs.append(IRInstr('mthi', vaddr, file_off, 'mthi',
                                  uses=[rv(ir, rs)]))
        elif funct == 0x13:  # MTLO
            instrs.append(IRInstr('mtlo', vaddr, file_off, 'mtlo',
                                  uses=[rv(ir, rs)]))
        else:
            instrs.append(IRInstr('unk_rtype', vaddr, file_off, f'funct=0x{funct:02X}'))

    # I-type instructions
    elif op == 0x01:  # REGIMM (branch on condition)
        rt_name = MIPS_REGS[rt]
        if rt == 0x00:  # BLTZ
            instrs.append(IRInstr('bltz', vaddr, file_off, 'bltz',
                                  uses=[rv(ir, rs)],
                                  branch_target=vaddr + 4 + (imm_signed << 2)))
        elif rt == 0x01:  # BGEZ
            instrs.append(IRInstr('bgez', vaddr, file_off, 'bgez',
                                  uses=[rv(ir, rs)],
                                  branch_target=vaddr + 4 + (imm_signed << 2)))
        elif rt == 0x10:  # BLTZAL
            instrs.append(IRInstr('bltzal', vaddr, file_off, 'bltzal',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs)],
                                  branch_target=vaddr + 4 + (imm_signed << 2)))
        elif rt == 0x11:  # BGEZAL
            instrs.append(IRInstr('bgezal', vaddr, file_off, 'bgezal',
                                  defs=[rv(ir, rd)],
                                  uses=[rv(ir, rs)],
                                  branch_target=vaddr + 4 + (imm_signed << 2)))
        elif rt == 0x08:  # TGEI
            instrs.append(IRInstr('tgei', vaddr, file_off, 'tgei',
                                  uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
        elif rt == 0x0A:  # TLTI
            instrs.append(IRInstr('tlti', vaddr, file_off, 'tlti',
                                  uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
        elif rt == 0x0C:  # TEQI
            instrs.append(IRInstr('teqi', vaddr, file_off, 'teqi',
                                  uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
        elif rt == 0x0E:  # TNEI
            instrs.append(IRInstr('tnei', vaddr, file_off, 'tnei',
                                  uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
        else:
            instrs.append(IRInstr('unk_regimm', vaddr, file_off, f'rt=0x{rt:02X}'))

    elif op == 0x04:  # BEQ
        instrs.append(IRInstr('beq', vaddr, file_off, 'beq',
                              uses=[rv(ir, rs), rv(ir, rt)],
                              branch_target=vaddr + 4 + (imm_signed << 2)))
    elif op == 0x05:  # BNE
        instrs.append(IRInstr('bne', vaddr, file_off, 'bne',
                              uses=[rv(ir, rs), rv(ir, rt)],
                              branch_target=vaddr + 4 + (imm_signed << 2)))
    elif op == 0x06:  # BLEZ
        instrs.append(IRInstr('blez', vaddr, file_off, 'blez',
                              uses=[rv(ir, rs)],
                              branch_target=vaddr + 4 + (imm_signed << 2)))
    elif op == 0x07:  # BGTZ
        instrs.append(IRInstr('bgtz', vaddr, file_off, 'bgtz',
                              uses=[rv(ir, rs)],
                              branch_target=vaddr + 4 + (imm_signed << 2)))
    elif op == 0x08:  # ADDI
        instrs.append(IRInstr('addi', vaddr, file_off, 'addi',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
    elif op == 0x09:  # ADDIU
        instrs.append(IRInstr('addiu', vaddr, file_off, 'addiu',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
    elif op == 0x0A:  # SLTI
        instrs.append(IRInstr('slti', vaddr, file_off, 'slti',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
    elif op == 0x0B:  # SLTIU
        instrs.append(IRInstr('sltiu', vaddr, file_off, 'sltiu',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm_signed)]))
    elif op == 0x0C:  # ANDI
        instrs.append(IRInstr('andi', vaddr, file_off, 'andi',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm)]))
    elif op == 0x0D:  # ORI
        instrs.append(IRInstr('ori', vaddr, file_off, 'ori',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm)]))
    elif op == 0x0E:  # XORI
        instrs.append(IRInstr('xori', vaddr, file_off, 'xori',
                              defs=[rv(ir, rt)],
                              uses=[rv(ir, rs), IRValue('imm', imm)]))
    elif op == 0x0F:  # LUI
        instrs.append(IRInstr('lui', vaddr, file_off, 'lui',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('imm', imm << 16)]))
    elif op == 0x20:  # LB
        instrs.append(IRInstr('lb', vaddr, file_off, 'lb',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x21:  # LH
        instrs.append(IRInstr('lh', vaddr, file_off, 'lh',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x22:  # LWL
        instrs.append(IRInstr('lwl', vaddr, file_off, 'lwl',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x23:  # LW
        instrs.append(IRInstr('lw', vaddr, file_off, 'lw',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x24:  # LBU
        instrs.append(IRInstr('lbu', vaddr, file_off, 'lbu',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x25:  # LHU
        instrs.append(IRInstr('lhu', vaddr, file_off, 'lhu',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x26:  # LWR
        instrs.append(IRInstr('lwr', vaddr, file_off, 'lwr',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x27:  # LWU
        instrs.append(IRInstr('lwu', vaddr, file_off, 'lwu',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x28:  # SB
        instrs.append(IRInstr('sb', vaddr, file_off, 'sb',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))
    elif op == 0x29:  # SH
        instrs.append(IRInstr('sh', vaddr, file_off, 'sh',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))
    elif op == 0x2A:  # SWL
        instrs.append(IRInstr('swl', vaddr, file_off, 'swl',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))
    elif op == 0x2B:  # SW
        instrs.append(IRInstr('sw', vaddr, file_off, 'sw',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))
    elif op == 0x2E:  # SWR
        instrs.append(IRInstr('swr', vaddr, file_off, 'swr',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))
    elif op == 0x31:  # LWC1
        instrs.append(IRInstr('lwc1', vaddr, file_off, 'lwc1',
                              defs=[rv(ir, rt)],
                              uses=[IRValue('mem', (rs, imm_signed))]))
    elif op == 0x39:  # SWC1
        instrs.append(IRInstr('swc1', vaddr, file_off, 'swc1',
                              uses=[rv(ir, rt), IRValue('mem', (rs, imm_signed))]))

    # J-type instructions
    elif op == 0x02:  # J
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        instrs.append(IRInstr('j', vaddr, file_off, 'j',
                              branch_target=target))
    elif op == 0x03:  # JAL
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        instrs.append(IRInstr('jal', vaddr, file_off, 'jal',
                              defs=[rv(ir, 31)],  # $ra
                              branch_target=target))

    # COP1 (FPU)
    elif op == 0x11:
        cop1_op = (word >> 21) & 0x1F
        if cop1_op == 0x00:  # MFC1
            instrs.append(IRInstr('mfc1', vaddr, file_off, 'mfc1',
                                  defs=[rv(ir, rt)],
                                  uses=[rv(ir, fs)]))
        elif cop1_op == 0x04:  # MTC1
            instrs.append(IRInstr('mtc1', vaddr, file_off, 'mtc1',
                                  uses=[rv(ir, rt), rv(ir, fs)]))
        elif cop1_op == 0x06:  # CTC1
            instrs.append(IRInstr('ctc1', vaddr, file_off, 'ctc1',
                                  uses=[rv(ir, rt), rv(ir, fs)]))
        elif cop1_op == 0x10:  # COP1_S
            funct = word & 0x3F
            fs = (word >> 11) & 0x1F
            fd = (word >> 6) & 0x1F
            ft = rt
            if funct == 0x00:  # ADD.S
                instrs.append(IRInstr('add.s', vaddr, file_off, 'add.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs), rv(ir, ft)]))
            elif funct == 0x01:  # SUB.S
                instrs.append(IRInstr('sub.s', vaddr, file_off, 'sub.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs), rv(ir, ft)]))
            elif funct == 0x02:  # MUL.S
                instrs.append(IRInstr('mul.s', vaddr, file_off, 'mul.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs), rv(ir, ft)]))
            elif funct == 0x03:  # DIV.S
                instrs.append(IRInstr('div.s', vaddr, file_off, 'div.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs), rv(ir, ft)]))
            elif funct == 0x05:  # ABS.S
                instrs.append(IRInstr('abs.s', vaddr, file_off, 'abs.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs)]))
            elif funct == 0x06:  # MOV.S
                instrs.append(IRInstr('mov.s', vaddr, file_off, 'mov.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs)]))
            elif funct == 0x07:  # NEG.S
                instrs.append(IRInstr('neg.s', vaddr, file_off, 'neg.s',
                                      defs=[rv(ir, fd)],
                                      uses=[rv(ir, fs)]))
            else:
                instrs.append(IRInstr('unk_cop1_s', vaddr, file_off, f'cop1.s funct=0x{funct:02X}'))
        else:
            instrs.append(IRInstr('unk_cop1', vaddr, file_off, f'cop1 rs=0x{cop1_op:02X}'))

    # COP2 (VU0 vector)
    elif op == 0x12:
        if (word >> 25) == 0x25:  # COP2 vector
            if (word & 0x3C) == 0x3C:
                opcode = word & 0x7FF
            else:
                opcode = word & 0x3F
            instrs.append(IRInstr('cop2_vec', vaddr, file_off, f'cop2_vec opcode=0x{opcode:03X}'))
        else:
            instrs.append(IRInstr('cop2', vaddr, file_off, f'cop2 rs={rs}'))

    # Unknown
    else:
        instrs.append(IRInstr('unknown', vaddr, file_off, f'op=0x{op:02X}'))

    return instrs


def lift_elf(data, start_vaddr, end_vaddr):
    """Lift a range of the ELF into IR instructions."""
    start_off = vaddr_to_file(start_vaddr)
    end_off = min(len(data) - 4, vaddr_to_file(end_vaddr))

    ir = IRFunction(start_vaddr, end_vaddr)

    off = start_off
    while off < end_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)

        ir_instrs = lift_instruction(word, vaddr, off, ir)
        for instr in ir_instrs:
            ir.add_instr(instr.opcode, instr.vaddr, instr.file_off,
                         instr.mnemonic, instr.defs, instr.uses,
                         instr.branch_target)

        off += 4

    return ir


def write_ir(ir, output_path=None):
    """Print IR to stdout or write to file."""
    lines = [str(ir)]
    output = '\n'.join(lines)
    if output_path:
        Path(output_path).write_text(output + '\n')
        print(f"Wrote IR to {output_path}")
    else:
        print(output)


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0018C518
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else start_vaddr + 0x400
    output_path = sys.argv[4] if len(sys.argv) > 4 else None

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF MIPS-to-IR LIFTER")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print(f"Output: {output_path or 'stdout'}")
    print()

    ir = lift_elf(data, start_vaddr, end_vaddr)
    write_ir(ir, output_path)


if __name__ == '__main__':
    main()
