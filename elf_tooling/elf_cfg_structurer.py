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
from elf_ir_lifter import lift_elf, IRFunction
from elf_ssa import (
    lift_and_block, compute_dominance_frontiers, build_ssa,
    IRValue, IRInstr
)


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
        # Flatten nested BlockStmts and drop pure nops for cleaner output
        flat = []
        for s in stmts:
            if isinstance(s, BlockStmt):
                flat.extend(s.stmts)
            elif isinstance(s, Stmt) and s.kind == 'nop':
                continue
            elif isinstance(s, Stmt) and s.kind == 'expr' and str(getattr(s, 'expr', '')).startswith('/* nop'):
                continue
            else:
                flat.append(s)
        super().__init__('block', stmts=flat)

    def __str__(self, indent=0):
        pad = '  ' * indent
        lines = []
        for s in self.stmts:
            if isinstance(s, Stmt):
                lines.append(s.__str__(indent))
            else:
                lines.append(f'{pad}{s}')
        return '\n'.join(lines) if lines else f'{pad};'


def _fmt_imm(v):
    """Pretty-print an immediate."""
    if not isinstance(v, int):
        return str(v)
    if v < 0:
        return f'-0x{-v:X}' if -v > 9 else str(v)
    if v < 10:
        return str(v)
    return f'0x{v:X}'


def expr_str(instr):
    """Convert an IR instruction to a clean C-like expression string."""
    op = instr.opcode
    uses = instr.uses
    defs = instr.defs

    def u(i):
        if i < len(uses):
            return str(uses[i])
        return '0'

    def d(i):
        if i < len(defs):
            return str(defs[i])
        return '_'

    # Arithmetic / logical (register and immediate forms)
    if op in ('addiu', 'addi', 'addu', 'daddu', 'daddiu'):
        rhs = u(1)
        # Collapse "x + 0" / "x + zero"
        if rhs in ('0', 'zero'):
            return f'{d(0)} = {u(0)}'
        return f'{d(0)} = {u(0)} + {rhs}'
    if op in ('sub', 'subu', 'dsub', 'dsubu'):
        return f'{d(0)} = {u(0)} - {u(1)}'
    if op in ('and', 'andi'):
        return f'{d(0)} = {u(0)} & {u(1)}'
    if op in ('or', 'ori'):
        return f'{d(0)} = {u(0)} | {u(1)}'
    if op in ('xor', 'xori'):
        return f'{d(0)} = {u(0)} ^ {u(1)}'
    if op in ('sll', 'dsll', 'sllv', 'dsllv'):
        # SLL $zero,$zero,0 is the canonical MIPS nop
        if not defs or (str(u(0)) in ('0', 'zero') and str(u(1)) in ('0', 'zero')):
            return '/* nop */'
        return f'{d(0)} = {u(0)} << {u(1)}'
    if op in ('srl', 'dsrl', 'srlv', 'dsrlv'):
        return f'{d(0)} = {u(0)} >> {u(1)}'
    if op in ('sra', 'dsra', 'srav', 'dsrav'):
        return f'{d(0)} = (int32_t){u(0)} >> {u(1)}'
    if op == 'lui':
        return f'{d(0)} = {u(0)}'
    if op == 'slt':
        return f'{d(0)} = ({u(0)} < {u(1)}) ? 1 : 0'
    if op == 'sltu':
        return f'{d(0)} = ((uint32_t){u(0)} < (uint32_t){u(1)}) ? 1 : 0'
    if op == 'slti':
        return f'{d(0)} = ({u(0)} < {u(1)}) ? 1 : 0'
    if op == 'sltiu':
        return f'{d(0)} = ((uint32_t){u(0)} < (uint32_t){u(1)}) ? 1 : 0'
    if op == 'nor':
        return f'{d(0)} = ~({u(0)} | {u(1)})'
    if op in ('mult', 'multu', 'div', 'divu'):
        return f'/* {op} {u(0)}, {u(1)} */'
    if op in ('mflo', 'mfhi'):
        return f'{d(0)} = {op}()'
    if op in ('mtlo', 'mthi'):
        return f'{op}({u(0)})'

    # Conditional moves
    if op == 'movz':
        return f'if ({u(1)} == 0) {d(0)} = {u(0)}'
    if op == 'movn':
        return f'if ({u(1)} != 0) {d(0)} = {u(0)}'

    # Memory: IRValue('mem') already prints the address expression
    if op in ('lw', 'lwu', 'lh', 'lhu', 'lb', 'lbu', 'ld', 'lq', 'lwc1', 'ldc1'):
        if op in ('lw', 'lwu', 'lwc1'):
            return f'{d(0)} = READ32({u(0)})'
        if op == 'lb':
            return f'{d(0)} = (int8_t)mem[{u(0)}]'
        if op == 'lbu':
            return f'{d(0)} = (uint8_t)mem[{u(0)}]'
        return f'{d(0)} = mem[{u(0)}]'
    if op in ('sw', 'sh', 'sb', 'sd', 'sq', 'swc1', 'sdc1'):
        return f'WRITE32({u(1)}, {u(0)})' if op in ('sw', 'swc1') else f'mem[{u(1)}] = {u(0)}'

    # Moves / COP1
    if op == 'mfc1':
        return f'{d(0)} = {u(0)}'
    if op == 'mtc1':
        return f'{u(0)} = {u(1)}'
    if op in ('add.s', 'sub.s', 'mul.s', 'div.s'):
        sym = {'add.s': '+', 'sub.s': '-', 'mul.s': '*', 'div.s': '/'}[op]
        return f'{d(0)} = {u(0)} {sym} {u(1)}'
    if op == 'abs.s':
        return f'{d(0)} = abs({u(0)})'
    if op == 'neg.s':
        return f'{d(0)} = -{u(0)}'
    if op == 'mov.s':
        return f'{d(0)} = {u(0)}'

    # Control transfer
    if op == 'jal':
        tgt = getattr(instr, 'branch_target', None)
        if tgt is not None:
            return f'call_0x{tgt:08X}()'
        return f'call({instr.mnemonic})'
    if op == 'jalr':
        site = getattr(instr, 'vaddr', 0) or 0
        return f'call({u(0)}); /* jalr @ 0x{site:08X} */'
    if op == 'jr':
        return f'goto *{u(0)}'
    if op == 'j':
        tgt = getattr(instr, 'branch_target', None)
        if tgt is not None:
            return f'goto label_0x{tgt:08X}'
        return f'goto {instr.mnemonic}'
    if op == 'syscall':
        return 'syscall()'
    if op == 'nop' or (op == 'sll' and not defs):
        return '/* nop */'
    if op == 'break':
        return 'break_exception()'

    # Fallback: keep original mnemonic for unknown ops
    return f'/* {instr.mnemonic} */'


def condition_str(instr):
    """Convert a branch instruction to a condition string."""
    op = instr.opcode
    uses = instr.uses
    if len(uses) >= 2:
        a, b = str(uses[0]), str(uses[1])
    elif len(uses) == 1:
        a, b = str(uses[0]), '0'
    else:
        a, b = '0', '0'

    # Treat "reg == 0" style cleanly
    if op in ('beq', 'beql'):
        if b in ('0', 'zero'):
            return f'{a} == 0'
        if a in ('0', 'zero'):
            return f'{b} == 0'
        return f'{a} == {b}'
    if op in ('bne', 'bnel'):
        if b in ('0', 'zero'):
            return f'{a} != 0'
        if a in ('0', 'zero'):
            return f'{b} != 0'
        return f'{a} != {b}'
    if op in ('blez', 'blezl'):
        return f'{a} <= 0'
    if op in ('bgtz', 'bgtzl'):
        return f'{a} > 0'
    if op in ('bltz', 'bltzl'):
        return f'{a} < 0'
    if op in ('bgez', 'bgezl'):
        return f'{a} >= 0'
    return f'/* {instr.mnemonic} */'


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

    BRANCH_OPS = (
        'beq', 'bne', 'blez', 'bgtz', 'beql', 'bnel', 'blezl', 'bgtzl',
        'bltz', 'bgez', 'bltzl', 'bgezl', 'bltzal', 'bgezal', 'bltzall', 'bgezall',
    )

    def structure(self):
        """Convert the CFG into a structured statement tree.

        Walks from the entry, then appends any remaining unstructured blocks
        so nothing is silently dropped.
        """
        root = self._structure_block(0)
        # Emit any blocks we never reached (disconnected / missed edges)
        extras = []
        for i in range(self.n):
            if i not in self.structured:
                va = self.ir_blocks[i][0]
                extras.append(Stmt('expr', expr=f'/* --- unreached block 0x{va:08X} --- */'))
                extras.append(self._structure_block(i))
        if extras:
            if isinstance(root, BlockStmt):
                root.stmts.extend(extras)
            else:
                root = BlockStmt([root] + extras)
        return root

    def _fallthrough_succ(self, idx):
        """Preferred sequential successor (fallthrough edge, else next index)."""
        for s in self.succs[idx]:
            # Prefer edges that were marked fallthrough in the original edge list
            for f, t, kind in self.edges:
                if f == idx and t == s and kind == 'fallthrough':
                    return s
        # Fallback: any successor that is numerically later
        later = [s for s in self.succs[idx] if s > idx]
        if later:
            return min(later)
        if idx + 1 < self.n and (idx + 1) in self.succs[idx]:
            return idx + 1
        return None

    def _structure_block(self, idx):
        """Structure a basic block and its successors."""
        if idx in self.structured:
            return Stmt('nop')

        self.structured.add(idx)
        _, instrs = self.ir_blocks[idx]

        # Split body vs terminator. Delay-slot instr after a branch stays in body.
        body_instrs = []
        terminator = None
        for instr in instrs:
            if instr.opcode in ('jalr', 'jr', 'syscall', 'break', 'unk_rtype'):
                terminator = instr
            elif instr.opcode in self.BRANCH_OPS:
                terminator = instr
            elif instr.opcode in ('j', 'jal'):
                terminator = instr
            else:
                body_instrs.append(instr)

        stmts = [Stmt('expr', expr=expr_str(instr)) for instr in body_instrs]

        # --- no terminator: pure fall-through ---
        if terminator is None:
            nxt = self._fallthrough_succ(idx)
            if nxt is not None and nxt not in self.structured:
                stmts.append(self._structure_block(nxt))
            return BlockStmt(stmts)

        # --- unconditional jump ---
        if terminator.opcode == 'j':
            target = terminator.branch_target
            if target in self.vaddr_to_idx:
                t_idx = self.vaddr_to_idx[target]
                if t_idx not in self.structured:
                    stmts.append(self._structure_block(t_idx))
                else:
                    stmts.append(Stmt('expr', expr=f'goto label_0x{target:08X}'))
            else:
                stmts.append(Stmt('expr', expr=expr_str(terminator)))
            return BlockStmt(stmts)

        # --- direct call (JAL) ---
        if terminator.opcode == 'jal':
            stmts.append(Stmt('call', expr=expr_str(terminator)))
            nxt = self._fallthrough_succ(idx)
            if nxt is not None and nxt not in self.structured:
                stmts.append(self._structure_block(nxt))
            return BlockStmt(stmts)

        # --- indirect call / return / trap ---
        if terminator.opcode in ('jalr', 'jr', 'syscall', 'break'):
            stmts.append(Stmt('expr', expr=expr_str(terminator)))
            if terminator.opcode == 'jalr':
                nxt = self._fallthrough_succ(idx)
                if nxt is not None and nxt not in self.structured:
                    stmts.append(self._structure_block(nxt))
            return BlockStmt(stmts)

        # --- conditional branch ---
        if terminator.opcode in self.BRANCH_OPS:
            cond = condition_str(terminator)
            target = terminator.branch_target
            ft = self._fallthrough_succ(idx)

            if target is not None and target in self.vaddr_to_idx:
                t_idx = self.vaddr_to_idx[target]

                # Back-edge → while loop
                is_back = (
                    (t_idx in self.loop_headers and self._dominates(t_idx, idx))
                    or (t_idx < idx and self._dominates(t_idx, idx))
                    or any(l['header'] == t_idx and l['back_edge_from'] == idx for l in self.loops)
                )
                if is_back:
                    # Structure the loop body (blocks reachable from header that
                    # can reach the back-edge source, excluding the header itself
                    # for the condition check).
                    body = self._build_loop_body(t_idx, idx)
                    # The while condition is the back-edge condition; body is
                    # everything between header and latch.
                    stmts.append(Stmt('while', cond=cond, body=body))
                    # After the loop, continue at the fall-through of the latch
                    # (or of the header's non-loop succ).
                    if ft is not None and ft not in self.structured:
                        stmts.append(self._structure_block(ft))
                    return BlockStmt(stmts)

                # Ordinary if/else
                then_block = self._structure_block(t_idx) if t_idx not in self.structured else Stmt('nop')
                else_block = (
                    self._structure_block(ft)
                    if ft is not None and ft not in self.structured
                    else Stmt('nop')
                )
                stmts.append(Stmt('if', cond=cond, then_block=then_block, else_block=else_block))
                return BlockStmt(stmts)

            # Target outside analysed range
            stmts.append(Stmt('expr', expr=f'if ({cond}) goto 0x{target:08X}' if target else f'/* {cond} */'))
            if ft is not None and ft not in self.structured:
                stmts.append(self._structure_block(ft))
            return BlockStmt(stmts)

        return BlockStmt(stmts)

    def _dominates(self, a, b):
        """Check if block a dominates block b."""
        current = b
        seen = set()
        while current is not None and current not in seen:
            if current == a:
                return True
            seen.add(current)
            current = self.idom.get(current)
        return False

    def _natural_loop(self, header_idx, latch_idx):
        """Natural loop set: header + nodes that reach latch without going through header."""
        body = {latch_idx}
        stack = [latch_idx]
        while stack:
            node = stack.pop()
            for p in self.preds[node]:
                if p not in body and p != header_idx:
                    body.add(p)
                    stack.append(p)
        body.add(header_idx)
        return body

    def _inner_loops(self, outer_body, outer_header):
        """Loops whose header is inside outer_body (properly nested)."""
        inners = []
        for loop in self.loops:
            h = loop['header']
            if h in outer_body and h != outer_header:
                # Prefer innermost: body must be subset of outer
                lb = self._natural_loop(h, loop['back_edge_from'])
                if lb <= outer_body:
                    inners.append((h, loop['back_edge_from'], lb))
        # Sort outer-first so we process outer of nested-inner pairs first... 
        # actually innermost first so they get structured before parent consumes them
        inners.sort(key=lambda x: len(x[2]))
        return inners

    def _emit_block_linear(self, idx, skip_branch_to=None, loop_header=None, loop_latch=None, loop_body=None):
        """Emit a single block's instructions as linear stmts.

        skip_branch_to: omit branch to this idx (loop-back → while cond)
        loop_*: rewrite intra-loop gotos to continue / break
        """
        stmts = []
        _, instrs = self.ir_blocks[idx]
        body = loop_body or set()
        for instr in instrs:
            if instr.opcode in self.BRANCH_OPS:
                tgt = instr.branch_target
                t_idx = self.vaddr_to_idx.get(tgt) if tgt else None
                if skip_branch_to is not None and t_idx == skip_branch_to:
                    continue
                cond = condition_str(instr)
                if t_idx is not None and loop_header is not None:
                    if t_idx == loop_header or t_idx == loop_latch:
                        stmts.append(Stmt('expr', expr=f'if ({cond}) continue'))
                    elif t_idx not in body:
                        stmts.append(Stmt('expr', expr=f'if ({cond}) break'))
                    else:
                        stmts.append(Stmt('expr', expr=f'if ({cond}) goto block_0x{tgt:08X}'))
                elif t_idx is not None:
                    stmts.append(Stmt('expr', expr=f'if ({cond}) goto block_0x{tgt:08X}'))
                else:
                    stmts.append(Stmt('expr', expr=f'if ({cond}) goto 0x{tgt:08X}'))
            elif instr.opcode == 'jalr':
                site = getattr(instr, 'vaddr', 0) or 0
                uses = instr.uses
                target_reg = str(uses[0]) if uses else '?'
                stmts.append(Stmt('expr', expr=f'call({target_reg}); /* jalr @ 0x{site:08X} */'))
            elif instr.opcode in ('j', 'jal', 'jr'):
                stmts.append(Stmt('expr', expr=expr_str(instr)))
            else:
                stmts.append(Stmt('expr', expr=expr_str(instr)))
        return stmts

    def _build_loop_body(self, header_idx, latch_idx):
        """Structure the natural loop body, nesting any inner loops as while."""
        body = self._natural_loop(header_idx, latch_idx)
        inners = self._inner_loops(body, header_idx)

        inner_header_of = {h: (h, latch, lb) for h, latch, lb in inners}
        consumed_by_inner = set()
        for h, latch, lb in inners:
            for b in lb:
                if b != h:
                    consumed_by_inner.add(b)

        def emit_opts(i):
            skip_to = header_idx if i == latch_idx else None
            return dict(
                skip_branch_to=skip_to,
                loop_header=header_idx,
                loop_latch=latch_idx,
                loop_body=body,
            )

        stmts = []
        for i in sorted(body):
            if i in consumed_by_inner:
                continue
            if i in self.structured and i != header_idx and i != latch_idx:
                if i not in inner_header_of:
                    continue

            if i in inner_header_of:
                h, ilatch, ilb = inner_header_of[i]
                _, latch_instrs = self.ir_blocks[ilatch]
                cond = '1'
                for instr in latch_instrs:
                    if instr.opcode in self.BRANCH_OPS:
                        tgt = instr.branch_target
                        if self.vaddr_to_idx.get(tgt) == h:
                            cond = condition_str(instr)
                            break
                for b in ilb:
                    self.structured.add(b)
                inner_body = self._build_loop_body(h, ilatch)
                stmts.append(Stmt('while', cond=cond, body=inner_body))
                continue

            self.structured.add(i)
            stmts.extend(self._emit_block_linear(i, **emit_opts(i)))

        return BlockStmt(stmts)


def _default_elf():
    here = Path(__file__).resolve().parent
    for c in (here.parent / 'source_data' / 'SLUS_214.42',
              here / 'source_data' / 'SLUS_214.42',
              Path('source_data/SLUS_214.42')):
        if c.is_file():
            return str(c)
    return str(here.parent / 'source_data' / 'SLUS_214.42')


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else _default_elf()
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
