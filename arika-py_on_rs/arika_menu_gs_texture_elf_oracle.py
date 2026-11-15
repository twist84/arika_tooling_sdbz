"""Controlled R5900 scalar interpreter for EU-beta texture register setup.

Reads exact *user-owned* ELF bytes at runtime. Supports only the
instruction families used by 0x10C3E0 and mip helper 0x10C7C0.
Not a generic EE, GS or VU emulator; no ELF code is stored here.
"""
import hashlib
import struct

EXPECTED_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
MASK64 = (1 << 64) - 1
FILE_BIAS = 0xfff80


def signed(value, width):
    value &= (1 << width) - 1
    return value - (1 << width) if value & (1 << (width - 1)) else value


class c_native_texture_elf_oracle:
    def __init__(self, elf_data):
        if hashlib.sha256(elf_data).hexdigest() != EXPECTED_SHA256:
            raise ValueError('wrong EU-beta ELF SHA256')
        self.m_code = {}
        for begin, end in ((0x10c3e0, 0x10c7bc),
                           (0x10c7c0, 0x10c88c)):
            for pc in range(begin, end, 4):
                self.m_code[pc] = struct.unpack_from(
                    '<I', elf_data, pc - FILE_BIAS)[0]
        self.m_regs = [0] * 32
        self.m_memory = {}
        self.m_lo = 0
        self.m_regs[29] = 0x800000
        self.m_regs[31] = 0xf00000
        self.m_steps = 0

    def read(self, address, size):
        return int.from_bytes(bytes(self.m_memory.get(address + i, 0)
                                    for i in range(size)), 'little')

    def write(self, address, value, size):
        data = (value & ((1 << (size*8))-1)).to_bytes(size, 'little')
        for i, byte in enumerate(data):
            self.m_memory[address + i] = byte

    def bytes(self, address, data):
        for i, value in enumerate(data):
            self.m_memory[address + i] = value

    def scalar(self, word):
        if word == 0:
            return
        r = self.m_regs
        op = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        sh, fn = (word >> 6) & 31, word & 63
        imm = signed(word & 0xffff, 16)
        addr = (r[rs] + imm) & MASK64
        if op == 0:
            if fn == 0: r[rd] = signed(r[rt] << sh, 32)
            elif fn == 2: r[rd] = signed((r[rt] & 0xffffffff) >> sh, 32)
            elif fn == 3: r[rd] = signed(signed(r[rt], 32) >> sh, 32)
            elif fn == 0x21: r[rd] = signed(r[rs] + r[rt], 32)
            elif fn == 0x2d: r[rd] = signed(r[rs] + r[rt], 64)
            elif fn == 0x23: r[rd] = signed(r[rs] - r[rt], 32)
            elif fn == 0x25: r[rd] = signed(r[rs] | r[rt], 64)
            elif fn == 0x24: r[rd] = signed(r[rs] & r[rt], 64)
            elif fn == 0x2a: r[rd] = int(signed(r[rs], 64) < signed(r[rt], 64))
            elif fn == 0x38: r[rd] = signed((r[rt] & MASK64) << sh, 64)
            elif fn == 0x3b: r[rd] = signed(r[rt], 64) >> sh
            elif fn == 0x3c: r[rd] = signed((r[rt] & MASK64) << (sh+32), 64)
            elif fn == 0x3f: r[rd] = signed(r[rt], 64) >> (sh+32)
            elif fn == 0x18:
                # R5900's three-operand MULT writes RD as well as LO.
                self.m_lo = signed(
                    signed(r[rs], 32) * signed(r[rt], 32), 32)
                if rd: r[rd] = self.m_lo
            elif fn == 0x12: r[rd] = self.m_lo
            else: raise AssertionError('unsupported scalar special %08x' % word)
        elif op == 9: r[rt] = signed(r[rs]+imm, 32)
        elif op == 15: r[rt] = signed((word & 0xffff) << 16, 32)
        elif op == 13: r[rt] = signed(r[rs] | (word & 0xffff), 64)
        elif op == 12: r[rt] = signed(r[rs] & (word & 0xffff), 64)
        elif op == 10: r[rt] = int(signed(r[rs], 64) < imm)
        elif op == 11: r[rt] = int((r[rs] & MASK64) < (imm & MASK64))
        elif op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x37, 0x1e):
            size = {0x20:1, 0x21:2, 0x23:4, 0x24:1,
                    0x25:2, 0x37:8, 0x1e:16}[op]
            value = self.read(addr, size)
            if op == 0x1e:
                r[rt] = signed(value, 128)
            else:
                r[rt] = value if op in (0x24, 0x25) else signed(value, size*8)
        elif op in (0x28, 0x29, 0x2b, 0x3f, 0x1f):
            self.write(addr, r[rt],
                       {0x28:1,0x29:2,0x2b:4,0x3f:8,0x1f:16}[op])
        else:
            raise AssertionError('unsupported scalar %08x' % word)
        r[0] = 0

    def run(self, start=0x10c3e0):
        pc = start
        r = self.m_regs
        for _ in range(40000):
            self.m_steps += 1
            if pc == 0xf00000:
                return signed(r[2], 32)
            if pc not in self.m_code:
                raise AssertionError('unmapped code 0x%x' % pc)
            word = self.m_code[pc]
            op = word >> 26
            rs, rt, fn = (word >> 21) & 31, (word >> 16) & 31, word & 63
            is_branch = op in (1, 4, 5, 6, 7)
            is_jump = op == 0 and fn in (8, 9)
            if is_branch:
                if op == 1:
                    if rt == 0: take = signed(r[rs], 64) < 0
                    elif rt == 1: take = signed(r[rs], 64) >= 0
                    else: raise AssertionError('unsupported REGIMM %08x' % word)
                elif op == 4: take = r[rs] == r[rt]
                elif op == 5: take = r[rs] != r[rt]
                elif op == 6: take = r[rs] <= 0
                else: take = r[rs] > 0
                target = pc + 4 + signed(word & 0xffff, 16) * 4
                self.scalar(self.m_code[pc + 4])
                pc = target if take else pc + 8
            elif op == 2 or op == 3:
                target = (pc & 0xf0000000) | ((word & 0x3ffffff) << 2)
                if op == 3:
                    r[31] = pc + 8
                self.scalar(self.m_code[pc + 4])
                pc = target
            elif is_jump:
                target = r[rs] & 0xffffffff
                if fn == 9:
                    r[(word >> 11) & 31] = pc + 8
                self.scalar(self.m_code[pc + 4])
                pc = target
            else:
                self.scalar(word)
                pc += 4
        raise AssertionError('native function exceeded iteration limit')

    def native_writes(self, slot, descriptor, filter_flag, clamp_flag):
        self.m_regs[4] = slot
        addresses = (0x600000, 0x600010, 0x600020,
                     0x600030, 0x600040, 0x600050)
        for i, address in enumerate(addresses):
            self.m_regs[5+i] = address
        self.m_regs[11] = filter_flag
        self.write(self.m_regs[29], clamp_flag, 4)
        self.bytes(0x4ff8f0 + (slot - 1) * 48, descriptor)
        result = self.run()
        return result, [self.read(address, 8) for address in addresses]
