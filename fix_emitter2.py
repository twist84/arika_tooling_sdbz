import re

with open('elf_tooling/elf_c_emitter.py', 'r') as f:
    content = f.read()

# Find the function
start = content.find('def mips_expr_to_c(expr_str):')
end = content.find('\ndef condition_to_c', start)

print(f"Found mips_expr_to_c at {start}-{end}")

new_func = '''def mips_expr_to_c(expr_str):
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
        expr = f'{m.group(1)} = {m.group(2)} + {m.group(3)}'

    # Handle DADDU rd,rs,imm -> rd = rs + imm
    m = re.match(r'DADDU\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        expr = f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle ADDI rd,rs,imm -> rd = rs + imm
    m = re.match(r'ADDI\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        expr = f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle ADDIU rd,rs,imm -> rd = rs + imm
    m = re.match(r'ADDIU\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        if val.startswith('0x-'):
            val = f'-{val[3:]}'
        expr = f'{m.group(1)} = {m.group(2)} + {val}'

    # Handle SLTI rd,rs,imm -> rd = (rs < imm) ? 1 : 0
    m = re.match(r'SLTI\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        val = m.group(3)
        expr = f'{m.group(1)} = ({m.group(2)} < {val}) ? 1 : 0'

    # Handle LUI rd,imm -> rd = imm
    m = re.match(r'LUI\s+(\w+),\s*(0x[\da-fA-F]+)', expr)
    if m:
        expr = f'{m.group(1)} = {m.group(2)}'

    # Handle SLL rd,rs,imm -> rd = rs << imm
    m = re.match(r'SLL\s+(\w+),\s*(\w+),\s*(0x[\da-fA-F]+|\d+)', expr)
    if m:
        expr = f'{m.group(1)} = {m.group(2)} << {m.group(3)}'

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

    return expr'''

content = content[:start] + new_func + content[end:]

with open('elf_tooling/elf_c_emitter.py', 'w') as f:
    f.write(content)

print('Done - function replaced')
