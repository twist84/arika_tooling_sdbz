"""Validate all 37 original EU-beta 0x3F1C40 factory-provider callsites.

No game executable bytes or disassembly are distributed. For exact-ELF
verification provide the user-owned EU beta SLES_541.61, never EU retail.

These provider JAL sites can invoke BSS factories through 0x3F1C78,
but their presence in static code does not show runtime execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
ELF_BIAS = 0xFFF80
PROVIDER = 0x3F1C40
PROVIDER_FACTORY_JALR = 0x3F1C78
PROVIDER_JAL = 0x0C000000 | ((PROVIDER >> 2) & 0x03FFFFFF)
SNAPSHOT = (Path(__file__).with_name('research') /
            'native_factory_provider_calls_eu_beta.json')
REGISTRY = (Path(__file__).with_name('research') /
            'native_app_registry_eu_beta.json')


def _word(data, address):
    offset = address - ELF_BIAS
    if not isinstance(address, int) or offset < 0 or offset + 4 > len(data):
        raise ValueError('ELF instruction address outside mapped segment')
    return struct.unpack_from('<I', data, offset)[0]


def verify_provider_audit(data, snapshot, canonical_registry):
    """Cross-check snapshot, canonical 110 calls and exact binary opcodes."""
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('exact EU-beta ELF SHA-256 required')
    if (snapshot['elf_sha256'] != ELF_SHA256 or
            canonical_registry['elf_sha256'] != ELF_SHA256 or
            snapshot['provider_entrypoint'] != PROVIDER or
            snapshot['provider_indirect_factory_callsite'] !=
            PROVIDER_FACTORY_JALR or
            snapshot['registered_application_count'] != 47 or
            snapshot['provider_callsite_count'] != 37):
        raise ValueError('inconsistent provider metadata')
    if _word(data, PROVIDER_FACTORY_JALR) != 0x0040F809:
        raise ValueError('provider indirect factory JALR mismatch')

    names = {entry['id']: entry['class_name']
             for entry in canonical_registry['applications']}
    if set(names) != set(range(1, 48)):
        raise ValueError('incomplete canonical registry')
    original = {edge['callsite'] for edge in canonical_registry['callsites']
                if edge['api'] == 'factory_lookup'}
    if len(original) != 37:
        raise ValueError('canonical factory-provider count changed')

    observed = set()
    kinds = {'literal': 0, 'child_id_byte': 0,
             'pending_id_byte': 0, 'requested_child_id': 0}
    literal_ids = set()
    for row in snapshot['callsites']:
        site = row['callsite']
        argument_site = row['argument_site']
        kind = row['argument_kind']
        target_id = row['target_id']
        if site in observed or site not in original or kind not in kinds:
            raise ValueError('duplicate/invalid provider at 0x%08X' % site)
        observed.add(site)
        kinds[kind] += 1
        if (row['callee'] != PROVIDER or
                row['argument_register'] != 'a0' or
                row['call_opcode'] != PROVIDER_JAL or
                _word(data, site) != PROVIDER_JAL):
            raise ValueError('provider JAL mismatch at 0x%08X' % site)
        if (_word(data, argument_site) != row['argument_opcode']):
            raise ValueError('argument source opcode mismatch at 0x%08X' % site)
        if (row['source_application_id'] is not None or
                row['source_ownership_verified'] or
                row['factory_invoked_in_observed_runtime'] or
                row['returned_object_observed']):
            raise ValueError('unsupported runtime/source attribution claim')
        position = row['argument_position']
        if position == 'jal_delay_slot':
            if argument_site != site + 4:
                raise ValueError('JAL delay slot location mismatch')
        elif position == 'before_jal':
            if argument_site >= site or site - argument_site > 0x10:
                raise ValueError('argument-before-call location mismatch')
        elif position == 'branch_delay_slot':
            if argument_site > site or site - argument_site > 0x100:
                raise ValueError('branch-derived literal location mismatch')
        else:
            raise ValueError('unrecognized argument instruction position')

        opcode = row['argument_opcode']
        if kind == 'literal':
            if (type(target_id) is not int or target_id not in names or
                    opcode != (0x24040000 | target_id) or
                    row['target_class'] != names[target_id]):
                raise ValueError('literal provider ID mismatch at 0x%08X'
                                 % site)
            literal_ids.add(target_id)
        else:
            if target_id is not None or row['target_class'] is not None:
                raise ValueError('dynamic provider falsely given literal ID')
            if kind == 'requested_child_id':
                if opcode != 0x0220202D:
                    raise ValueError('forwarded ID move opcode mismatch')
            else:
                offset = 0x12 if kind == 'child_id_byte' else 0x10
                # lb a0,+0x12/+0x10(base register). Preserve exact opcode
                # for each register, rather than assuming all bases are s0.
                if (opcode >> 26 != 0x20 or
                        (opcode >> 16) & 31 != 4 or
                        (opcode & 0xFFFF) != offset):
                    raise ValueError('application field load opcode mismatch')

    if observed != original:
        raise ValueError('missing original native provider sites')
    if kinds != {'literal': 26, 'child_id_byte': 9,
                 'pending_id_byte': 1, 'requested_child_id': 1}:
        raise ValueError('provider argument classification changed')
    if snapshot['classification_counts'] != kinds:
        raise ValueError('provider summary does not match rows')
    if literal_ids != {2, 5, 6, 8, 9, 14, 15, 22}:
        raise ValueError('distinct literal provider IDs changed')
    return {
        'verified_provider_sites': len(observed),
        'verified_argument_sites': len(observed),
        'classification_counts': kinds,
        'distinct_literal_ids': sorted(literal_ids),
        'runtime_execution_proven': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--audit', type=Path, default=SNAPSHOT)
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    args = parser.parse_args()
    try:
        data = args.elf.read_bytes()
        snapshot = json.loads(args.audit.read_text(encoding='utf-8'))
        canonical = json.loads(args.registry.read_text(encoding='utf-8'))
        result = verify_provider_audit(data, snapshot, canonical)
    except (OSError, ValueError, KeyError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
