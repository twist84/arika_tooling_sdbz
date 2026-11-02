#!/usr/bin/env python3
"""
ELF tooling: SSA (Static Single Assignment) construction for MIPS IR.

Takes MIPS ELF code, lifts to IR, builds CFG, computes dominance frontiers,
inserts phi functions, and renames variables with version numbers.

SSA form is the foundation for decompilation: it makes data flow explicit,
enables control flow structuring (if/while/for reconstruction), and is the
input to most compiler optimizations and C code emission.

Usage:
    python elf_ssa.py [elf] [start_vaddr] [end_vaddr]

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
from elf_cfg_builder import (
    split_into_basic_blocks, build_cfg_edges,
    compute_dominators, find_loop_back_edges,
    BasicBlock
)
from elf_ir_lifter import lift_elf, IRFunction, IRInstr, IRValue


MIPS_REGS = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']


def reg_name(n):
    return MIPS_REGS[n] if 0 <= n < 32 else f'${n}'


class IRValue:
    """An IR value: virtual register, constant, or memory."""
    def __init__(self, kind, value):
        self.kind = kind   # 'vreg', 'imm', 'mem', 'label', 'phi'
        self.value = value

    def __repr__(self):
        if self.kind == 'vreg':
            return f't{self.value}'
        if self.kind == 'imm':
            return f'0x{self.value:08X}'
        if self.kind == 'mem':
            base, off = self.value
            return f'mem[{reg_name(base)}+0x{off:04X}]'
        if self.kind == 'phi':
            return f'PHI({", ".join(str(v) for v in self.value)})'
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
        self.opcode = opcode
        self.vaddr = vaddr
        self.file_off = file_off
        self.mnemonic = mnemonic
        self.defs = defs or []      # List of IRValue
        self.uses = uses or []      # List of IRValue
        self.branch_target = branch_target

    def __repr__(self):
        defs_str = ', '.join(str(d) for d in self.defs)
        uses_str = ', '.join(str(u) for u in self.uses)
        target = f' -> {self.branch_target:08X}' if self.branch_target else ''
        return f'{self.opcode} {defs_str} := {uses_str}{target}'


class IRFunction:
    """A lifted IR function with block structure."""
    def __init__(self, start_vaddr, end_vaddr):
        self.start_vaddr = start_vaddr
        self.end_vaddr = end_vaddr
        self.blocks = []  # List of (start_vaddr, [IRInstr])

    def add_block(self, start_vaddr):
        self.blocks.append((start_vaddr, []))
        return self.blocks[-1][1]

    def __repr__(self):
        lines = [f'; IR function @ 0x{self.start_vaddr:08X}-0x{self.end_vaddr:08X}']
        for start_vaddr, instrs in self.blocks:
            lines.append(f'  Block @ 0x{start_vaddr:08X}:')
            for instr in instrs:
                lines.append(f'    {instr}')
        return '\n'.join(lines)


class SSAVariable:
    """A versioned SSA variable: tN_vM where N is the original reg and M is the version."""
    def __init__(self, vreg, version):
        self.vreg = vreg
        self.version = version

    def __repr__(self):
        return f't{self.vreg}_v{self.version}'

    def __hash__(self):
        return hash((self.vreg, self.version))

    def __eq__(self, other):
        return isinstance(other, SSAVariable) and self.vreg == other.vreg and self.version == other.version


def lift_and_block(data, start_vaddr, end_vaddr):
    """Lift ELF to IR and split into basic blocks with IR instructions assigned."""
    start_off = vaddr_to_file(start_vaddr)
    end_off = min(len(data) - 4, vaddr_to_file(end_vaddr))

    # First pass: split into basic blocks (using raw words for CFG structure)
    raw_blocks = split_into_basic_blocks(data, start_vaddr, end_vaddr)

    # Second pass: lift instructions and assign to blocks
    ir_blocks = []
    for block in raw_blocks:
        block_instrs = []
        off = block.start_file_off
        block_end = block.start_file_off + len(block.instructions) * 4

        while off < block_end and off < len(data) - 4:
            word = struct.unpack_from('<I', data, off)[0]
            vaddr = file_to_vaddr(off)
            info = decode_instruction(word, vaddr)
            mnemonic = info.get('mnemonic', '')
            op = (word >> 26) & 0x3F
            rs = (word >> 21) & 0x1F
            rt = (word >> 16) & 0x1F
            rd = (word >> 11) & 0x1F
            sa = (word >> 6) & 0x1F
            funct = word & 0x3F
            imm = word & 0xFFFF
            imm_signed = imm - 0x10000 if imm & 0x8000 else imm

            # Build IR instruction
            ir_instr = _lift_single(word, vaddr, off, mnemonic, op, rs, rt, rd, sa, funct, imm, imm_signed)
            if ir_instr:
                # Filter out None vregs (from $zero, which is constant 0)
                ir_instr.defs = [d for d in ir_instr.defs if d is not None]
                ir_instr.uses = [u for u in ir_instr.uses if u is not None]
                block_instrs.append(ir_instr)

            off += 4

        ir_blocks.append((block.start_vaddr, block_instrs))

    return ir_blocks


def _lift_single(word, vaddr, file_off, mnemonic, op, rs, rt, rd, sa, funct, imm, imm_signed):
    """Lift a single instruction to IRInstr with defs/uses."""
    def rv(n):
        if n == 0:
            return None  # $zero is constant 0
        return IRValue('vreg', n)

    instrs = []

    if op == 0x00:  # R-type
        if funct == 0x08:  # JR
            return IRInstr('jr', vaddr, file_off, mnemonic,
                           uses=[rv(rs)] if rv(rs) else [])
        elif funct == 0x09:  # JALR
            return IRInstr('jalr', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs)] if rv(rs) else [])
        elif funct == 0x0C:  # SYSCALL
            return IRInstr('syscall', vaddr, file_off, mnemonic)
        elif funct == 0x0D:  # BREAK
            return IRInstr('break', vaddr, file_off, mnemonic)
        elif funct == 0x20:  # ADD
            return IRInstr('add', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x21:  # ADDU
            return IRInstr('addu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x22:  # SUB
            return IRInstr('sub', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x23:  # SUBU
            return IRInstr('subu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x24:  # AND
            return IRInstr('and', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x25:  # OR
            return IRInstr('or', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x26:  # XOR
            return IRInstr('xor', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x27:  # NOR
            return IRInstr('nor', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2A:  # SLT
            return IRInstr('slt', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2B:  # SLTU
            return IRInstr('sltu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2C:  # DADD
            return IRInstr('dadd', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2D:  # DADDU
            return IRInstr('daddu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2E:  # DSUB
            return IRInstr('dsub', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x2F:  # DSUBU
            return IRInstr('dsubu', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None])
        elif funct == 0x00:  # SLL
            return IRInstr('sll', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])
        elif funct == 0x02:  # SRL
            return IRInstr('srl', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])
        elif funct == 0x03:  # SRA
            return IRInstr('sra', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [],
                           uses=[rv(rt) if rv(rt) else None, IRValue('imm', sa)])
        elif funct == 0x10:  # MFHI
            return IRInstr('mfhi', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [])
        elif funct == 0x12:  # MFLO
            return IRInstr('mflo', vaddr, file_off, mnemonic,
                           defs=[rv(rd)] if rv(rd) else [])

    # I-type
    elif op == 0x04:  # BEQ
        return IRInstr('beq', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))
    elif op == 0x05:  # BNE
        return IRInstr('bne', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None, rv(rt) if rv(rt) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))
    elif op == 0x06:  # BLEZ
        return IRInstr('blez', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))
    elif op == 0x07:  # BGTZ
        return IRInstr('bgtz', vaddr, file_off, mnemonic,
                       uses=[rv(rs) if rv(rs) else None],
                       branch_target=vaddr + 4 + (imm_signed << 2))
    elif op == 0x08:  # ADDI
        return IRInstr('addi', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])
    elif op == 0x09:  # ADDIU
        return IRInstr('addiu', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])
    elif op == 0x0A:  # SLTI
        return IRInstr('slti', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])
    elif op == 0x0B:  # SLTIU
        return IRInstr('sltiu', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm_signed)])
    elif op == 0x0C:  # ANDI
        return IRInstr('andi', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])
    elif op == 0x0D:  # ORI
        return IRInstr('ori', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])
    elif op == 0x0E:  # XORI
        return IRInstr('xori', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[rv(rs) if rv(rs) else None, IRValue('imm', imm)])
    elif op == 0x0F:  # LUI
        return IRInstr('lui', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('imm', imm << 16)])
    elif op == 0x23:  # LW
        return IRInstr('lw', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('mem', (rs, imm_signed))])
    elif op == 0x2B:  # SW
        return IRInstr('sw', vaddr, file_off, mnemonic,
                       uses=[rv(rt) if rv(rt) else None, IRValue('mem', (rs, imm_signed))])
    elif op == 0x31:  # LWC1
        return IRInstr('lwc1', vaddr, file_off, mnemonic,
                       defs=[rv(rt)] if rv(rt) else [],
                       uses=[IRValue('mem', (rs, imm_signed))])
    elif op == 0x39:  # SWC1
        return IRInstr('swc1', vaddr, file_off, mnemonic,
                       uses=[rv(rt) if rv(rt) else None, IRValue('mem', (rs, imm_signed))])

    # J-type
    elif op == 0x02:  # J
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        return IRInstr('j', vaddr, file_off, mnemonic, branch_target=target)
    elif op == 0x03:  # JAL
        target_idx = word & 0x3FFFFFF
        target = (vaddr & 0xF0000000) | (target_idx << 2)
        return IRInstr('jal', vaddr, file_off, mnemonic,
                       defs=[rv(31)] if rv(31) else [],
                       branch_target=target)

    # COP1
    elif op == 0x11:
        rs_cop1 = (word >> 21) & 0x1F
        if cop1_op == 0x00:  # MFC1
            return IRInstr('mfc1', vaddr, file_off, mnemonic,
                           defs=[rv(rt)] if rv(rt) else [],
                           uses=[rv(fs) if rv(fs) else None])
        elif cop1_op == 0x04:  # MTC1
            return IRInstr('mtc1', vaddr, file_off, mnemonic,
                           uses=[rv(rt) if rv(rt) else None, rv(fs) if rv(fs) else None])

    # Return None for unhandled instructions (they don't define/use vregs in a meaningful way)
    return None


def compute_dominance_frontiers(blocks, edges, idom):
    """Compute dominance frontiers: DF(n) = {y | n dominates pred of y, but n doesn't strictly dominate y}"""
    n = len(blocks)
    preds = [[] for _ in range(n)]
    for from_idx, to_idx, _ in edges:
        preds[to_idx].append(from_idx)

    df = [set() for _ in range(n)]

    for n_idx in range(n):
        if len(preds[n_idx]) < 2:
            continue
        for p in preds[n_idx]:
            runner = p
            while runner is not None and runner != idom.get(n_idx, n_idx):
                df[runner].add(n_idx)
                runner = idom.get(runner)

    return df


def build_ssa(ir_blocks, blocks, edges, dom, idom):
    """Build SSA form: compute DF, insert phi functions, rename variables."""
    n = len(ir_blocks)
    df = compute_dominance_frontiers(blocks, edges, idom)

    # Step 1: Collect defined vregs per block
    block_defs = [set() for _ in range(n)]
    block_uses = [set() for _ in range(n)]

    for i, (_, instrs) in enumerate(ir_blocks):
        for instr in instrs:
            for d in instr.defs:
                if d.is_reg():
                    block_defs[i].add(d.value)
            for u in instr.uses:
                if u.is_reg():
                    block_uses[i].add(u.value)

    # Step 2: Insert phi functions at dominance frontiers
    # For each vreg defined in block n, add phi to all blocks in DF(n)
    phi_inserted = [set() for _ in range(n)]  # track which vregs have phi in each block

    defs_worklist = [set(block_defs[i]) for i in range(n)]

    while any(defs_worklist):
        changed = False
        for i in range(n):
            for vreg in list(defs_worklist[i]):
                if vreg not in phi_inserted[i]:
                    # Insert phi at all DF blocks
                    for df_block in df[i]:
                        if df_block < n and vreg not in phi_inserted[df_block]:
                            phi_inserted[df_block].add(vreg)
                            # Add phi definition to this block
                            defs_worklist[df_block].add(vreg)
                            changed = True
        if not changed:
            break

    # Step 3: Rename variables
    # Version counter per vreg
    vreg_counter = {}
    # Stack of versions per vreg
    vreg_stack = {}

    # Track last version of each vreg at end of each block (for phi operands)
    block_out_versions = {}  # block_idx -> {vreg: version}

    def get_version(vreg):
        if vreg not in vreg_counter:
            vreg_counter[vreg] = 0
            vreg_stack[vreg] = []
        return vreg_counter[vreg]

    def new_version(vreg):
        if vreg not in vreg_counter:
            vreg_counter[vreg] = 0
            vreg_stack[vreg] = []
        vreg_counter[vreg] += 1
        vreg_stack[vreg].append(vreg_counter[vreg])
        return vreg_counter[vreg]

    def current_version(vreg):
        if vreg not in vreg_stack or not vreg_stack[vreg]:
            return 0  # undefined version
        return vreg_stack[vreg][-1]

    def pop_version(vreg):
        if vreg_stack.get(vreg):
            vreg_stack[vreg].pop()

    # Rename function (DFS over CFG in dominator tree order)
    visited = set()

    def rename_block(block_idx):
        if block_idx in visited:
            return
        visited.add(block_idx)

        _, instrs = ir_blocks[block_idx]

        # Insert phi functions at start of block
        phi_instrs = []
        for vreg in sorted(phi_inserted[block_idx]):
            version = new_version(vreg)
            # Phi operands will be filled in later (need predecessor info)
            phi_instrs.append(IRInstr('phi', vaddr=ir_blocks[block_idx][0],
                                      file_off=0, mnemonic='phi',
                                      defs=[IRValue('vreg', version)],
                                      uses=[]))  # uses filled later

        # Replace uses/defs in existing instructions
        new_instrs = list(phi_instrs)
        for instr in instrs:
            new_uses = []
            for u in instr.uses:
                if u.is_reg():
                    v = current_version(u.value)
                    new_uses.append(IRValue('vreg', v))
                else:
                    new_uses.append(u)
            new_defs = []
            for d in instr.defs:
                if d.is_reg():
                    v = new_version(d.value)
                    new_defs.append(IRValue('vreg', v))
                else:
                    new_defs.append(d)
            new_instrs.append(IRInstr(instr.opcode, instr.vaddr, instr.file_off,
                                      instr.mnemonic, new_defs, new_uses,
                                      instr.branch_target))

        ir_blocks[block_idx] = (ir_blocks[block_idx][0], new_instrs)

        # Record outgoing versions (last version of each vreg at end of block)
        block_out_versions[block_idx] = {}
        for vreg in vreg_stack:
            if vreg_stack[vreg]:
                block_out_versions[block_idx][vreg] = vreg_stack[vreg][-1]

        # Recurse on CFG children (dominator tree order)
        for j in range(n):
            if idom.get(j) == block_idx and j not in visited:
                rename_block(j)

    # Start from entry block (block 0)
    if n > 0:
        rename_block(0)

    # Step 4: Fill in phi operands
    # For each phi at block B with vreg v, find each predecessor P of B,
    # look up the last version of v at the end of P, and use that as the operand
    # Build predecessor list
    block_preds = [[] for _ in range(n)]
    for from_idx, to_idx, _ in edges:
        block_preds[to_idx].append(from_idx)

    for i, (_, instrs) in enumerate(ir_blocks):
        new_instrs = []
        for instr in instrs:
            if instr.opcode == 'phi' and instr.defs:
                vreg = instr.defs[0].value
                version = new_version(vreg)  # This is the phi result version
                instr.defs[0] = IRValue('vreg', version)
                
                # Fill phi uses: one operand per predecessor block
                new_uses = []
                for pred_idx in block_preds[i]:
                    pred_out_versions = block_out_versions.get(pred_idx, {})
                    pred_version = pred_out_versions.get(vreg, 0)
                    new_uses.append(IRValue('vreg', pred_version))
                instr.uses = new_uses
            new_instrs.append(instr)
        ir_blocks[i] = (ir_blocks[i][0], new_instrs)

    return ir_blocks, vreg_counter


def print_ssa(ir_blocks):
    """Print SSA form."""
    print("\n" + "=" * 72)
    print("SSA FORM")
    print("=" * 72)
    for start_vaddr, instrs in ir_blocks:
        print(f"\n  Block @ 0x{start_vaddr:08X}:")
        for instr in instrs:
            print(f"    {instr}")


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0018C518
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else start_vaddr + 0x400

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF SSA CONSTRUCTION")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print()

    # Step 1: Lift and block
    ir_blocks = lift_and_block(data, start_vaddr, end_vaddr)
    print(f"IR blocks: {len(ir_blocks)}")
    total_instrs = sum(len(instrs) for _, instrs in ir_blocks)
    print(f"Total IR instructions: {total_instrs}")
    print()

    # Step 2: Build CFG from raw blocks (for dominance)
    raw_blocks = split_into_basic_blocks(data, start_vaddr, end_vaddr)
    edges = build_cfg_edges(raw_blocks)

    # Step 3: Compute dominators
    dom, idom = compute_dominators(raw_blocks, edges)

    # Step 4: Build SSA
    ssa_blocks, vreg_counter = build_ssa(ir_blocks, raw_blocks, edges, dom, idom)

    # Step 5: Print
    print_ssa(ssa_blocks)

    print(f"\nVersion counters: {dict(vreg_counter)}")


if __name__ == '__main__':
    main()
