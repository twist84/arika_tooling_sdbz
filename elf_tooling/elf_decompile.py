#!/usr/bin/env python3
"""
ELF tooling: Full ELF decompiler - decompile entire ELF to multiple C files.

Scans the ELF for function boundaries (JAL targets + entry point),
then decompiles each function into C code. Functions are split across
multiple files, max 350 per file.

Usage:
    python elf_decompile.py [elf] [start_vaddr] [end_vaddr] [output_dir]

Defaults:
    elf   = source_data/SLUS_214.42
    start = 0x00100000 (entry point)
    end   = 0x00400700 (end of code section)
    out   = decompiled/
"""
import struct
import sys
import os
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file
from elf_ir_lifter import lift_elf, IRFunction, IRInstr, IRValue
from elf_cfg_builder import (
    split_into_basic_blocks, build_cfg_edges,
    compute_dominators, find_loop_back_edges
)
from elf_ssa import lift_and_block
from elf_cfg_structurer import CFGStructurer
from elf_c_emitter import CEmitter


MEM_SIZE = 0x100000


def find_function_boundaries(data, start_vaddr, end_vaddr):
    """Scan the ELF for function boundaries.

    A function boundary is:
    - The entry point (first address)
    - Any address that is a target of a JAL instruction (function call target)
    """
    start_off = vaddr_to_file(start_vaddr)
    end_off = min(len(data) - 4, vaddr_to_file(end_vaddr))

    targets = set()
    targets.add(start_vaddr)  # Entry point is always a function start

    off = start_off
    while off < end_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        op = (word >> 26) & 0x3F

        if op == 0x03:  # JAL
            target_idx = word & 0x3FFFFFF
            target_vaddr = (vaddr & 0xF0000000) | (target_idx << 2)
            if start_vaddr <= target_vaddr < end_vaddr:
                targets.add(target_vaddr)

        off += 4

    return sorted(targets)


def lift_function(data, start_vaddr, end_vaddr):
    """Lift a single function to IR instructions."""
    start_off = vaddr_to_file(start_vaddr)
    end_off = min(len(data) - 4, vaddr_to_file(end_vaddr))

    ir = IRFunction(start_vaddr, end_vaddr)

    off = start_off
    while off < end_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        op = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        rd = (word >> 11) & 0x1F
        sa = (word >> 6) & 0x1F
        funct = word & 0x3F
        imm = word & 0xFFFF
        imm_signed = imm - 0x10000 if imm & 0x8000 else imm

        ir_instrs = lift_instruction(word, vaddr, off, info.get('mnemonic', ''),
                                     op, rs, rt, rd, sa, funct, imm, imm_signed)
        for instr in ir_instrs:
            ir.add_instr(instr.opcode, instr.vaddr, instr.file_off,
                         instr.mnemonic, instr.defs, instr.uses,
                         instr.branch_target)

        off += 4

    return ir


def lift_instruction(word, vaddr, file_off, mnemonic, op, rs, rt, rd, sa, funct, imm, imm_signed):
    """Lift a single instruction to IR instructions."""
    def rv(n):
        if n == 0:
            return None
        return IRValue('vreg', n)

    instrs = []

    if op == 0x00:  # R-type
        if funct == 0x08:  # JR
            return [IRInstr('jr', vaddr, file_off, mnemonic,
                           uses=[rv(rs)] if rv(rs) else [])]
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


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x00100000
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x00400700
    output_dir = sys.argv[4] if len(sys.argv) > 4 else 'decompiled'
    max_funcs_per_file = int(sys.argv[5]) if len(sys.argv) > 5 else 350

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF DECOMPILER - Full ELF to C")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print(f"Output dir: {output_dir}")
    print(f"Max functions per file: {max_funcs_per_file}")
    print()

    # Step 1: Find function boundaries
    print("Scanning for function boundaries...")
    functions = find_function_boundaries(data, start_vaddr, end_vaddr)
    print(f"Found {len(functions)} function entry points")

    # Step 2: Decompile each function
    all_functions = []
    for i, func_start in enumerate(functions):
        func_end = functions[i + 1] if i + 1 < len(functions) else end_vaddr

        print(f"  [{i+1}/{len(functions)}] Decompiling 0x{func_start:08X}-0x{func_end:08X}")

        try:
            # Lift to IR
            ir_blocks = lift_function(data, func_start, func_end)

            if not ir_blocks:
                print(f"  [WARNING] No instructions for function at 0x{func_start:08X}")
                continue

            # Build CFG
            raw_blocks = split_into_basic_blocks(data, func_start, func_end)
            edges = build_cfg_edges(raw_blocks)

            # Compute dominators
            dom, idom = compute_dominators(raw_blocks, edges)

            # Find loops
            back_edges = find_loop_back_edges(raw_blocks, edges, idom)
            loops = []
            for from_idx, to_idx in back_edges:
                loops.append({'header': to_idx, 'back_edge_from': from_idx, 'body': {to_idx, from_idx}})

            # Structure CFG
            structurer = CFGStructurer(ir_blocks, raw_blocks, edges, dom, idom, loops)
            root_stmt = structurer.structure()

            # Emit C
            emitter = CEmitter()
            c_code = emitter.emit_c(root_stmt, function_name=f'func_0x{func_start:08X}')

            all_functions.append((func_start, func_end, c_code))

        except Exception as e:
            print(f"  [ERROR] Failed to decompile 0x{func_start:08X}: {e}")
            continue

        # Write file when we have enough functions
        if len(current_file_funcs) >= funcs_per_file:
            output_path = os.path.join(output_dir, f'decompiled_{file_idx:03d}.c')
            write_c_file(output_path, current_file_funcs)
            print(f"Wrote {output_path} ({len(current_file_funcs)} functions)")
            file_idx += 1
            current_file_funcs = []

    # Write remaining functions
    if current_file_funcs:
        output_path = os.path.join(output_dir, f'decompiled_{file_idx:03d}.c')
        write_c_file(output_path, current_file_funcs)
        print(f"Wrote {output_path} ({len(current_file_funcs)} functions)")

    print(f'\nDecompilation complete! {len(all_functions)} functions in {file_idx + 1} files.')


def write_c_file(output_path, file_functions):
    """Write a C file with multiple functions."""
    with open(output_path, 'w') as f:
        f.write('#include <stdint.h>\n')
        f.write('#include <stdio.h>\n')
        f.write('#include <string.h>\n')
        f.write('\n')
        f.write(f'#define MEM_SIZE 0x{MEM_SIZE:X}\n')
        f.write('static uint8_t mem[MEM_SIZE];\n')
        f.write('\n')
        f.write('#define READ32(addr) (*(uint32_t*)(mem + (addr)))\n')
        f.write('#define WRITE32(addr, val) (*(uint32_t*)(mem + (addr)) = (val))\n')
        f.write('\n')

        # Collect all variables used
        all_vars = set()
        for func_start, func_end, c_code in file_functions:
            for m in re.finditer(r'\bt(\d+)\b', c_code):
                all_vars.add(f't{m.group(1)}')

        if all_vars:
            sorted_vars = sorted(all_vars, key=lambda v: int(v[1:]))
            decls = ', '.join(sorted_vars)
            f.write(f'uint32_t {decls};\n')
            f.write('\n')

        for func_start, func_end, c_code in file_functions:
            f.write(f'\n/* Function at 0x{func_start:08X}-0x{func_end:08X} */\n')
            f.write(c_code)
            f.write('\n')


if __name__ == '__main__':
    main()
