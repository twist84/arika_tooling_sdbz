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
    
    # Handle negative hex: 0x-0000040 -> -0x40
    expr = re.sub(r'0x-0*(\d+)', lambda m: '-' + m.group(1), expr)

    # Handle << 0 -> remove
    expr = re.sub(r'<< 0\b', '', expr)

    # Handle mem[something] -> READ32(something)
    while 'mem[' in expr:
        expr = re.sub(r'mem\[([^\]]+)\]', lambda m: 'READ32(' + m.group(1) + ')', expr)

    # Handle lhs = lhs + imm -> lhs += imm (or lhs = lhs - imm)
    m = re.match(r'(\w+)\s*=\s*\1\s*\+\s*(-?0x[\da-fA-F]+|-?\d+)', expr)
    if m:
        lhs = m.group(1)
        val = m.group(2)
        if val.startswith('-'):
            return f'{lhs} -= {val[1:]}'
        return f'{lhs} += {val}'

    # Handle lhs = lhs - imm -> lhs -= imm
    m = re.match(r'(\w+)\s*=\s*\1\s*-\s*(-?0x[\da-fA-F]+|-?\d+)', expr)
    if m:
        lhs = m.group(1)
        val = m.group(2)
        if val.startswith('-'):
            return f'{lhs} += {val[1:]}'
        return f'{lhs} -= {val}'

    # Handle lhs = lhs + reg -> lhs += reg
    m = re.match(r'(\w+)\s*=\s*\1\s*\+\s*(\w+)', expr)
    if m:
        lhs = m.group(1)
        rhs = m.group(2)
        return f'{lhs} += {rhs}'

    # Handle lhs = lhs - reg -> lhs -= reg
    m = re.match(r'(\w+)\s*=\s*\1\s*-\s*(\w+)', expr)
    if m:
        lhs = m.group(1)
        rhs = m.group(2)
        return f'{lhs} -= {rhs}'

    # Handle lhs = rhs + imm (different registers)
    m = re.match(r'(\w+)\s*=\s*(\w+)\s*\+\s*(-?0x[\da-fA-F]+|-?\d+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} + {m.group(3)}'

    # Handle lhs = rhs - imm (different registers)
    m = re.match(r'(\w+)\s*=\s*(\w+)\s*-\s*(-?0x[\da-fA-F]+|-?\d+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} - {m.group(3)}'

    # Handle lhs = rhs + reg (different registers)
    m = re.match(r'(\w+)\s*=\s*(\w+)\s*\+\s*(\w+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} + {m.group(3)}'

    # Handle lhs = rhs - reg (different registers)
    m = re.match(r'(\w+)\s*=\s*(\w+)\s*-\s*(\w+)', expr)
    if m:
        return f'{m.group(1)} = {m.group(2)} - {m.group(3)}'

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

    # Handle call_0xADDR -> sub_ADDR
    m = re.match(r'call_0x([\da-fA-F]+)\(\)', expr)
    if m:
        return f'sub_{m.group(1)}()'

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

    # Final cleanup: handle + zero
    expr = re.sub(r'\+\s*zero\b', '', expr)
    # Handle zero + expr -> just expr
    expr = re.sub(r'^zero\s*\+\s*', '', expr)
    # Clean up extra spaces
    expr = re.sub(r'\s+', ' ', expr).strip()

    return expr


def condition_to_c(cond_str):
    """Light cleanup of condition strings."""
    if not cond_str or not isinstance(cond_str, str):
        return str(cond_str)
    cond = cond_str.strip()
    cond = re.sub(r'0x-([0-9a-fA-F]+)', r'-0x\1', cond)
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

    def _emit_block(self, block, indent=0, braces=True):
        """Emit a block of statements. braces=False when already inside if/while."""
        pad = '  ' * indent
        if braces:
            self._emit_line(f'{pad}{{', indent)
            inner = indent + 1
        else:
            inner = indent
        for s in block.stmts:
            if isinstance(s, Stmt):
                self._emit_stmt(s, inner)
            else:
                self._emit_line(f'{"  " * inner}/* {s} */', inner)
        if braces:
            self._emit_line(f'{pad}}}', indent)

    def _emit_body(self, stmt, indent):
        """Emit then/else/while body without adding another brace layer."""
        if isinstance(stmt, BlockStmt):
            self._emit_block(stmt, indent, braces=False)
        else:
            self._emit_stmt(stmt, indent)

    def _emit_stmt(self, stmt, indent=0):
        """Emit a single statement."""
        pad = '  ' * indent
        kind = stmt.kind

        if kind == 'expr':
            expr = mips_expr_to_c(stmt.expr)
            if not expr or expr == ';':
                return
            stripped = expr.rstrip()
            if stripped.startswith('/*') and stripped.endswith('*/'):
                self._emit_line(f'{pad}{expr}', indent)
            elif stripped.endswith(';') or '; /*' in stripped or stripped.endswith('*/'):
                # Already terminated, or statement + trailing comment
                self._emit_line(f'{pad}{expr}', indent)
            else:
                self._emit_line(f'{pad}{expr};', indent)
        elif kind == 'assign':
            lhs = mips_expr_to_c(stmt.lhs) if '=' not in stmt.lhs else stmt.lhs
            rhs = mips_expr_to_c(stmt.rhs)
            self._emit_line(f'{pad}{lhs} = {rhs};', indent)
        elif kind == 'if':
            cond = condition_to_c(stmt.cond)
            self._emit_line(f'{pad}if ({cond}) {{', indent)
            self._emit_body(stmt.then_block, indent + 1)
            else_b = stmt.else_block
            # Skip empty / nop-only else
            has_else = False
            if else_b is not None:
                if isinstance(else_b, BlockStmt) and else_b.stmts:
                    has_else = True
                elif isinstance(else_b, Stmt) and else_b.kind not in ('nop',):
                    has_else = True
            if has_else:
                self._emit_line(f'{pad}}} else {{', indent)
                self._emit_body(else_b, indent + 1)
            self._emit_line(f'{pad}}}', indent)
        elif kind == 'while':
            cond = condition_to_c(stmt.cond)
            self._emit_line(f'{pad}while ({cond}) {{', indent)
            self._emit_body(stmt.body, indent + 1)
            self._emit_line(f'{pad}}}', indent)
        elif kind == 'return':
            self._emit_line(f'{pad}return {stmt.expr};', indent)
        elif kind == 'call':
            expr = mips_expr_to_c(stmt.expr)
            self._emit_line(f'{pad}{expr};', indent)
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
        """Extract MIPS register / temp names from an expression string."""
        if not expr or not isinstance(expr, str):
            return
        # Real MIPS register names + any tN leftovers
        for m in re.finditer(
            r'\b(zero|at|v0|v1|a0|a1|a2|a3|t0|t1|t2|t3|t4|t5|t6|t7|'
            r's0|s1|s2|s3|s4|s5|s6|s7|t8|t9|k0|k1|gp|sp|fp|ra|t\d+)\b',
            expr
        ):
            name = m.group(1)
            if name != 'zero':  # constant, no need to declare
                self.vars.add(name)
        # Also scan inside READ32(...) / WRITE32(...) / mem[...]
        for m in re.finditer(r'(?:READ32|WRITE32|mem)\[?\(?([^)\]]+)\)?\]?', expr):
            self._extract_vars_from_expr(m.group(1))

    def emit_c(self, root_stmt, function_name='decompiled_main'):
        """Emit complete C code."""
        self.lines = []

        # Collect all variables used
        self.collect_vars(root_stmt)

        # Prefer canonical register order, then any extras
        REG_ORDER = [
            'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
            't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
            's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
            't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'
        ]
        ordered = [r for r in REG_ORDER if r in self.vars]
        extras = sorted(self.vars - set(ordered))
        sorted_vars = ordered + extras

        # Header
        self._emit_line('#include <stdint.h>')
        self._emit_line('#include <stdio.h>')
        self._emit_line('#include <string.h>')
        self._emit_line('')
        self._emit_line(f'#define MEM_SIZE 0x{MEM_SIZE:X}')
        self._emit_line('static uint8_t mem[MEM_SIZE];')
        self._emit_line('')
        self._emit_line('#define READ32(addr) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))))')
        self._emit_line('#define WRITE32(addr, val) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))) = (val))')
        self._emit_line('')

        # Variable declarations
        if sorted_vars:
            decls = ', '.join(sorted_vars)
            self._emit_line(f'uint32_t {decls};')
            self._emit_line('')

        # Main function
        self._emit_line(f'int {function_name}(void) {{')
        if isinstance(root_stmt, BlockStmt):
            self._emit_block(root_stmt, 1, braces=False)
        else:
            self.emit(root_stmt, 1)
        self._emit_line('  return 0;')
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


def _default_elf():
    """Resolve default ELF path relative to this script."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / 'source_data' / 'SLUS_214.42',
        here / 'source_data' / 'SLUS_214.42',
        Path('source_data/SLUS_214.42'),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return str(candidates[0])


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else _default_elf()
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
