"""Bounded EU-beta ELF scan for menu sprite attachment *initializer* flags.

This scans direct JAL 0x2FD8F0 instructions in the menu-adjacent ELF
code range 0x370000..0x3B0000, including generic routines also called
from outside the menu. It recognizes a strict literal sequence and
eleven individually audited reaching-definition paths. Anything else
remains UNKNOWN. It does not follow indirect calls, pointer aliases,
later setter calls, or active GS draws.

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

# (callsite, a2 definition, a3 definition, a4 definition, a5 definition)
# These eleven non-adjacent sites were reviewed instruction-by-instruction
# in the exact file-hash-gated ELF, including the JAL delay slot.
# This is not a generic or inferred interprocedural dataflow solver.
VERIFIED_NONCANONICAL_DEFS = (
    (0x37086c, 0x37085c, 0x37082c, 0x370834, 0x37083c),
    (0x370930, 0x370908, 0x37090c, 0x370914, 0x37091c),
    (0x37098c, 0x370968, 0x37096c, 0x370970, 0x370974),
    (0x3709ac, 0x37099c, 0x3709a0, 0x3709a4, 0x3709a8),
    (0x3727b4, 0x3727b8, 0x372794, 0x37279c, 0x3727a4),
    (0x37c53c, 0x37c528, 0x37c52c, 0x37c530, 0x37c534),
    (0x37c5bc, 0x37c5a8, 0x37c5ac, 0x37c5b0, 0x37c5b4),
    (0x37c624, 0x37c604, 0x37c60c, 0x37c610, 0x37c614),
    (0x37c754, 0x37c73c, 0x37c740, 0x37c744, 0x37c748),
    (0x37d864, 0x37d83c, 0x37d844, 0x37d84c, 0x37d868),
    (0x3810d8, 0x3810d0, 0x38103c, 0x3810d4, 0x3810dc),
)
VERIFIED_NONCANONICAL_BY_SITE = {site: (a2, a3, a4, a5)
                                  for site, a2, a3, a4, a5
                                  in VERIFIED_NONCANONICAL_DEFS}
# These routines in this *range* have external callsites; do not label
# all scanned initializers as owned by the native main menu.
EXTERNAL_CALLER_EVIDENCE = (
    (0x3707f0, 0x41665c),
    (0x370a00, 0x417ef8),
    (0x372790, 0x34266c),
    (0x372790, 0x344864),
    (0x37c470, 0x408338),
    (0x37c7c0, 0x408b28),
)
# Containing routine identities are backed by inspected function bodies
# and direct caller JALs, NOT claims of exclusive main-menu ownership.
NEAREST_ROUTINE_SITES = (
    (0x3707f0, (0x37098c,)),
    (0x370a00, (0x370a6c, 0x370b7c, 0x370be4, 0x370c08)),
    (0x372790, (0x3727b4,)),
    (0x37c470, (0x37c56c, 0x37c5bc, 0x37c624, 0x37c67c)),
    (0x37c7c0, (0x37d8d0,)),
)
NEAREST_ROUTINE_BY_SITE = {
    addr: entry
    for entry, addresses in NEAREST_ROUTINE_SITES for addr in addresses
}

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


def verify_noncanonical_reaching_defs(elf, callsite):
    """Check an explicitly audited ELF argument path; fail closed.

    The exact SHA and each defining instruction are checked; this
    preserves a precise review trail without assuming intervening
    stores or branches are harmless in an arbitrary executable.
    The path at 0x3810D8 takes the branch from 0x381040 to 0x3810C8
    with a3=1. No intermediate instruction on that path changes a3.
    """
    if not isinstance(elf, bytes) or hashlib.sha256(elf).hexdigest() != EU_BETA_SHA256:
        raise ValueError('requires exact EU-beta SLES_541.61 SHA-256')
    defs = VERIFIED_NONCANONICAL_BY_SITE.get(callsite)
    if defs is None:
        return None
    def word(va):
        return struct.unpack_from('<I', elf, va - ELF_LOAD_BIAS)[0]
    if word(callsite) != JAL_SETTER:
        raise ValueError('audited setter JAL is missing')
    a2, a3, a4, a5 = defs
    if (word(a2), word(a4), word(a5)) != (ZERO_A2, ZERO_A4, ZERO_A5):
        raise ValueError('audited noncanonical argument definitions changed')
    if word(a3) == ONE_A3:
        return (0, 1, 0, 0)
    if word(a3) == ZERO_A3:
        return (0, 0, 0, 0)
    raise ValueError('audited a3 filter-selector definition changed')


def scan_menu_sprite_attachments(elf):
    """Return literal argument counts for the exact user-owned EU-beta ELF."""
    if not isinstance(elf, bytes) or hashlib.sha256(elf).hexdigest() != EU_BETA_SHA256:
        raise ValueError('requires exact EU-beta SLES_541.61 SHA-256')
    known_sites = {entry[0]: (entry[1], entry[2])
                   for entry in NATIVE_MENU_ATTACHMENT_SITES}

    def word(va):
        return struct.unpack_from('<I', elf, va - ELF_LOAD_BIAS)[0]

    result = []
    noncanonical_verified = set()
    for addr in range(MENU_START, MENU_STOP, 4):
        if word(addr) != JAL_SETTER:
            continue
        flags = classify_literal_attachment_words(
            word(addr - 12), word(addr - 8), word(addr - 4),
            word(addr + 4))
        source = 'adjacent_literal'
        if flags is None:
            flags = verify_noncanonical_reaching_defs(elf, addr)
            if flags is not None:
                source = 'audited_reaching_definitions'
                noncanonical_verified.add(addr)
        if flags is None:
            kind = 'unknown'
            source = 'unresolved'
        else:
            kind = 'linear' if flags[1] else 'nearest'
        entry, owner = known_sites.get(addr, (None, None))
        if entry is not None and flags != STATIC_ATTACHMENT_FLAGS:
            raise ValueError('known native attachment initializer has changed')
        result.append({
            'callsite': hex(addr),
            'sampler_bytes': list(flags) if flags is not None else None,
            'proof': source,
            'argument_definition_addresses': [
                hex(address) for address in VERIFIED_NONCANONICAL_BY_SITE[addr]
            ] if addr in noncanonical_verified else None,
            'initial_filter': kind,
            'clamp_flag_if_bound': (1 if flags[2] == 0 else 0)
                                   if flags is not None else None,
            'known_resource_entry': entry,
            'known_owner': owner,
            'containing_routine_if_verified_nearest': (
                hex(NEAREST_ROUTINE_BY_SITE[addr])
                if addr in NEAREST_ROUTINE_BY_SITE
                and kind == 'nearest' else None),
        })

    if noncanonical_verified != set(VERIFIED_NONCANONICAL_BY_SITE):
        raise ValueError('audited noncanonical callsite inventory changed')
    if set(NEAREST_ROUTINE_BY_SITE) != {
            int(row['callsite'], 16)
            for row in result if row['initial_filter'] == 'nearest'}:
        raise ValueError('nearest routine provenance inventory changed')

    summary = {
        'elf_sha256': EU_BETA_SHA256,
        'scan_range': [hex(MENU_START), hex(MENU_STOP)],
        'direct_setter_calls': len(result),
        'literal_linear': sum(site['initial_filter'] == 'linear' and
                              site['proof'] == 'adjacent_literal'
                              for site in result),
        'literal_nearest': sum(site['initial_filter'] == 'nearest' and
                               site['proof'] == 'adjacent_literal'
                               for site in result),
        'audited_linear': sum(site['initial_filter'] == 'linear' and
                              site['proof'] == 'audited_reaching_definitions'
                              for site in result),
        'audited_nearest': sum(site['initial_filter'] == 'nearest' and
                               site['proof'] == 'audited_reaching_definitions'
                               for site in result),
        'total_linear': sum(site['initial_filter'] == 'linear'
                            for site in result),
        'total_nearest': sum(site['initial_filter'] == 'nearest'
                             for site in result),
        'nearest_routine_groups': [
            {'function': hex(entry), 'nearest_calls': [
                hex(a) for a in addresses]}
            for entry, addresses in NEAREST_ROUTINE_SITES
        ],
        'external_callers_in_scanned_range': [
            {'function': hex(function), 'caller': hex(caller)}
            for function, caller in EXTERNAL_CALLER_EVIDENCE
        ],
        'unclassified': sum(site['initial_filter'] == 'unknown'
                            for site in result),
        'limitations': (
            'Direct initializer calls in a menu-adjacent region, not '
            'necessarily native-menu-owned sprites.',
            'Noncanonical calls are audited site-by-site for this exact '
            'ELF and do not generalize to other binaries.',
            'No runtime texture bindings, resource validity, texture '
            'records or active GS filtering are captured.',
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
