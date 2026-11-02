#!/usr/bin/env python3
"""
ELF tooling: C code emitter - convert structured IR to compilable C code.

Takes the structured pseudocode from elf_cfg_structurer.py and emits
compilable C code with:
- Variable declarations for all virtual registers
- Memory array for ELF data access
- Proper function structure
- Memory access as pointer dereferences
- Proper C expression syntax (MIPS assembly -> C conversion)

Usage:
    python elf_c_emitter.py [elf] [start_vaddr] [end_vaddr] [output.c]

Defaults:
    elf    = source_data/SLUS_214.42
    start  = 0x0018C518 (main loop)
    end    = start + 0x400
    output = decompiled.c
"""
import struct
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from elf_cfg_structurer import CFGStructurer, Stmt, BlockStmt, expr_str, condition_str
from elf_cfg_builder import (
    split_into_basic_blocks, build_cfg_edges,
    compute_dominators, find_loop_back_edges
)
from elf_ir_lifter import lift_elf, IRFunction, IRInstr, IRValue
from elf_ssa import lift_and_block, compute_dominance_frontiers, build_ssa


MEM_SIZE = 0x100000  # 1MB ELF memory space


def mips_expr_to_c(expr_str):
    """Convert a MIPS assembly expression string to C."""
    expr = expr_str.strip()
    
    # Debug: print input
    if 'mem[' in expr_str:
        print(f'DEBUG mips_expr_to_c input: {expr_str!r}', file=sys.stderr)
    
    # Handle negative hex: 0x-0000040 -> -0x40
    expr = re.sub(r'0x-0*(\d+)', r'-\1', expr)

    # Handle << 0 -> remove
    expr = re.sub(r'<< 0\b', '', expr)

    # Handle + zero -> just the register
    expr = re.sub(r'\+\s*zero\b', '', expr)

    # Handle zero + expr -> just expr
    expr = re.sub(r'^zero\s*\+\s*', '', expr)

    # Handle mem[something] -> READ32(something)
    while 'mem[' in expr:
        expr = re.sub(r'mem\[([^\]]+)\]', r'READ32(\1)', expr)

    # Handle DADDU rd,rs,rt -> rd = rs + rt
    m = re.match(r'DADDU\s+(\w+),\s*(\w+),\s*(\w+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} + {m.group(3)}'

    # Handle DADDU rd,rs,imm -> rd = rs + imm
    m = re.match(r'DADDU\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        return f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle ADDI rd,rs,imm -> rd = rs + imm
    m = re.match(r'ADDI\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        return f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle ADDIU rd,rs,imm -> rd = rs + imm
    m = re.match(r'ADDIU\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        return f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle SLTI rd,rs,imm -> rd = (rs < imm) ? 1 : 0
    m = re.match(r'SLTI\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        return f'{m.group(1)} = ({m.group(2)} < {val}) ? 1 : 0'

    # Handle LUI rd,imm -> rd = imm
    m = re.match(r'LUI\s+(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)}'

    # Handle SLL rd,rs,imm -> rd = rs << imm
    m = re.match(r'SLL\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+|\d+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} << {m.group(3)}'

    # Handle generic function calls like "NAME(...)" -> NAME(...)
    m = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\(.*\)', expr)
    if m:
        return expr  # Keep as-is, it's a function call

    return expr


def condition_to_c(cond_str):
    """Convert a condition string to C."""
    cond = cond_str.strip()

    # Handle negative hex
    cond = re.sub(r'0x-0*(\d+)', r'-\1', cond)

    # Handle << 0
    cond = re.sub(r'<< 0\b', '', cond)

    # Handle + zero -> just the register
    cond = re.sub(r'\+\s*zero\b', '', cond)

    # Handle mem[...] -> just the inner (READ32 wraps it)
    while 'mem[' in cond:
        cond = re.sub(r'mem\[([^\]]+)\]', r'\1', cond)

    return cond


class CEmitter:
    """Converts structured IR statements to C code."""
    def __init__(self):
        self.vars = set()  # Set of variable names (t0, t1, etc.)
        self.lines = []     # Output lines
        self.indent = 0     # Current indentation level

    def emit(self, stmt, indent=0):
        """Emit a statement tree as C code."""
        if isinstance(stmt, BlockStmt):
            self._emit_block(stmt, indent)
        elif isinstance(stmt, Stmt):
            self._emit_stmt(stmt, indent)
        else:
            self._emit_line(f'/* unknown statement type: {type(stmt)} */', indent)

    def _emit_block(self, block, indent=0):
        """Emit a block of statements."""
        pad = '  ' * indent
        self._emit_line(f'{pad}{{', indent)
        for s in block.stmts:
            if isinstance(s, Stmt):
                self._emit_stmt(s, indent + 1)
            else:
                self._emit_line(f'{pad}  /* {s} */', indent + 1)
        self._emit_line(f'{pad}}}', indent)

    def _emit_stmt(self, stmt, indent=0):
        """Emit a single statement."""
        pad = '  ' * indent
        kind = stmt.kind

        if kind == 'expr':
            expr = mips_expr_to_c(stmt.expr)
            self._emit_line(f'{pad}{expr};', indent)
        elif kind == 'assign':
            lhs = mips_expr_to_c(stmt.lhs) if '=' not in stmt.lhs else stmt.lhs
            rhs = mips_expr_to_c(stmt.rhs)
            self._emit_line(f'{pad}{lhs} = {rhs};', indent)
        elif kind == 'if':
            cond = condition_to_c(stmt.cond)
            self._emit_line(f'{pad}if ({cond}) {{', indent)
            self._emit_stmt(stmt.then_block, indent + 1)
            if stmt.else_block:
                self._emit_line(f'{pad}}} else {{', indent)
                self._emit_stmt(stmt.else_block, indent + 1)
            self._emit_line(f'{pad}}}', indent)
        elif kind == 'while':
            cond = condition_to_c(stmt.cond)
            self._emit_line(f'{pad}while ({cond}) {{', indent)
            self._emit_stmt(stmt.body, indent + 1)
            self._emit_line(f'{pad}}}', indent)
        elif kind == 'return':
            self._emit_line(f'{pad}return {stmt.expr};', indent)
        elif kind == 'call':
            self._emit_line(f'{pad}{stmt.expr};', indent)
        elif kind == 'nop':
            self._emit_line(f'{pad};', indent)
        elif kind == 'block':
            self._emit_block(stmt, indent)
        else:
            self._emit_line(f'{pad}// unknown: {kind}', indent)

    def _emit_line(self, text, indent=0):
        pad = '  ' * indent
        self.lines.append(f'{pad}{text}')

    def collect_vars(self, stmt):
        """Recursively collect all variable names used in statements."""
        if isinstance(stmt, BlockStmt):
            for s in stmt.stmts:
                self.collect_vars(s)
        elif isinstance(stmt, Stmt):
            kind = stmt.kind
            if kind == 'expr':
                self._extract_vars_from_expr(stmt.expr)
            elif kind == 'assign':
                self._extract_vars_from_expr(stmt.lhs)
                self._extract_vars_from_expr(stmt.rhs)
            elif kind == 'if':
                self._extract_vars_from_expr(stmt.cond)
                self.collect_vars(stmt.then_block)
                if stmt.else_block:
                    self.collect_vars(stmt.else_block)
            elif kind == 'while':
                self._extract_vars_from_expr(stmt.cond)
                self.collect_vars(stmt.body)
            elif kind == 'call':
                self._extract_vars_from_expr(stmt.expr)
            elif kind == 'expr':
                self._extract_vars_from_expr(stmt.expr)
            elif kind == 'return':
                self._extract_vars_from_expr(stmt.expr)

    def _extract_vars_from_expr(self, expr):
        """Extract variable names from an expression string."""
        for m in re.finditer(r'\bt(\d+)\b', expr):
            self.vars.add(f't{m.group(1)}')
        # Find memory access patterns mem[...]
        for m in re.finditer(r'mem\[([^\]]+)\]', expr):
            inner = m.group(1)
            self._extract_vars_from_expr(inner)

    def emit_c(self, root_stmt, function_name='decompiled_main'):
        """Emit complete C code."""
        self.lines = []

        # Collect all variables used
        self.collect_vars(root_stmt)

        # Sort variables by number
        sorted_vars = sorted(self.vars, key=lambda v: int(v[1:]))

        # Header
        self._emit_line('#include <stdint.h>')
        self._emit_line('#include <stdio.h>')
        self._emit_line('#include <string.h>')
        self._emit_line('')
        self._emit_line(f'#define MEM_SIZE 0x{MEM_SIZE:X}')
        self._emit_line('static uint8_t mem[MEM_SIZE];')
        self._emit_line('')
        self._emit_line('#define READ32(addr) (*(uint32_t*)(mem + (addr)))')
        self._emit_line('#define WRITE32(addr, val) (*(uint32_t*)(mem + (addr)) = (val))')
        self._emit_line('')

        # Variable declarations
        if sorted_vars:
            decls = ', '.join(sorted_vars)
            self._emit_line(f'uint32_t {decls};')
            self._emit_line('')

        # Main function
        self._emit_line(f'int {function_name}(void) {{')
        self.emit(root_stmt, 1)
        self._emit_line('return 0;')
        self._emit_line('}')

        return '\n'.join(self.lines)


def emit_c_from_ir(ir_blocks, blocks, edges, dom, idom, loops, output_path=None):
    """Lift ELF to IR, build SSA, structure CFG, and emit C code."""
    from elf_cfg_structurer import CFGStructurer

    n = len(ir_blocks)

    # Build structurer
    structurer = CFGStructurer(ir_blocks, blocks, edges, dom, idom, loops)

    # Structure the CFG
    root_stmt = structurer.structure()

    # Emit C code
    emitter = CEmitter()
    c_code = emitter.emit_c(root_stmt, function_name='decompiled_main')

    if output_path:
        Path(output_path).write_text(c_code + '\n')
        print(f'Wrote C code to {output_path}')

    return c_code


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0018C518
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else start_vaddr + 0x400
    output_path = sys.argv[4] if len(sys.argv) > 4 else 'decompiled.c'

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF C CODE EMITTER")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print(f"Output: {output_path}")
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
        body = set()
        stack = [from_idx]
        while stack:
            node = stack.pop()
            if node == to_idx or node in body:
                continue
            body.add(node)
            for p_idx in range(len(raw_blocks)):
                if any(f == p_idx and t == node for f, t, _ in edges):
                    if p_idx != to_idx:
                        stack.append(p_idx)
        body.add(to_idx)
        loops.append({'header': to_idx, 'back_edge_from': from_idx, 'body': body})

    # Step 5: Structure and emit C
    emit_c_from_ir(ir_blocks, raw_blocks, edges, dom, idom, loops, output_path)


if __name__ == '__main__':
    main()
