#!/usr/bin/env python3
"""
ELF tooling: CFG Structurer - convert SSA IR to structured C-like pseudocode.

Takes SSA-form IR from elf_ssa.py and converts control flow into structured
constructs (if/else, while loops, sequences). This is the bridge between
SSA IR and C code emission.

Usage:
    python elf_cfg_structurer.py [elf] [start_vaddr] [end_vaddr]

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
from elf_ssa import lift_and_block, compute_dominance_frontiers, build_ssa


MIPS_REGS = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']


def reg_name(n):
    return MIPS_REGS[n] if 0 <= n < 32 else f'${n}'


class Stmt:
    """A statement in the structured IR."""
    def __init__(self, kind, **kwargs):
        self.kind = kind  # 'expr', 'assign', 'if', 'while', 'return', 'nop', 'call'
        self.__dict__.update(kwargs)

    def __str__(self, indent=0):
        pad = '  ' * indent
        if self.kind == 'expr':
            return f'{pad}{self.expr};'
        elif self.kind == 'assign':
            return f'{pad}{self.lhs} = {self.rhs};'
        elif self.kind == 'if':
            lines = [f'{pad}if ({self.cond}) {{']
            lines.append(self.then_block.__str__(indent + 1))
            if self.else_block:
                lines.append(f'{pad}}} else {{')
                lines.append(self.else_block.__str__(indent + 1))
            lines.append(f'{pad}}}')
            return '\n'.join(lines)
        elif self.kind == 'while':
            lines = [f'{pad}while ({self.cond}) {{']
            lines.append(self.body.__str__(indent + 1))
            lines.append(f'{pad}}}')
            return '\n'.join(lines)
        elif self.kind == 'return':
            return f'{pad}return {self.expr};'
        elif self.kind == 'nop':
            return f'{pad};'
        elif self.kind == 'call':
            return f'{pad}{self.expr};'
        return f'{pad}// unknown: {self.kind}'


class BlockStmt(Stmt):
    """A block of statements."""
    def __init__(self, stmts):
        super().__init__('block', stmts=stmts)

    def __str__(self, indent=0):
        pad = '  ' * indent
        lines = [f'{pad}{{']
        for s in self.stmts:
            if isinstance(s, Stmt):
                lines.append(s.__str__(indent + 1))
            else:
                lines.append(f'{pad}  {s}')
        lines.append(f'{pad}}}')
        return '\n'.join(lines)


def expr_str(instr):
    """Convert an IR instruction to an expression string."""
    op = instr.opcode
    uses = instr.uses
    defs = instr.defs

    def u(i):
        """Get i-th use or return '0' if missing."""
        if i < len(uses):
            return str(uses[i])
        return '0'

    def d(i):
        """Get i-th def or return 't0' if missing."""
        if i < len(defs):
            return str(defs[i])
        return 't0'

    if op == 'addiu':
        return f'{d(0)} = {u(0)} + {u(1)}'
    elif op == 'addi':
        return f'{d(0)} = {u(0)} + {u(1)}'
    elif op == 'addu':
        return f'{d(0)} = {u(0)} + {u(1)}'
    elif op == 'sub':
        return f'{d(0)} = {u(0)} - {u(1)}'
    elif op == 'subu':
        return f'{d(0)} = {u(0)} - {u(1)}'
    elif op == 'and':
        return f'{d(0)} = {u(0)} & {u(1)}'
    elif op == 'or':
        return f'{d(0)} = {u(0)} | {u(1)}'
    elif op == 'xor':
        return f'{d(0)} = {u(0)} ^ {u(1)}'
    elif op == 'sll':
        return f'{d(0)} = {u(0)} << {u(1)}'
    elif op == 'srl':
        return f'{d(0)} = {u(0)} >> {u(1)}'
    elif op == 'sra':
        return f'{d(0)} = {u(0)} >> {u(1)}'
    elif op == 'lui':
        return f'{d(0)} = {u(0)}'
    elif op == 'lw':
        return f'{d(0)} = mem[{u(0)}]'
    elif op == 'sw':
        return f'mem[{u(1)}] = {u(0)}'
    elif op == 'lwc1':
        return f'{d(0)} = mem[{u(0)}]'
    elif op == 'swc1':
        return f'mem[{u(1)}] = {u(0)}'
    elif op == 'mfc1':
        return f'{d(0)} = {u(0)}'
    elif op == 'mtc1':
        return f'{u(0)} = {u(1)}'
    elif op == 'add.s':
        return f'{d(0)} = {u(0)} + {u(1)}'
    elif op == 'sub.s':
        return f'{d(0)} = {u(0)} - {u(1)}'
    elif op == 'mul.s':
        return f'{d(0)} = {u(0)} * {u(1)}'
    elif op == 'div.s':
        return f'{d(0)} = {u(0)} / {u(1)}'
    elif op == 'abs.s':
        return f'{d(0)} = abs({u(0)})'
    elif op == 'neg.s':
        return f'{d(0)} = -{u(0)}'
    elif op == 'mov.s':
        return f'{d(0)} = {u(0)}'
    elif op == 'jal':
        return f'{d(0)} = {instr.mnemonic}(...)'
    elif op == 'jalr':
        return f'{d(0)} = {u(0)}(...)'
    elif op == 'syscall':
        return 'syscall()'
    elif op == 'nop':
        return 'nop'
    else:
        return f'{instr.mnemonic}(...)'


def condition_str(instr):
    """Convert a branch instruction to a condition string."""
    op = instr.opcode
    uses = instr.uses
    if len(uses) >= 2:
        a, b = uses[0], uses[1]
    elif len(uses) == 1:
        a, b = uses[0], IRValue('imm', 0)
    else:
        a, b = IRValue('imm', 0), IRValue('imm', 0)

    if op == 'beq':
        return f'{a} == {b}'
    elif op == 'bne':
        return f'{a} != {b}'
    elif op == 'blez':
        return f'{a} <= 0'
    elif op == 'bgtz':
        return f'{a} > 0'
    elif op == 'bltz':
        return f'{a} < 0'
    elif op == 'bgez':
        return f'{a} >= 0'
    elif op == 'beql':
        return f'{a} == {b}'
    elif op == 'bnel':
        return f'{a} != {b}'
    elif op == 'blezl':
        return f'{a} <= 0'
    elif op == 'bgtzl':
        return f'{a} > 0'
    elif op == 'bltzl':
        return f'{a} < 0'
    elif op == 'bgezl':
        return f'{a} >= 0'
    else:
        return f'{instr.mnemonic}(...)'


class CFGStructurer:
    """Converts SSA IR CFG into structured C-like pseudocode."""
    def __init__(self, ir_blocks, blocks, edges, dom, idom, loops):
        self.ir_blocks = ir_blocks  # list of (start_vaddr, [IRInstr])
        self.blocks = blocks  # list of BasicBlock
        self.edges = edges
        self.dom = dom
        self.idom = idom
        self.loops = loops
        self.n = len(ir_blocks)

        # Map vaddr -> block index
        self.vaddr_to_idx = {}
        for i, (vaddr, _) in enumerate(ir_blocks):
            self.vaddr_to_idx[vaddr] = i

        # Build successor/predecessor lists
        self.succs = [[] for _ in range(self.n)]
        self.preds = [[] for _ in range(self.n)]
        for from_idx, to_idx, edge_type in edges:
            self.succs[from_idx].append(to_idx)
            self.preds[to_idx].append(from_idx)

        # Identify loop headers
        self.loop_headers = set()
        for loop in loops:
            self.loop_headers.add(loop['header'])

        # Track which blocks have been structured
        self.structured = set()

    def structure(self):
        """Convert the CFG into a structured statement tree."""
        # Start from entry block
        return self._structure_block(0)

    def _structure_block(self, idx):
        """Structure a basic block and its successors."""
        if idx in self.structured:
            return Stmt('nop')

        self.structured.add(idx)

        # Get the block's instructions
        _, instrs = self.ir_blocks[idx]

        # Separate non-terminator instructions from terminator
        body_instrs = []
        terminator = None
        for instr in instrs:
            if instr.opcode in ('jalr', 'jr', 'syscall', 'break', 'unk_rtype'):
                terminator = instr
            elif instr.opcode in ('beq', 'bne', 'blez', 'bgtz', 'beql', 'bnel', 'blezl', 'bgtzl'):
                terminator = instr
            elif instr.opcode in ('j', 'jal'):
                terminator = instr
            else:
                body_instrs.append(instr)

        # Build statements from body instructions
        stmts = []
        for instr in body_instrs:
            stmts.append(Stmt('expr', expr=expr_str(instr)))

        # Handle terminator
        if terminator is None:
            # Block ends without explicit terminator (fall through)
            if idx + 1 < self.n:
                next_stmt = self._structure_block(idx + 1)
                stmts.append(next_stmt)
            return BlockStmt(stmts)

        if terminator.opcode == 'j':
            target = terminator.branch_target
            if target in self.vaddr_to_idx:
                target_idx = self.vaddr_to_idx[target]
                next_stmt = self._structure_block(target_idx)
                stmts.append(next_stmt)
            return BlockStmt(stmts)

        elif terminator.opcode == 'jal':
            target = terminator.branch_target
            if target in self.vaddr_to_idx:
                target_idx = self.vaddr_to_idx[target]
                # Function call, then fall through
                call_stmt = Stmt('call', expr=expr_str(terminator))
                stmts.append(call_stmt)
                if idx + 1 < self.n:
                    next_stmt = self._structure_block(idx + 1)
                    stmts.append(next_stmt)
                return BlockStmt(stmts)
            return BlockStmt(stmts)

        elif terminator.opcode in ('jalr', 'jr', 'syscall', 'break'):
            stmts.append(Stmt('expr', expr=expr_str(terminator)))
            return BlockStmt(stmts)

        elif terminator.opcode in ('beq', 'bne', 'blez', 'bgtz', 'beql', 'bnel', 'blezl', 'bgtzl'):
            cond = condition_str(terminator)
            target = terminator.branch_target

            if target in self.vaddr_to_idx:
                target_idx = self.vaddr_to_idx[target]

                # Check if this is a loop back edge (target dominates current)
                if target_idx in self.loop_headers and self._dominates(target_idx, idx):
                    # This is a while loop - condition is checked at header
                    # Build loop body from header to current block
                    loop_body = self._build_loop_body(target_idx, idx)
                    return Stmt('while', cond=cond, body=loop_body)
                else:
                    # If/then/else
                    then_block = self._structure_block(target_idx)
                    # Fall through to next block
                    if idx + 1 < self.n:
                        else_block = self._structure_block(idx + 1)
                    else:
                        else_block = Stmt('nop')
                    return Stmt('if', cond=cond, then_block=then_block, else_block=else_block)

            return BlockStmt(stmts)

        return BlockStmt(stmts)

        return BlockStmt(stmts)

    def _dominates(self, a, b):
        """Check if block a dominates block b."""
        current = b
        while current is not None:
            if current == a:
                return True
            current = self.idom.get(current)
        return False

    def _build_loop_body(self, header_idx, back_edge_from_idx):
        """Build the body of a loop from header to back edge source."""
        # Collect all blocks in the loop body
        loop_body_blocks = set()
        stack = [back_edge_from_idx]
        while stack:
            node = stack.pop()
            if node == header_idx or node in loop_body_blocks:
                continue
            loop_body_blocks.add(node)
            for p in self.preds[node]:
                if p != header_idx:
                    stack.append(p)

        # Build statements from the body
        stmts = []
        # Process blocks in order
        visited = set()

        def emit_block(idx):
            if idx in visited or idx not in loop_body_blocks:
                return
            visited.add(idx)
            _, instrs = self.ir_blocks[idx]
            for instr in instrs:
                if instr.opcode in ('beq', 'bne', 'blez', 'bgtz', 'beql', 'bnel', 'blezl', 'bgtzl'):
                    # Branch within loop
                    target = instr.branch_target
                    if target in self.vaddr_to_idx:
                        t_idx = self.vaddr_to_idx[target]
                        if t_idx == header_idx:
                            # Loop back - don't emit, it's the loop condition
                            stmts.append(Stmt('expr', expr=f'// loop back: {condition_str(instr)}'))
                        elif t_idx in self.vaddr_to_idx.values():
                            # Forward branch within loop
                            pass
                    elif instr.opcode in ('jalr', 'jr'):
                        stmts.append(Stmt('expr', expr=expr_str(instr)))
                    else:
                        stmts.append(Stmt('expr', expr=expr_str(instr)))
                elif instr.opcode in ('j', 'jal'):
                    stmts.append(Stmt('expr', expr=expr_str(instr)))
                else:
                    stmts.append(Stmt('expr', expr=expr_str(instr)))

        # Emit blocks in order
        for i in range(len(self.ir_blocks)):
            if i in loop_body_blocks:
                emit_block(i)

        return BlockStmt(stmts)


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0018C518
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else start_vaddr + 0x400

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF CFG STRUCTURER - Decompilation to C-like Pseudocode")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print()

    # Step 1: Lift to IR
    ir_blocks = lift_and_block(data, start_vaddr, end_vaddr)
    print(f"IR blocks: {len(ir_blocks)}")

    # Step 2: Build CFG
    raw_blocks = split_into_basic_blocks(data, start_vaddr, end_vaddr)
    edges = build_cfg_edges(raw_blocks)

    # Step 3: Compute dominators
    dom, idom = compute_dominators(raw_blocks, edges)

    # Step 4: Find loops
    back_edges = find_loop_back_edges(raw_blocks, edges, idom)
    loops = []
    for from_idx, to_idx in back_edges:
        # Compute loop body
        body = set()
        stack = [from_idx]
        while stack:
            node = stack.pop()
            if node == to_idx or node in body:
                continue
            body.add(node)
            for p in range(len(raw_blocks)):
                if edges and any(f == p and t == node for f, t, _ in edges):
                    if p != to_idx:
                        stack.append(p)
        body.add(to_idx)
        loops.append({'header': to_idx, 'back_edge_from': from_idx, 'body': body})

    # Step 5: Structure CFG
    structurer = CFGStructurer(ir_blocks, raw_blocks, edges, dom, idom, loops)
    root_stmt = structurer.structure()

    print("\n" + "=" * 72)
    print("STRUCTURED PSEUDOCODE")
    print("=" * 72)
    print(root_stmt.__str__())


if __name__ == '__main__':
    main()
