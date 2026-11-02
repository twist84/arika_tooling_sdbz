#!/usr/bin/env python3
"""
ELF tooling for Super Dragon Ball Z script command resolution.

Discovers script command behavior by:
1. Scanning ELF code for JAL instructions that register commands (0x2F9DB8-0x2FAD48)
2. Disassembling each command constructor function
3. Extracting JAL targets (called functions) and GP-relative data accesses
4. Producing a command ID -> behavior mapping

Usage:
    python elf_script_cmds.py [elf_path] [output.json]
"""
import struct
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    """Convert file offset to virtual address for this ELF."""
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    """Convert virtual address to file offset for this ELF."""
    return vaddr - 0x100000 + 0x80


def find_command_refs(data):
    """
    Find all script command constructor references in ELF code.
    
    Scans for JAL instructions in range 0x2F9DB8-0x2FAD48 that call
    command constructor functions. Returns list of (command_id, vaddr) pairs.
    """
    code_start = 0x2F9DB8
    code_end = 0x2FAD48
    results = []
    
    for off in range(code_start, code_end - 4, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            results.append(dict(command_id=len(results), vaddr=target_vaddr,
                                file_off=vaddr_to_file(target_vaddr),
                                registration_vaddr=vaddr))
    return results


def disassemble_function(data, start_file_off, max_instructions=300):
    """
    Disassemble a function starting at start_file_off.
    
    Stops at JR $RA or when max_instructions reached.
    """
    instructions = []
    off = start_file_off
    count = 0
    
    while off < len(data) - 4 and count < max_instructions:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        
        instructions.append(dict(vaddr=vaddr, file_off=off, word=word,
                                 mnemonic=info.get('mnemonic', f'unk_op_0x{word>>26:02X}'),
                                 op=info.get('op'),
                                 rs=info.get('rs'), rt=info.get('rt'),
                                 rd=info.get('rd'), imm=info.get('imm'),
                                 target=info.get('target'),
                                 branch=info.get('branch'), reg=info.get('reg')))
        
        # Stop at JR $RA
        if info.get('branch') == 'indirect' and info.get('reg') == 31:
            break
            
        off += 4
        count += 1
    
    return instructions


def extract_calls_and_data_refs(instructions):
    """
    Extract JAL targets and GP-relative data references from instructions.
    """
    jal_targets = []
    gp_refs = []
    lui_ori_pairs = []
    
    i = 0
    while i < len(instructions):
        instr = instructions[i]
        op = instr['op']
        
        # JAL - direct call
        if op == 0x03:
            jal_targets.append(dict(vaddr=instr['vaddr'], target=instr['target']))
        
        # LUI followed by ORI - address construction
        if op == 0x0F:  # LUI
            upper = instr['imm']
            rt = instr['rt']
            if i + 1 < len(instructions):
                next_instr = instructions[i + 1]
                if next_instr['op'] == 0x0D and next_instr['rt'] == rt:  # ORI
                    lower = next_instr['imm']
                    full_addr = (upper << 16) | lower
                    lui_ori_pairs.append(dict(vaddr=instr['vaddr'],
                                              full_addr=full_addr,
                                              rt=rt))
                    i += 2
                    continue
        
        # GP-relative memory access
        if op in (0x23, 0x2B):  # LW/SW
            if instr['rs'] == 28:  # $gp
                gp_refs.append(dict(vaddr=instr['vaddr'],
                                    op='LW' if op == 0x23 else 'SW',
                                    offset=instr['imm'],
                                    rt=instr['rt']))
        
        i += 1
    
    return jal_targets, gp_refs, lui_ori_pairs


def resolve_command_names(data):
    """
    Resolve script command behavior by disassembling constructors
    and extracting their JAL targets and data references.
    
    Returns list of dicts with command_id, vaddr, jal_targets, gp_refs, etc.
    """
    cmd_refs = find_command_refs(data)
    results = []
    
    for ref in cmd_refs:
        cmd_id = ref['command_id']
        vaddr = ref['vaddr']
        file_off = ref['file_off']
        
        # Disassemble the constructor function
        instrs = disassemble_function(data, file_off)
        
        # Extract calls and data references
        jal_targets, gp_refs, lui_ori_pairs = extract_calls_and_data_refs(instrs)
        
        results.append(dict(command_id=cmd_id, vaddr=vaddr,
                           file_off=file_off,
                           constructor_size=len(instrs) * 4,
                           jal_targets=jal_targets,
                           gp_refs=gp_refs,
                           lui_ori_pairs=lui_ori_pairs,
                           instruction_count=len(instrs)))
    
    return results


def group_by_constructor(results):
    """Group commands that share the same constructor address."""
    groups = {}
    for r in results:
        vaddr = r['vaddr']
        if vaddr not in groups:
            groups[vaddr] = []
        groups[vaddr].append(r['command_id'])
    return groups


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Analyze ELF script command constructors')
    parser.add_argument('elf', help='Path to SLUS_214.42 ELF file')
    parser.add_argument('output', nargs='?', help='Output JSON file (optional)')
    parser.add_argument('--groups', action='store_true',
                        help='Group commands by shared constructor address')
    args = parser.parse_args()
    
    data = Path(args.elf).read_bytes()
    results = resolve_command_names(data)
    
    print(f"Analyzed {len(results)} command constructors from ELF:")
    print()
    
    if args.groups:
        groups = group_by_constructor(results)
        print(f"Commands grouped by constructor ({len(groups)} unique constructors):")
        for vaddr, cmd_ids in sorted(groups.items()):
            print(f"  Constructor 0x{vaddr:08X}: commands {cmd_ids}")
    else:
        for r in results:
            jal_str = ', '.join(f"0x{t['target']:08X}" for t in r['jal_targets'][:5])
            gp_str = ', '.join(f"{g['op']}0x{g['offset']:04X}(gp)" for g in r['gp_refs'][:5])
            print(f"  cmd {r['command_id']:3d}: vaddr=0x{r['vaddr']:08X} "
                  f"size={r['constructor_size']} instr={r['instruction_count']}")
            if jal_str:
                print(f"      JAL: {jal_str}")
            if gp_str:
                print(f"      GP:  {gp_str}")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.output}")
