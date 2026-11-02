#!/usr/bin/env python3
"""Parse PS2 ELF (SLUS_214.42) headers, program headers, and section headers."""
import struct
from pathlib import Path


def parse_elf(path):
    data = Path(path).read_bytes()

    if data[0:4] != b'\x7fELF':
        raise ValueError("not an ELF file")

    ei_class = data[4]
    ei_data = data[5]
    endian = '<' if ei_data == 1 else '>'
    e_type = struct.unpack_from(f'{endian}H', data, 0x10)[0]
    e_machine = struct.unpack_from(f'{endian}H', data, 0x12)[0]
    e_entry = struct.unpack_from(f'{endian}I', data, 0x18)[0]
    e_phoff = struct.unpack_from(f'{endian}I', data, 0x1C)[0]
    e_shoff = struct.unpack_from(f'{endian}I', data, 0x20)[0]
    e_ehsize = struct.unpack_from(f'{endian}H', data, 0x28)[0]
    e_phentsize = struct.unpack_from(f'{endian}H', data, 0x2A)[0]
    e_phnum = struct.unpack_from(f'{endian}H', data, 0x2C)[0]
    e_shentsize = struct.unpack_from(f'{endian}H', data, 0x2E)[0]
    e_shnum = struct.unpack_from(f'{endian}H', data, 0x30)[0]
    e_shstrndx = struct.unpack_from(f'{endian}H', data, 0x32)[0]

    print(f"ELF: class={ei_class} endian={'little' if ei_data == 1 else 'big'}")
    print(f"  type={e_type} machine={e_machine} entry=0x{e_entry:08X}")
    print(f"  phoff=0x{e_phoff:X} phnum={e_phnum} phentsize={e_phentsize}")
    print(f"  shoff=0x{e_shoff:X} shnum={e_shnum} shentsize={e_shentsize} shstrndx={e_shstrndx}")

    # Program headers
    print("\n=== Program Headers ===")
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from(f'{endian}I', data, off)[0]
        p_offset = struct.unpack_from(f'{endian}I', data, off + 4)[0]
        p_vaddr = struct.unpack_from(f'{endian}I', data, off + 8)[0]
        p_paddr = struct.unpack_from(f'{endian}I', data, off + 0xC)[0]
        p_filesz = struct.unpack_from(f'{endian}I', data, off + 0x10)[0]
        p_memsz = struct.unpack_from(f'{endian}I', data, off + 0x14)[0]
        p_flags = struct.unpack_from(f'{endian}I', data, off + 0x18)[0]
        p_align = struct.unpack_from(f'{endian}I', data, off + 0x1C)[0]
        print(f"  [{i:3d}] type=0x{p_type:02X} off=0x{p_offset:06X} vaddr=0x{p_vaddr:08X}")
        print(f"         filesz=0x{p_filesz:06X} memsz=0x{p_memsz:06X} flags=0x{p_flags:02X} align=0x{p_align:04X}")

    # Section headers
    print("\n=== Section Headers ===")
    if e_shnum > 0 and e_shoff > 0:
        shstr_off = e_shoff + e_shstrndx * e_shentsize
        shstr_offset = struct.unpack_from(f'{endian}I', data, shstr_off + 0x14)[0]
        shstr_size = struct.unpack_from(f'{endian}I', data, shstr_off + 0x18)[0]
        shstr_data = data[shstr_offset:shstr_offset + shstr_size]

        for i in range(e_shnum):
            off = e_shoff + i * e_shentsize
            name_offset = struct.unpack_from(f'{endian}I', data, off)[0]
            sh_type = struct.unpack_from(f'{endian}I', data, off + 4)[0]
            sh_flags = struct.unpack_from(f'{endian}I', data, off + 8)[0]
            sh_addr = struct.unpack_from(f'{endian}I', data, off + 0xC)[0]
            sh_offset = struct.unpack_from(f'{endian}I', data, off + 0x10)[0]
            sh_size = struct.unpack_from(f'{endian}I', data, off + 0x14)[0]
            name = shstr_data[name_offset:].split(b'\x00')[0].decode('ascii', errors='replace')
            print(f"  [{i:3d}] {name:<20} type=0x{sh_type:02X} addr=0x{sh_addr:06X} offset=0x{sh_offset:06X} size=0x{sh_size:06X}")

    return data


def file_to_vaddr(file_off):
    """Convert file offset to virtual address for this ELF."""
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    """Convert virtual address to file offset for this ELF."""
    return vaddr - 0x100000 + 0x80


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    parse_elf(path)
