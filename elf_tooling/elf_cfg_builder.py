#!/usr/bin/env python3
"""
ELF tooling: Control Flow Graph (CFG) builder for MIPS R5900.

Splits a function's instructions into basic blocks and builds control flow
edges (fall-through + branch/jump targets). Outputs DOT format for graph
visualization and a textual summary.

This is a foundational step toward decompilation: CFGs are required to
reconstruct if/while/for control structures from raw instructions.

Usage:
    python elf_cfg_builder.py [elf] [start_vaddr] [end_vaddr] [output.dot]

Defaults:
    elf    = source_data/SLUS_214.42
    start  = 0x0018C518 (main loop)
    end    = start + 0x400
    output = cfg.dot
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


CODE_START = 0x80
CODE_END = 0x400700


def is_branch(op):
    return op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17)


def is_jump(op):
    return op in (0x02, 0x03)


def is_indirect(op, funct=None):
    return op == 0x00 and funct in (0x08, 0x09)  # JR, JALR


def compute_branch_target(op, word, vaddr, imm_signed):
    if op == 0x03:  # JAL
        target_idx = word & 0x3FFFFFF
        return (vaddr & 0xF0000000) | (target_idx << 2)
    if op == 0x02:  # J
        target_idx = word & 0x3FFFFFF
        return (vaddr & 0xF0000000) | (target_idx << 2)
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17):
        return vaddr + 4 + (imm_signed << 2)
    return None


def find_branch_targets(data, start_off, end_off):
    """First pass: find all branch/jump target addresses within range."""
    targets = set()
    off = start_off
    while off < end_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        op = (word >> 26) & 0x3F
        imm = word & 0xFFFF
        imm_signed = imm - 0x10000 if imm & 0x8000 else imm

        if op == 0x03:  # JAL
            target_idx = word & 0x3FFFFFF
            targets.add((vaddr & 0xF0000000) | (target_idx << 2))
        elif op == 0x02:  # J
            target_idx = word & 0x3FFFFFF
            targets.add((vaddr & 0xF0000000) | (target_idx << 2))
        elif op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17):
            targets.add(vaddr + 4 + (imm_signed << 2))

        off += 4
    return targets


class BasicBlock:
    def __init__(self, start_vaddr, start_file_off):
        self.start_vaddr = start_vaddr
        self.start_file_off = start_file_off
        self.instructions = []  # list of (vaddr, file_off, word, mnemonic, info)
        self.fall_through = None  # vaddr of next block if falls through
        self.branch_target = None  # vaddr of branch target
        self.is_terminal = False  # ends in JR/JALR/syscall

    def add_instruction(self, vaddr, file_off, word, mnemonic, info):
        self.instructions.append((vaddr, file_off, word, mnemonic, info))

    def last_instruction(self):
        return self.instructions[-1] if self.instructions else None

    def label(self):
        return f"BB_{self.start_vaddr:08X}"


def split_into_basic_blocks(data, start_vaddr, end_vaddr):
    """Split [start_vaddr, end_vaddr) into basic blocks.

    Blocks end at terminators (JR/JALR/SYSCALL/BREAK/J/JAL/branches) and
    at branch targets (so every branch target starts a new block).
    """
    start_off = vaddr_to_file(start_vaddr)
    end_off = vaddr_to_file(end_vaddr)

    # First pass: find all branch targets
    branch_targets = find_branch_targets(data, start_off, end_off)

    blocks = []
    current_block = None

    off = start_off
    while off < end_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mnemonic = info.get('mnemonic', '')
        op = (word >> 26) & 0x3F
        funct = word & 0x3F
        imm = word & 0xFFFF
        imm_signed = imm - 0x10000 if imm & 0x8000 else imm

        # Start a new block at the beginning or at a branch target
        if current_block is None or vaddr in branch_targets:
            if current_block is not None and current_block.instructions:
                blocks.append(current_block)
            current_block = BasicBlock(vaddr, off)

        current_block.add_instruction(vaddr, off, word, mnemonic, info)

        # Check if this instruction terminates the block
        terminates = False
        fall_through = None
        branch_target = None

        if is_indirect(op, funct):
            current_block.is_terminal = True
            terminates = True
        elif op == 0x0C:  # SYSCALL
            current_block.is_terminal = True
            terminates = True
        elif op == 0x0D:  # BREAK
            current_block.is_terminal = True
            terminates = True
        elif is_jump(op):
            branch_target = compute_branch_target(op, word, vaddr, imm_signed)
            current_block.is_terminal = True
            terminates = True
        elif is_branch(op):
            branch_target = compute_branch_target(op, word, vaddr, imm_signed)
            fall_through = file_to_vaddr(off + 4) if off + 4 < len(data) else None
            terminates = True
        elif op == 0x00 and funct == 0x08:  # JR
            current_block.is_terminal = True
            terminates = True

        if terminates:
            current_block.fall_through = fall_through
            current_block.branch_target = branch_target
            blocks.append(current_block)
            current_block = None
        else:
            off += 4
            continue

        off += 4

    if current_block is not None and current_block.instructions:
        blocks.append(current_block)

    # Set fall-through for blocks that don't end with a terminator
    # A block that doesn't terminate falls through to the next block in sequence
    for i in range(len(blocks) - 1):
        block = blocks[i]
        if not block.is_terminal and block.fall_through is None:
            next_block = blocks[i + 1]
            block.fall_through = next_block.start_vaddr

    return blocks


def build_cfg_edges(blocks):
    """Build CFG edges from basic blocks."""
    vaddr_to_block = {}
    for i, block in enumerate(blocks):
        vaddr_to_block[block.start_vaddr] = i

    edges = []
    for i, block in enumerate(blocks):
        # Fall-through edge (to next sequential block or explicit target)
        if block.fall_through is not None:
            target_idx = vaddr_to_block.get(block.fall_through)
            if target_idx is not None:
                edges.append((i, target_idx, 'fallthrough'))

        # Branch edge
        if block.branch_target is not None:
            target_idx = vaddr_to_block.get(block.branch_target)
            if target_idx is not None:
                edges.append((i, target_idx, 'branch'))

    return edges


def compute_dominators(blocks, edges):
    """Compute dominator sets using the iterative dataflow algorithm.

    dom(entry) = {entry}
    dom(n) = {n} ∪ ⋂_{p ∈ preds(n)} dom(p)

    Returns dict mapping block index -> set of block indices that dominate it.
    Also returns the immediate dominator (idom) dict.
    """
    n = len(blocks)
    if n == 0:
        return {}, {}

    # Build predecessor lists
    preds = [[] for _ in range(n)]
    for from_idx, to_idx, _ in edges:
        preds[to_idx].append(from_idx)

    # Initialize dominator sets
    dom = [set() for _ in range(n)]
    dom[0] = {0}  # entry block dominates itself

    # All other blocks start with all blocks
    for i in range(1, n):
        dom[i] = set(range(n))

    # Iterate until fixpoint
    changed = True
    while changed:
        changed = False
        for i in range(1, n):
            if not preds[i]:
                continue
            inter = set(range(n))
            for p in preds[i]:
                inter &= dom[p]
            new_dom = {i} | inter
            if new_dom != dom[i]:
                dom[i] = new_dom
                changed = True

    # Compute immediate dominators
    idom = {}
    for i in range(1, n):
        if not preds[i]:
            continue
        # idom(n) = the unique dominator of n that is dominated by all other dominators of n
        # i.e., d is idom(n) if d dominates n and all other dominators of n dominate d
        candidates = dom[i] - {i}
        for d in candidates:
            # d is an immediate dominator if all other dominators of n dominate d
            # i.e., for all d2 ≠ d: d2 ∈ dom[d] (d2 is in d's dominator set)
            is_idom = True
            for d2 in candidates:
                if d2 != d and d2 not in dom[d]:
                    is_idom = False
                    break
            if is_idom:
                idom[i] = d
                break

    return dom, idom


def find_loop_back_edges(blocks, edges, idom):
    """Find back edges in the CFG.

    A back edge is an edge (a → b) where b dominates a.
    The loop header is b, and the loop body contains b and all nodes
    that can reach a without going through b.
    """
    back_edges = []
    for from_idx, to_idx, edge_type in edges:
        if to_idx in idom and idom[to_idx] == from_idx:
            # This is NOT a back edge (it's the immediate dominator edge)
            continue
        if to_idx in idom:
            # Check if to_idx dominates from_idx
            if is_dominated_by(from_idx, to_idx, idom):
                back_edges.append((from_idx, to_idx))

    return back_edges


def is_dominated_by(node_idx, dominator_idx, idom):
    """Check if dominator_idx dominates node_idx using the idom chain."""
    current = node_idx
    while current is not None:
        if current == dominator_idx:
            return True
        current = idom.get(current)
    return False


def compute_loop_bodies(blocks, edges, back_edges):
    """For each back edge (a → b), compute the loop body.

    The loop body is b plus all nodes that can reach a without going through b.
    We do a reverse traversal from a through predecessors, stopping at b.
    """
    loops = []
    for from_idx, to_idx in back_edges:
        header = to_idx
        # Reverse traversal from from_idx
        body = set()
        stack = [from_idx]
        while stack:
            node = stack.pop()
            if node == header or node in body:
                continue
            body.add(node)
            # Add predecessors
            for f, t, _ in edges:
                if t == node and f != header:
                    stack.append(f)
        body.add(header)
        loops.append({
            'header': header,
            'back_edge_from': from_idx,
            'back_edge_to': to_idx,
            'body': body,
        })
    return loops


def print_dominator_info(blocks, edges, dom, idom, loops):
    print("\n" + "=" * 72)
    print("DOMINATOR ANALYSIS")
    print("=" * 72)
    print(f"{'Block':<12} {'Dominators':<30} {'IDom':<12}")
    print("-" * 72)
    for i in range(len(blocks)):
        dom_str = ','.join(f"BB_{blocks[d].start_vaddr:08X}" for d in sorted(dom[i]))
        idom_str = f"BB_{blocks[idom[i]].start_vaddr:08X}" if i in idom else "none"
        print(f"  BB_{blocks[i].start_vaddr:08X}  {dom_str:<30} {idom_str:<12}")

    print()
    print("=" * 72)
    print("LOOP ANALYSIS (back edges)")
    print("=" * 72)
    if not loops:
        print("  No loops detected.")
    else:
        for loop in loops:
            h = loop['header']
            be_from = loop['back_edge_from']
            body_str = ','.join(f"BB_{blocks[b].start_vaddr:08X}" for b in sorted(loop['body']))
            print(f"  Loop header: BB_{blocks[h].start_vaddr:08X}")
            print(f"    Back edge: BB_{blocks[be_from].start_vaddr:08X} -> BB_{blocks[h].start_vaddr:08X}")
            print(f"    Loop body ({len(loop['body'])} blocks): {body_str}")
            print()


def write_dot(blocks, edges, output_path):
    """Write CFG in DOT format."""
    lines = []
    lines.append('digraph CFG {')
    lines.append('  rankdir=TB;')
    lines.append('  node [shape=box, fontname="monospace"];')
    lines.append('')

    for i, block in enumerate(blocks):
        label_parts = [block.label()]
        for vaddr, off, word, mnemonic, info in block.instructions:
            label_parts.append(f'  0x{vaddr:08X}: {mnemonic}')
        label = '\\n'.join(label_parts)
        lines.append(f'  {block.label()} [label="{label}"];')

    lines.append('')

    for from_idx, to_idx, edge_type in edges:
        from_block = blocks[from_idx]
        to_block = blocks[to_idx]
        style = 'solid' if edge_type == 'fallthrough' else 'dashed'
        color = 'black' if edge_type == 'fallthrough' else 'red'
        lines.append(f'  {from_block.label()} -> {to_block.label()} '
                     f'[style={style}, color={color}];')

    lines.append('}')

    Path(output_path).write_text('\n'.join(lines) + '\n')
    print(f"Wrote DOT file: {output_path}")


def print_summary(blocks, edges):
    print("\n" + "=" * 72)
    print("CONTROL FLOW GRAPH SUMMARY")
    print("=" * 72)
    print(f"Basic blocks: {len(blocks)}")
    print(f"CFG edges: {len(edges)}")
    print()

    for i, block in enumerate(blocks):
        term = " (TERMINAL)" if block.is_terminal else ""
        ft = f" -> FT: BB_{block.fall_through:08X}" if block.fall_through else ""
        bt = f" -> BR: BB_{block.branch_target:08X}" if block.branch_target else ""
        print(f"  {block.label()} @ 0x{block.start_vaddr:08X} "
              f"({len(block.instructions)} insns){term}{ft}{bt}")
        for vaddr, off, word, mnemonic, info in block.instructions:
            print(f"    0x{vaddr:08X}: {mnemonic}")
        print()

    # Dominator analysis
    dom, idom = compute_dominators(blocks, edges)
    loops = compute_loop_bodies(blocks, edges, find_loop_back_edges(blocks, edges, idom))
    print_dominator_info(blocks, edges, dom, idom, loops)


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    start_vaddr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0018C518
    end_vaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else start_vaddr + 0x400
    output_path = sys.argv[4] if len(sys.argv) > 4 else 'cfg.dot'

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF CONTROL FLOW GRAPH BUILDER")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Range: 0x{start_vaddr:08X} - 0x{end_vaddr:08X}")
    print(f"Output: {output_path}")
    print()

    blocks = split_into_basic_blocks(data, start_vaddr, end_vaddr)
    edges = build_cfg_edges(blocks)

    print_summary(blocks, edges)
    write_dot(blocks, edges, output_path)


if __name__ == '__main__':
    main()
