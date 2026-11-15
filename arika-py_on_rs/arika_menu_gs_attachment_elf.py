"""Bounded EU-beta ELF scan for menu sprite attachment *initializer* flags.

This scans direct JAL 0x2FD8F0 instructions in the ELF menu-code region
0x370000..0x3B0000. It recognizes only a strict, consecutive literal
argument pattern; every other call remains UNKNOWN. It does not follow
indirect calls, pointer aliases, later setter calls, or actual GS draws.

Run against a user-owned SLES_541.61 (never committed to Git):
  python arika_menu_gs_attachment_elf.py /path/to/SLES_541.61
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

from arika_menu_gs_attachment import (
    NATIVE_MENU_ATTACHMENT_SITES, SAMPLER_SETTER_ADDRESS,
    STATIC_ATTACHMENT_FLAGS,
)


EU_BETA_SHA256 = (
    '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
)
ELF_LOAD_BIAS = 0xfff80
MENU_START = 0x370000
MENU_STOP = 0x3b0000
JAL_SETTER = 0x0c000000 | (SAMPLER_SETTER_ADDRESS >> 2)
ZERO_A2 = 0x0000302d
ZERO_A3 = 0x0000382d
ONE_A3 = 0x24070001
ZERO_A4 = 0x0000402d
ZERO_A5 = 0x0000482d


def classify_literal_attachment_words(before_a2, before_a3, before_a4,
                                      delay_a5):
    """Classify only native argument words with no intervening instructions.

    In the recovered common calling sequence, a2/a3/a4 are set in
    three instructions immediately before JAL, and a5 is set in
    the call's delay slot. Anything else is unresolved.
    """
    if (before_a2 != ZERO_A2 or before_a4 != ZERO_A4 or
            delay_a5 != ZERO_A5):
        return None
    if before_a3 == ONE_A3:
        return (0, 1, 0, 0)
    if before_a3 == ZERO_A3:
        return (0, 0, 0, 0)
    return None


def scan_menu_sprite_attachments(elf):
    """Return literal argument counts for the exact user-owned EU-beta ELF."""
    if not isinstance(elf, bytes) or hashlib.sha256(elf).hexdigest() != EU_BETA_SHA256:
        raise ValueError('requires exact EU-beta SLES_541.61 SHA-256')
    known_sites = {entry[0]: (entry[1], entry[2])
                   for entry in NATIVE_MENU_ATTACHMENT_SITES}

    def word(va):
        return struct.unpack_from('<I', elf, va - ELF_LOAD_BIAS)[0]

    result = []
    for addr in range(MENU_START, MENU_STOP, 4):
        if word(addr) != JAL_SETTER:
            continue
        flags = classify_literal_attachment_words(
            word(addr - 12), word(addr - 8), word(addr - 4),
            word(addr + 4))
        if flags is None:
            kind = 'unknown'
        else:
            kind = 'linear' if flags[1] else 'nearest'
        entry, owner = known_sites.get(addr, (None, None))
        if entry is not None and flags != STATIC_ATTACHMENT_FLAGS:
            raise ValueError('known native attachment initializer has changed')
        result.append({
            'callsite': hex(addr),
            'sampler_bytes': list(flags) if flags is not None else None,
            'initial_filter': kind,
            'clamp_flag_if_bound': (1 if flags[2] == 0 else 0)
                                   if flags is not None else None,
            'known_resource_entry': entry,
            'known_owner': owner,
        })

    summary = {
        'elf_sha256': EU_BETA_SHA256,
        'scan_range': [hex(MENU_START), hex(MENU_STOP)],
        'direct_setter_calls': len(result),
        'literal_linear': sum(site['initial_filter'] == 'linear'
                              for site in result),
        'literal_nearest': sum(site['initial_filter'] == 'nearest'
                               for site in result),
        'unclassified': sum(site['initial_filter'] == 'unknown'
                            for site in result),
        'limitations': (
            'Literal initializer calls only; not runtime texture bindings, '
            'resource validity, texture records or active GS filtering.',
        ),
        'sites': result,
    }
    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path, help='user-owned EU-beta ELF')
    parser.add_argument('--only-nearest', action='store_true',
                        help='print just the verified literal nearest sites')
    args = parser.parse_args()
    try:
        result = scan_menu_sprite_attachments(args.elf.read_bytes())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.only_nearest:
        result['sites'] = [site for site in result['sites']
                           if site['initial_filter'] == 'nearest']
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
