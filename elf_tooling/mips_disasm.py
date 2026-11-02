#!/usr/bin/env python3
"""Improved MIPS R5900 disassembler with branch target resolution and basic block tracing."""
import struct
import sys
from pathlib import Path


# MIPS opcodes (6-bit)  -- per PCSX2 tbl_Standard
OPCODES = {
    0x00: 'SPECIAL', 0x01: 'REGIMM', 0x02: 'J', 0x03: 'JAL',
    0x04: 'BEQ', 0x05: 'BNE', 0x06: 'BLEZ', 0x07: 'BGTZ',
    0x08: 'ADDI', 0x09: 'ADDIU', 0x0A: 'SLTI', 0x0B: 'SLTIU',
    0x0C: 'ANDI', 0x0D: 'ORI', 0x0E: 'XORI', 0x0F: 'LUI',
    0x10: 'COP0', 0x11: 'COP1', 0x12: 'COP2', 0x13: 'Unknown',
    0x14: 'BEQL', 0x15: 'BNEL', 0x16: 'BLEZL', 0x17: 'BGTZL',
    0x18: 'DADDI', 0x19: 'DADDIU', 0x1A: 'LDL', 0x1B: 'LDR',
    0x1C: 'MMI', 0x1D: 'Unknown', 0x1E: 'LQ', 0x1F: 'SQ',
    0x20: 'LB', 0x21: 'LH', 0x22: 'LWL', 0x23: 'LW',
    0x24: 'LBU', 0x25: 'LHU', 0x26: 'LWR', 0x27: 'LWU',
    0x27: 'LWU',
    0x28: 'SB', 0x29: 'SH', 0x2A: 'SWL', 0x2B: 'SW',
    0x2C: 'SDL', 0x2D: 'SDR', 0x2E: 'SWR', 0x2F: 'CACHE',
    0x30: 'Unknown', 0x31: 'LWC1', 0x32: 'Unknown', 0x33: 'PREF',
    0x34: 'Unknown', 0x35: 'Unknown', 0x36: 'LQC2', 0x37: 'LD',
    0x38: 'Unknown', 0x39: 'SWC1', 0x3A: 'Unknown', 0x3B: 'Unknown',
    0x3C: 'Unknown', 0x3D: 'Unknown', 0x3E: 'SQC2', 0x3F: 'SD',
}

# R-type funct codes (per PCSX2 tbl_Special)
FUNCTS = {
    0x00: 'SLL', 0x01: 'unk_funct_0x01', 0x02: 'SRL', 0x03: 'SRA',
    0x04: 'SLLV', 0x05: 'unk_funct_0x05', 0x06: 'SRLV', 0x07: 'SRAV',
    0x08: 'JR', 0x09: 'JALR', 0x0A: 'MOVZ', 0x0B: 'MOVN',
    0x0C: 'SYSCALL', 0x0D: 'BREAK', 0x0E: 'unk_funct_0x0E', 0x0F: 'SYNC',
    0x10: 'MFHI', 0x11: 'MTHI', 0x12: 'MFLO', 0x13: 'MTLO',
    0x14: 'DSLLV', 0x15: 'unk_funct_0x15', 0x16: 'DSRLV', 0x17: 'DSRAV',
    0x18: 'MULT', 0x19: 'MULTU', 0x1A: 'DIV', 0x1B: 'DIVU',
    0x1C: 'unk_funct_0x1C', 0x1D: 'unk_funct_0x1D', 0x1E: 'unk_funct_0x1E', 0x1F: 'unk_funct_0x1F',
    0x20: 'ADD', 0x21: 'ADDU', 0x22: 'SUB', 0x23: 'SUBU',
    0x24: 'AND', 0x25: 'OR', 0x26: 'XOR', 0x27: 'NOR',
    0x28: 'MFSA', 0x29: 'MTSA', 0x2A: 'SLT', 0x2B: 'SLTU',
    0x2C: 'DADD', 0x2D: 'DADDU', 0x2E: 'DSUB', 0x2F: 'DSUBU',
    0x30: 'TGE', 0x31: 'TGEU', 0x32: 'TLT', 0x33: 'TLTU',
    0x34: 'TEQ', 0x35: 'unk_funct_0x35', 0x36: 'TNE', 0x37: 'unk_funct_0x37',
    0x38: 'DSLL', 0x39: 'unk_funct_0x39', 0x3A: 'DSRL', 0x3B: 'DSRA',
    0x3C: 'DSLL32', 0x3D: 'unk_funct_0x3D', 0x3E: 'DSRL32', 0x3F: 'DSRA32',
}

# REGIMM branch condition codes (rt field for op=0x01)
REGIMM = {0x00: 'BLTZ', 0x01: 'BGEZ', 0x02: 'BLTZL', 0x03: 'BGEZL',
          0x04: 'unk_regimm_0x04', 0x05: 'unk_regimm_0x05', 0x06: 'unk_regimm_0x06', 0x07: 'unk_regimm_0x07',
          0x08: 'TGEI', 0x09: 'TGEIU', 0x0A: 'TLTI', 0x0B: 'TLTIU',
          0x0C: 'TEQI', 0x0D: 'unk_regimm_0x0D', 0x0E: 'TNEI', 0x0F: 'unk_regimm_0x0F',
          0x10: 'BLTZAL', 0x11: 'BGEZAL', 0x12: 'BLTZALL', 0x13: 'BGEZALL',
          0x14: 'unk_regimm_0x14', 0x15: 'unk_regimm_0x15', 0x16: 'unk_regimm_0x16', 0x17: 'unk_regimm_0x17',
          0x18: 'MTSAB', 0x19: 'MTSAH', 0x1A: 'unk_regimm_0x1A', 0x1B: 'unk_regimm_0x1B',
          0x1C: 'unk_regimm_0x1C', 0x1D: 'unk_regimm_0x1D', 0x1E: 'unk_regimm_0x1E', 0x1F: 'unk_regimm_0x1F'}

# PS2 EE COP1 (FPU) subclass tables, per PCSX2 tbl_COP1 / tbl_COP1_S / tbl_COP1_W / tbl_COP1_BC1
# tbl_COP1 indexed by rs (bits 25-21)
COP1_TABLE = {
    0x00: 'MFC1', 0x02: 'CFC1', 0x04: 'MTC1', 0x06: 'CTC1',
    0x08: 'COP1_BC1',
    0x10: 'COP1_S',
    0x14: 'COP1_W',
}

# tbl_COP1_S indexed by funct (bits 5-0)
COP1_S_TABLE = {
    0x00: 'ADD.S', 0x01: 'SUB.S', 0x02: 'MUL.S', 0x03: 'DIV.S',
    0x04: 'SQRT.S', 0x05: 'ABS.S', 0x06: 'MOV.S', 0x07: 'NEG.S',
    0x16: 'RSQRT.S',
    0x18: 'ADDA.S', 0x19: 'SUBA.S', 0x1A: 'MULA.S',
    0x1C: 'MADD.S', 0x1D: 'MSUB.S', 0x1E: 'MADDA.S', 0x1F: 'MSUBA.S',
    0x24: 'CVT.W.S',
    0x28: 'MAX.S', 0x29: 'MIN.S',
    0x30: 'C.F', 0x32: 'C.EQ.S', 0x34: 'C.LT.S', 0x36: 'C.LE.S',
}

# tbl_COP1_W indexed by funct (bits 5-0)
COP1_W_TABLE = {
    0x20: 'CVT.S.W',
}

# tbl_COP1_BC1 indexed by rt (bits 20-16)
COP1_BC1_TABLE = {
    0x00: 'BC1F', 0x01: 'BC1T', 0x02: 'BC1FL', 0x03: 'BC1TL',
}

# COP1 branch condition names for C.xx.S cond field (funct bits 3-2 pattern)
COP1_CC = {0x00: 'F', 0x01: 'UN', 0x02: 'EQ', 0x03: 'UEQ',
           0x04: 'OLT', 0x05: 'ULT', 0x06: 'OLE', 0x07: 'ULE',
           0x08: 'SF', 0x09: 'NGLE', 0x0A: 'SEQ', 0x0B: 'NGL',
           0x0C: 'LT', 0x0D: 'NGE', 0x0E: 'LE', 0x0F: 'NGT'}

# PS2 EE COP2 (VU0) vector instruction table.
# opcode -> (mnemonic, dt)  dt = register-decode template id:
#   0 none            (vnop)
#   1 ft, fs          (vadd $vf0,$vf1)
#   2 fd, fs, ft      (vadd $vf0,$vf1,$vf2.xyzw)
#   3 fd, fs, $i      (vaddi $vf0,$vf1,$i)
#   4 fd, fs, $q      (vaddq $vf0,$vf1,$q)
#   5 $acc, fs, ft    (vadda $acc,$vf1,$vf2.xyzw)
#   6 $acc, fs, $i
#   7 $acc, fs, $q
#   8 $acc, fs, ft
#   9 $acc, fs, ft    (vopmula)
#   10 fd, fs, ft     (vopmsub)
#   11 fs, ft         (vclip $vf1,$vf0)
#   12 $q, fs.c, ft.c (vdiv $q,$vf1.x,$vf0.x)
#   13 $q, fs.c       (vsqrt $q,$vf1.x)
#   14 vi, vi, vi     (viadd $vi0,$vi1,$vi2)
#   15 vi, vi, imm    (viaddi $vi0,$vi1,imm)
#   16 ft, fs         (vmove $vf0,$vf1)
#   17 ft, fs         (vmfir $vf0,$vi1)
#   18 ft, fs.c       (vmtir $vi0,$vf1.x)
#   19 ft, fs         (vlqd $vf0,$vi1)
#   20 vi, vi         (vilwr $vi0,$vi1)
#   21 ft, $c         (vrget $vf0,$c)
#   22 ft, $c         (vrnext $vf0,$c)
COP2_TABLE = {
    0x000: ('vaddx',    2), 0x001: ('vaddy',    2), 0x002: ('vaddz',    2), 0x003: ('vaddw',    2),
    0x004: ('vsubx',    2), 0x005: ('vsuby',    2), 0x006: ('vsubz',    2), 0x007: ('vsubw',    2),
    0x008: ('vmaddx',   2), 0x009: ('vmaddy',   2), 0x00A: ('vmaddz',   2), 0x00B: ('vmaddw',   2),
    0x00C: ('vmsubx',   2), 0x00D: ('vmsuby',   2), 0x00E: ('vmsubz',   2), 0x00F: ('vmsubw',   2),
    0x010: ('vmaxx',    2), 0x011: ('vmaxy',    2), 0x012: ('vmaxz',    2), 0x013: ('vmaxw',    2),
    0x014: ('vminix',   2), 0x015: ('vminiy',   2), 0x016: ('vminiz',   2), 0x017: ('vminiw',   2),
    0x018: ('vmulx',    2), 0x019: ('vmuly',    2), 0x01A: ('vmulz',    2), 0x01B: ('vmulw',    2),
    0x01D: ('vmaxi',    3), 0x01E: ('vmuli',    3), 0x01F: ('vminii',   3),
    0x020: ('vaddq',    4), 0x021: ('vmaddq',   4), 0x022: ('vaddi',    3), 0x023: ('vmaddi',   3),
    0x024: ('vsubq',    4), 0x025: ('vmsubq',   4), 0x026: ('vsubi',    3), 0x027: ('vmsubi',   3),
    0x028: ('vadd',     1), 0x029: ('vmadd',    1), 0x02A: ('vmul',     1), 0x02B: ('vmax',     1),
    0x02C: ('vsub',     1), 0x02D: ('vmsub',    1), 0x02E: ('vopmsub', 10), 0x02F: ('vmini',    1),
    0x030: ('viadd',   14), 0x031: ('visub',   14), 0x032: ('viaddi',  15), 0x034: ('viand',   14),
    0x035: ('vior',    14), 0x03C: ('vaddax',   2), 0x03D: ('vadday',   2), 0x03E: ('vaddaz',   2),
    0x03F: ('vaddaw',   2), 0x07C: ('vsubax',   2), 0x07D: ('vsubay',   2), 0x07E: ('vsubaz',   2),
    0x07F: ('vsubaw',   2), 0x0BC: ('vmaddax',  2), 0x0BD: ('vmadday',  2), 0x0BE: ('vmaddaz',  2),
    0x0BF: ('vmaddaw',  2), 0x0FC: ('vmsubax',  2), 0x0FD: ('vmsubay',  2), 0x0FE: ('vmsubaz',  2),
    0x0FF: ('vmsubaw',  2), 0x15C: ('vaddaw',   2), 0x1BC: ('vmulax',   2), 0x1BD: ('vmulay',   2),
    0x1BE: ('vmulaz',   2), 0x1BF: ('vmulaw',   2), 0x1FE: ('vmulai',   3), 0x1FC: ('vmulaq',   4),
    0x1FD: ('vabs',     1), 0x1FF: ('vclip',   11), 0x23C: ('vaddaq',   4), 0x23D: ('vmaddaq',  4),
    0x23E: ('vaddai',   3), 0x23F: ('vmaddai',  3), 0x27C: ('vsubaq',   4), 0x27D: ('vmsubaq',  4),
    0x27E: ('vsubai',   3), 0x27F: ('vmsubai',  3), 0x2BD: ('vmadda',   5), 0x2BE: ('vmula',    5),
    0x2BC: ('vadda',    5), 0x2BD: ('vmadda',   5), 0x2FD: ('vmsuba',   5), 0x2FE: ('vopmula',  9),
    0x2FF: ('vnop',     0), 0x33C: ('vmove',   16), 0x33D: ('vmr32',   16), 0x37C: ('vlqi',    19),
    0x37E: ('vlqd',    19), 0x37D: ('vsqi',    19), 0x37F: ('vsqd',    19), 0x3BC: ('vdiv',    12),
    0x3BD: ('vsqrt',   13), 0x3BE: ('vrsqrt', 12), 0x3BF: ('vwaitq',   0), 0x3FC: ('vmtir',   18),
    0x3FD: ('vmfir',   17), 0x3FE: ('vilwr',  20), 0x3FF: ('viswr',  20), 0x43C: ('vrnext',  22),
    0x43D: ('vrget',   21), 0x43E: ('vrinit',  0), 0x43F: ('vrxor',    0),
    # Additional COP2 opcodes observed in SLUS_214.42
    0x01C: ('vitof0', 17), 0x11C: ('vitof4', 17), 0x21C: ('vitof12', 17), 0x31C: ('vitof15', 17),
    0x033: ('cop2_unk_0x033', 0), 0x039: ('cop2_unk_0x039', 0), 0x03A: ('cop2_unk_0x03a', 0),
    0x03B: ('cop2_unk_0x03b', 0), 0x13D: ('cop2_unk_0x13d', 0), 0x17D: ('cop2_unk_0x17d', 0),
}


def cop2_dest_suffix(word):
    """Return .xyzw suffix from COP2 destination field (bits 21-24)."""
    dest = (word >> 21) & 0xF
    s = ''
    if dest & 0x8: s += 'x'
    if dest & 0x4: s += 'y'
    if dest & 0x2: s += 'z'
    if dest & 0x1: s += 'w'
    return s


def cop2_reg(word, kind, n):
    """Return COP2 register operand string."""
    if kind == 'vf':
        return f'$vf{n}'
    if kind == 'vi':
        return f'$vi{n}'
    if kind == 'acc':
        return '$acc'
    if kind == 'i':
        return '$i'
    if kind == 'q':
        return '$q'
    if kind == 'ctl':
        return f'${chr(ord("x") + n)}' if n < 4 else f'${n}'
    return f'${n}'


def decode_cop2(word, vaddr=None):
    """Decode a PS2 EE COP2 (VU0) vector instruction."""
    # Plugin detection: top 7 bits == 0x25  => COP2 vector instruction
    if (word >> 25) != 0x25:
        return None
    if (word & 0x3C) == 0x3C:
        opcode = word & 0x7FF
    else:
        opcode = word & 0x3F
    entry = COP2_TABLE.get(opcode)
    if entry is None:
        return f'cop2 0x{opcode:03X}'
    name, dt = entry
    ft = (word >> 16) & 0x1F
    fs = (word >> 11) & 0x1F
    fd = (word >> 6) & 0x1F
    imm = (word >> 6) & 0x1F
    dest = cop2_dest_suffix(word) if dt in (2, 5, 8, 9) else ''
    if dt == 0:
        return name
    if dt == 1 or dt == 17:
        return f'{name} {cop2_reg(word,"vf",ft)}, {cop2_reg(word,"vf",fs)}'
    if dt == 2:
        return f'{name} {cop2_reg(word,"vf",fd)}, {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}{dest}'
    if dt == 3:
        return f'{name} {cop2_reg(word,"vf",fd)}, {cop2_reg(word,"vf",fs)}, $i'
    if dt == 4:
        return f'{name} {cop2_reg(word,"vf",fd)}, {cop2_reg(word,"vf",fs)}, $q'
    if dt == 5:
        return f'{name} $acc, {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}{dest}'
    if dt == 6:
        return f'{name} $acc, {cop2_reg(word,"vf",fs)}, $i'
    if dt == 7:
        return f'{name} $acc, {cop2_reg(word,"vf",fs)}, $q'
    if dt == 8:
        return f'{name} $acc, {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}{dest}'
    if dt == 9:
        return f'{name} $acc, {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}{dest}'
    if dt == 10:
        return f'{name} {cop2_reg(word,"vf",fd)}, {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}'
    if dt == 11:
        return f'{name} {cop2_reg(word,"vf",fs)}, {cop2_reg(word,"vf",ft)}'
    if dt == 12:
        ftf = (word >> 23) & 3
        fsf = (word >> 21) & 3
        return (f'{name} $q, {cop2_reg(word,"vf",fs)}.{ "xyzw"[fsf]}, '
                f'{cop2_reg(word,"vf",ft)}.{ "xyzw"[ftf]}')
    if dt == 13:
        fsf = (word >> 21) & 3
        return f'{name} $q, {cop2_reg(word,"vf",fs)}.{ "xyzw"[fsf]}'
    if dt == 14:
        return f'{name} {cop2_reg(word,"vi",ft)}, {cop2_reg(word,"vi",fs)}, {cop2_reg(word,"vi",fd)}'
    if dt == 15:
        return f'{name} {cop2_reg(word,"vi",ft)}, {cop2_reg(word,"vi",fs)}, {imm}'
    if dt == 16:
        return f'{name} {cop2_reg(word,"vf",ft)}, {cop2_reg(word,"vf",fs)}'
    if dt == 17:
        return f'{name} {cop2_reg(word,"vf",ft)}, {cop2_reg(word,"vi",fs)}'
    if dt == 18:
        fsf = (word >> 21) & 3
        return f'{name} {cop2_reg(word,"vi",ft)}, {cop2_reg(word,"vf",fs)}.{ "xyzw"[fsf]}'
    if dt == 19:
        return f'{name} {cop2_reg(word,"vf",ft)}, {cop2_reg(word,"vi",fs)}'
    if dt == 20:
        return f'{name} {cop2_reg(word,"vi",ft)}, {cop2_reg(word,"vi",fs)}'
    if dt == 21:
        return f'{name} {cop2_reg(word,"vf",ft)}, $c{fs}'
    if dt == 22:
        return f'{name} {cop2_reg(word,"vf",ft)}, $c{fs}'
    return f'cop2 0x{opcode:03X}'


def cop1_reg(n):
    """FP register name $f0-$f31."""
    return f'$f{n}'


def cop1_ctl(n):
    """Cop1 control register name ($fcr31 for 31)."""
    return '$fcr31' if n == 31 else f'$fcr{n}'


# PS2 EE COP0 (system coprocessor) subclass tables, per PCSX2 tbl_COP0 / tbl_COP0_BC0 / tbl_COP0_C0
# tbl_COP0 indexed by rs (bits 25-21)
COP0_TABLE = {
    0x00: 'MFC0', 0x04: 'MTC0',
    0x08: 'COP0_BC0',
    0x10: 'COP0_C0',
}

# tbl_COP0_BC0 indexed by bits 16-17 (condition)
COP0_BC0_TABLE = {
    0x00: 'BC0F', 0x01: 'BC0T', 0x02: 'BC0FL', 0x03: 'BC0TL',
}

# tbl_COP0_C0 indexed by funct (bits 5-0)
COP0_C0_TABLE = {
    0x01: 'TLBR', 0x02: 'TLBWI', 0x06: 'TLBWR', 0x08: 'TLBP',
    0x18: 'ERET', 0x38: 'EI', 0x39: 'DI',
}


def decode_cop0(word, vaddr=None):
    """Decode a PS2 EE COP0 system coprocessor instruction."""
    if (word >> 26) & 0x3F != 0x10:
        return None
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    cls = COP0_TABLE.get(rs)
    if cls is None:
        return f'cop0 0x{rs:02X}'

    if cls == 'MFC0':
        return f'mfc0 {reg_name(rt)}, $c{rd}'
    if cls == 'MTC0':
        return f'mtc0 {reg_name(rt)}, $c{rd}'
    if cls == 'COP0_BC0':
        name = COP0_BC0_TABLE.get((word >> 16) & 3, f'bc0_unk_0x{(word >> 16) & 3:X}')
        return f'{name} {imm_signed:+d}'
    if cls == 'COP0_C0':
        name = COP0_C0_TABLE.get(funct, f'cop0_c0_unk_0x{funct:02X}')
        return name
    return f'cop0 0x{rs:02X}'


# PS2 EE MMI (MultiMedia Instruction) subclass tables, per PCSX2 tbl_MMI / tbl_MMI0-3
# tbl_MMI indexed by funct (bits 5-0) when op=0x1C
MMI_TABLE = {
    0x00: 'MADD', 0x01: 'MADDU', 0x04: 'PLZCW', 0x08: 'MFHI1', 0x09: 'MTHI1',
    0x0A: 'MFLO1', 0x0B: 'MTLO1', 0x0C: 'MULT1', 0x0D: 'MULTU1', 0x0E: 'DIV1',
    0x0F: 'DIVU1', 0x10: 'MADD1', 0x11: 'MADDU1', 0x14: 'PMFHL', 0x15: 'PMTHL',
    0x16: 'PSLLH', 0x17: 'PSRLH', 0x18: 'PSRAH', 0x1C: 'PSLLW', 0x1D: 'PSRLW',
    0x1E: 'PSRAW',
}


def decode_mmi(word, vaddr=None):
    """Decode a PS2 EE MMI (multimedia) instruction."""
    if (word >> 26) & 0x3F != 0x1C:
        return None
    funct = word & 0x3F
    name = MMI_TABLE.get(funct, f'mmi_unk_0x{funct:02X}')
    # MMI instructions are mostly 3-operand GPR ops
    rd = (word >> 11) & 0x1F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    return f'{name} {reg_name(rd)},{reg_name(rs)},{reg_name(rt)}'


def decode_cop2_nv(word, vaddr=None):
    """Decode a PS2 EE COP2 non-vector instruction."""
    if (word >> 26) & 0x3F != 0x12:
        return None
    if (word >> 25) & 1:  # bit 25 set = vector, handled by decode_cop2
        return None
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    if rs == 0x00:  # QMFC2: GPR rt <- VU register rd
        return f'qmfc2 {reg_name(rt)}, $vf{rd}'
    if rs == 0x02:  # CFC2: GPR rt <- control register rd
        return f'cfc2 {reg_name(rt)}, $c{rd}'
    if rs == 0x04:  # QMTC2: VU register rd <- GPR rt
        return f'qmtc2 $vf{rd}, {reg_name(rt)}'
    if rs == 0x06:  # CTC2: control register rd <- GPR rt
        return f'ctc2 $c{rd}, {reg_name(rt)}'
    if rs == 0x08:  # BC2F/T/FL/TL
        bc = (word >> 16) & 3
        name = {0: 'bc2f', 1: 'bc2t', 2: 'bc2fl', 3: 'bc2tl'}.get(bc, f'bc2_unk_0x{bc:X}')
        return f'{name} {imm_signed:+d}'
    return f'cop2_nv_unk_0x{rs:02X}'


def decode_cop1(word, vaddr=None):
    """Decode a PS2 EE COP1 (FPU) scalar instruction."""
    if (word >> 26) & 0x3F != 0x11:
        return None
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    fs = (word >> 11) & 0x1F
    fd = (word >> 6) & 0x1F
    ft = (word >> 16) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    cls = COP1_TABLE.get(rs)
    if cls is None:
        return f'cop1 0x{rs:02X}'

    if cls == 'MFC1':
        return f'mfc1 {cop1_reg(rt)}, {cop1_reg(fs)}'
    if cls == 'CFC1':
        return f'cfc1 {cop1_reg(rt)}, {cop1_ctl(fs)}'
    if cls == 'MTC1':
        return f'mtc1 {cop1_reg(rt)}, {cop1_reg(fs)}'
    if cls == 'CTC1':
        return f'ctc1 {cop1_reg(rt)}, {cop1_ctl(fs)}'
    if cls == 'COP1_BC1':
        name = COP1_BC1_TABLE.get(rt, f'unk_bc1_0x{rt:02X}')
        return f'{name} {imm_signed:+d}'
    if cls == 'COP1_S':
        name = COP1_S_TABLE.get(funct)
        if name is None:
            return f'cop1.s 0x{funct:02X}'
        # C.xx.S uses cond field (bits 3-2 of funct? no, bits of the format)
        # PCSX2: C.F/C.EQ.S/C.LT.S/C.LE.S at funct 0x30/0x32/0x34/0x36 with ft,fs
        if name in ('C.F', 'C.EQ.S', 'C.LT.S', 'C.LE.S'):
            return f'{name} {cop1_reg(ft)}, {cop1_reg(fs)}'
        # Arithmetic: ft fs fd
        if name in ('ADD.S', 'SUB.S', 'MUL.S', 'DIV.S', 'MAX.S', 'MIN.S',
                    'MADD.S', 'MSUB.S', 'RSQRT.S'):
            return f'{name} {cop1_reg(fd)}, {cop1_reg(fs)}, {cop1_reg(ft)}'
        # Unary: fs fd
        if name in ('SQRT.S', 'ABS.S', 'MOV.S', 'NEG.S', 'CVT.W.S'):
            return f'{name} {cop1_reg(fd)}, {cop1_reg(fs)}'
        # Accumulator: ft fs (no fd)
        if name in ('ADDA.S', 'SUBA.S', 'MULA.S', 'MADDA.S', 'MSUBA.S'):
            return f'{name} {cop1_reg(ft)}, {cop1_reg(fs)}'
        return name
    if cls == 'COP1_W':
        name = COP1_W_TABLE.get(funct)
        if name == 'CVT.S.W':
            return f'cvt.s.w {cop1_reg(fd)}, {cop1_reg(fs)}'
        return f'cop1.w 0x{funct:02X}'
    return f'cop1 0x{rs:02X}'


MIPS_REGS = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']


def reg_name(n):
    """MIPS register name."""
    return MIPS_REGS[n] if 0 <= n < 32 else f'${n}'


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

    # PS2 EE COP2 (VU0) vector instructions take priority.
    cop2 = decode_cop2(word)
    if cop2 is not None:
        info['mnemonic'] = cop2
        info['branch'] = None
        return info

    # PS2 EE COP2 non-vector instructions (QMFC2, CFC2, QMTC2, CTC2, BC2F/T).
    cop2nv = decode_cop2_nv(word)
    if cop2nv is not None:
        info['mnemonic'] = cop2nv
        info['branch'] = None
        return info

    # PS2 EE COP1 (FPU) scalar instructions.
    cop1 = decode_cop1(word)
    if cop1 is not None:
        info['mnemonic'] = cop1
        info['branch'] = None
        return info

    # PS2 EE COP0 (system coprocessor) instructions.
    cop0 = decode_cop0(word)
    if cop0 is not None:
        info['mnemonic'] = cop0
        info['branch'] = None
        return info

    # PS2 EE MMI (multimedia) instructions.
    mmi = decode_mmi(word)
    if mmi is not None:
        info['mnemonic'] = mmi
        info['branch'] = None
        return info

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
        elif name in ('ADD', 'ADDU', 'SUB', 'SUBU', 'AND', 'OR', 'XOR', 'NOR', 'SLT', 'SLTU',
                      'DADD', 'DADDU', 'DSUB', 'DSUBU'):
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rs)},{reg_name(rt)}'
        elif name in ('DSLL', 'DSRL', 'DSRA', 'DSLL32', 'DSRL32', 'DSRA32'):
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{sa}'
        elif name in ('DSLLV', 'DSRLV', 'DSRAV'):
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rt)},{reg_name(rs)}'
        elif name in ('MFSA', 'MTSA'):
            if name == 'MFSA':
                info['mnemonic'] = f'{name} {reg_name(rd)}'
            else:
                info['mnemonic'] = f'{name} {reg_name(rs)}'
        elif name in ('TGE', 'TGEU', 'TLT', 'TLTU', 'TEQ', 'TNE'):
            info['mnemonic'] = f'{name} {reg_name(rs)},{reg_name(rt)}'
        else:
            info['mnemonic'] = f'{name} {reg_name(rd)},{reg_name(rs)},{reg_name(rt)}'

    elif op == 0x01:  # Branch on condition / cop1
        bc = rt  # For bc1t/bc1f, rt is the condition; for BLTZ etc., rt is the subtype
        if rs == 0x00:  # BLTZ, BGEZ, etc.
            name = REGIMM.get(rt, f'unk_bcond_0x{rt:02X}')
            offset = imm_signed * 4
            target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
            info['mnemonic'] = f'{name} {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else name
            info['branch'] = 'cond'
            info['target'] = target_vaddr
        elif rs == 0x10:  # Trap immediate
            name = REGIMM.get(rt, f'unk_trap_0x{rt:02X}')
            info['mnemonic'] = f'{name} {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        else:
            name = REGIMM.get(rt, f'unk_bcond_0x{rt:02X}')
            offset = imm_signed * 4
            target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
            info['mnemonic'] = f'{name} {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else name
            info['branch'] = 'cond'
            info['target'] = target_vaddr

    elif op == 0x02:  # J
        target_vaddr = (vaddr & 0xF0000000) | (target << 2) if vaddr else None
        info['mnemonic'] = f'J 0x{target_vaddr:08X}' if target_vaddr else f'J 0x{target:06X}'
        info['branch'] = 'direct'
        info['target'] = target_vaddr

    elif op == 0x03:  # JAL
        target_vaddr = (vaddr & 0xF0000000) | (target << 2) if vaddr else None
        info['mnemonic'] = f'JAL 0x{target_vaddr:08X}' if target_vaddr else f'JAL 0x{target:06X}'
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
    elif op == 0x27:  # LWU
        info['mnemonic'] = f'LWU {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x28:  # SB
        info['mnemonic'] = f'SB {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x29:  # SH
        info['mnemonic'] = f'SH {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2A:  # SWL
        info['mnemonic'] = f'SWL {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2B:  # SW
        info['mnemonic'] = f'SW {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2C:  # SDL
        info['mnemonic'] = f'SDL {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2D:  # SDR
        info['mnemonic'] = f'SDR {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2E:  # SWR
        info['mnemonic'] = f'SWR {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x31:  # LWC1 (FPU load word)
        info['mnemonic'] = f'LWC1 {cop1_reg(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x39:  # SWC1 (FPU store word)
        info['mnemonic'] = f'SWC1 {cop1_reg(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x36:  # LQC2 (COP2 load qword)
        info['mnemonic'] = f'LQC2 {cop2_reg(word,"vf",rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x3E:  # SQC2 (COP2 store qword)
        info['mnemonic'] = f'SQC2 {cop2_reg(word,"vf",rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x3F:  # SD (store double) — per PCSX2 tbl_Standard
        info['mnemonic'] = f'SD {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x2F:  # CACHE
        info['mnemonic'] = f'CACHE {sa},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x33:  # PREF
        info['mnemonic'] = f'PREF {sa},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x37:  # LD (load double)
        info['mnemonic'] = f'LD {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x14:  # BEQL
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BEQL {reg_name(rs)},{reg_name(rt)},0x{target_vaddr:08X}' if target_vaddr else f'BEQL {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr
    elif op == 0x15:  # BNEL
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BNEL {reg_name(rs)},{reg_name(rt)},0x{target_vaddr:08X}' if target_vaddr else f'BNEL {reg_name(rs)},{reg_name(rt)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr
    elif op == 0x16:  # BLEZL
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BLEZL {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else f'BLEZL {reg_name(rs)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr
    elif op == 0x17:  # BGTZL
        offset = imm_signed * 4
        target_vaddr = (vaddr + 4 + offset) & 0xFFFFFFFF if vaddr else None
        info['mnemonic'] = f'BGTZL {reg_name(rs)},0x{target_vaddr:08X}' if target_vaddr else f'BGTZL {reg_name(rs)},0x{imm:04X}'
        info['branch'] = 'cond'
        info['target'] = target_vaddr
    elif op == 0x18:  # DADDI
        info['mnemonic'] = f'DADDI {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x19:  # DADDIU
        info['mnemonic'] = f'DADDIU {reg_name(rt)},{reg_name(rs)},0x{imm:04X}'
    elif op == 0x1A:  # LDL
        info['mnemonic'] = f'LDL {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x1B:  # LDR
        info['mnemonic'] = f'LDR {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x1E:  # LQ
        info['mnemonic'] = f'LQ {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
    elif op == 0x1F:  # SQ
        info['mnemonic'] = f'SQ {reg_name(rt)},0x{imm:04X}({reg_name(rs)})'
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


def disassemble_buffer(buffer, base_address=0x00100000):
    """Performs two-pass disassembly with basic block tracing.

    Pass 1: Decode every instruction and collect branch targets.
    Pass 2: Print instructions with structural dividers at branch targets
            and basic block ending markers (JR, J, JAL, JALR, branches).

    Returns a list of (pc, word, asm, target_addr, is_branch_target, is_block_end) tuples.
    """
    instructions = {}
    branch_targets = set()

    # First Pass: Decode and find branch targets
    for i in range(0, len(buffer), 4):
        if i + 4 > len(buffer):
            break
        pc = base_address + i
        word = struct.unpack('<I', buffer[i:i + 4])[0]
        op = (word >> 26) & 0x3F
        funct = word & 0x3F

        asm, target = _decode_for_buffer(word, pc)

        instructions[pc] = (asm, target, word)

        if target:
            branch_targets.add(target)

    # Second Pass: Print basic blocks dynamically with structural dividers
    results = []
    for pc in sorted(instructions.keys()):
        asm, target, word = instructions[pc]
        is_branch_target = pc in branch_targets

        # Check basic block ending markers
        is_block_end = False
        if op in [0x02, 0x03] or (op == 0x00 and funct in [0x08, 0x09]):
            is_block_end = True

        results.append({
            'pc': pc,
            'word': word,
            'asm': asm,
            'target': target,
            'is_branch_target': is_branch_target,
            'is_block_end': is_block_end,
        })

    return results


def _decode_for_buffer(word, pc):
    """Decode a single instruction for use in disassemble_buffer.

    Returns (mnemonic_string, target_addr_or_None).
    """
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    funct = word & 0x3F

    imm = word & 0xFFFF
    imm_signed = imm - 0x10000 if imm & 0x8000 else imm

    target_addr = None
    mnemonic = OPCODES.get(op, f"unk_op_0x{op:02X}")

    if mnemonic == 'SPECIAL':
        mnemonic = FUNCTS.get(funct, f"unk_funct_0x{funct:02X}")
        if funct in (0x08, 0x09):  # JR, JALR
            return f"{mnemonic} ${MIPS_REGS[rs]}", None
        return f"{mnemonic} ${MIPS_REGS[rd]}, ${MIPS_REGS[rs]}, ${MIPS_REGS[rt]}", None

    elif mnemonic == 'REGIMM':
        mnemonic = REGIMM.get(rt, f"unk_regimm_0x{rt:02X}")
        target_addr = pc + 4 + (imm_signed << 2)
        return f"{mnemonic} ${MIPS_REGS[rs]}, 0x{target_addr:08X}", target_addr

    elif mnemonic in ('J', 'JAL'):
        target_idx = word & 0x03FFFFFF
        target_addr = (pc & 0xF0000000) | (target_idx << 2)
        return f"{mnemonic} 0x{target_addr:08X}", target_addr

    elif mnemonic in ('BEQ', 'BNE', 'BEQL', 'BNEL'):
        target_addr = pc + 4 + (imm_signed << 2)
        return f"{mnemonic} ${MIPS_REGS[rs]}, ${MIPS_REGS[rt]}, 0x{target_addr:08X}", target_addr

    elif mnemonic in ('BLEZ', 'BGTZ', 'BLEZL', 'BGTZL'):
        target_addr = pc + 4 + (imm_signed << 2)
        return f"{mnemonic} ${MIPS_REGS[rs]}, 0x{target_addr:08X}", target_addr

    elif mnemonic in ('ADDI', 'ADDIU', 'DADDI', 'DADDIU', 'SLTI', 'SLTIU'):
        return f"{mnemonic} ${MIPS_REGS[rt]}, ${MIPS_REGS[rs]}, {imm_signed}", None

    elif mnemonic in ('ANDI', 'ORI', 'XORI'):
        return f"{mnemonic} ${MIPS_REGS[rt]}, ${MIPS_REGS[rs]}, 0x{imm:04X}", None

    elif mnemonic == 'LUI':
        return f"{mnemonic} ${MIPS_REGS[rt]}, 0x{imm:04X}", None

    elif mnemonic == 'COP2':
        # Check if bit 25 is set for VU0 micro instructions
        if word & (1 << 25):
            v_funct = word & 0x7FF
            v_name, _ = COP2_TABLE.get(v_funct, (f"v_unk_0x{v_funct:03X}", 0))
            return f"{v_name} (COP2 bits: 0x{word & 0x1FFFFFF:07X})", None
        else:
            return f"COP2_MACRO 0x{word:08X}", None

    # Base fallback for loads and stores
    if op >= 0x20:
        return f"{mnemonic} ${MIPS_REGS[rt]}, {imm_signed}(${MIPS_REGS[rs]})", None

    return f"{mnemonic} 0x{word:08X}", None


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x230260
    end = int(sys.argv[3], 0) if len(sys.argv) > 3 else start + 256

    data = Path(path).read_bytes()
    for info in disassemble_range(data, start, end):
        print(format_disassembly([info]))
