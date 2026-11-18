"""Re-extract and verify the 47 native SDBZ EU-beta application registrations.

Requires the original 2006-05-02 SLES_541.61, never the retail ELF.
The checked-in JSON is metadata only; no executable bytes are distributed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
ELF_BIAS = 0xFFF80
GP = 0x4FF370
REGISTER = 0x3DFA60
TRANSITION = 0x3DFB00
CHILD = 0x3DFBD0
LOOKUP = 0x3F1C40
TABLE = 0x6217E0
REGISTRY = Path(__file__).with_name('research') / 'native_app_registry_eu_beta.json'


def _word(data, address):
    offset = address - ELF_BIAS
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('ELF address out of bounds: 0x%08X' % address)
    return struct.unpack_from('<I', data, offset)[0]


def _s16(word):
    return ((word & 0xFFFF) ^ 0x8000) - 0x8000


def _jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def _string(data, address):
    offset = address - ELF_BIAS
    if offset < 0 or offset + 96 > len(data):
        raise ValueError('class string out of bounds')
    parts = data[offset:offset + 96].split(b'\0', 1)
    if len(parts) != 2:
        raise ValueError('unterminated class string')
    return parts[0].decode('ascii')


def _factory(data, site):
    for address in range(site - 4, site - 48, -4):
        ins = _word(data, address)
        if ins >> 16 != 0x2463:
            continue
        factory = (0x3F0000 + _s16(ins)) & 0xFFFFFFFF
        if not (0x3F1C00 <= factory < 0x3F2F00):
            continue
        if any(_word(data, address + step) == 0x0060F809
               for step in (4, 8, 12)):
            return factory, address
    raise ValueError('factory not recovered at 0x%08X' % site)


def _vtables(data, ctor):
    registers = {}
    stores = []
    for address in range(ctor, ctor + 0x100, 4):
        ins = _word(data, address)
        op = ins >> 26
        source = (ins >> 21) & 31
        dest = (ins >> 16) & 31
        if op == 15:
            registers[dest] = (ins & 65535) << 16
        elif op == 9:
            if source in registers:
                registers[dest] = (registers[source] + _s16(ins)) & 0xFFFFFFFF
            else:
                registers.pop(dest, None)
        elif op == 43 and source in (16, 17):
            if _s16(ins) in (0, 4) and dest in registers:
                pointer = registers[dest]
                if 0x4F0000 <= pointer <= 0x4FFFFF:
                    stores.append((source, _s16(ins), pointer, address))
        if ins == 0x03E00008 and address > ctor + 0x18:
            break
    # Match a pair of stores to the same top-level object. A later
    # store to +0 of a nested CMenu is NOT the application's vtable.
    for owner, offset, base, site in stores:
        if offset != 0:
            continue
        for other_owner, other_offset, phase, other_site in stores:
            if (owner == other_owner and other_offset == 4 and
                    abs(other_site - site) <= 0x38):
                return base, phase, site, other_site
    raise ValueError('unresolved vtable pair at 0x%08X' % ctor)


def _name_address(data, getter):
    registers = {}
    for address in range(getter, getter + 0x20, 4):
        ins = _word(data, address)
        op = ins >> 26
        source = (ins >> 21) & 31
        dest = (ins >> 16) & 31
        if op == 15:
            registers[dest] = (ins & 65535) << 16
        elif op == 9 and source in registers:
            registers[dest] = (registers[source] + _s16(ins)) & 0xFFFFFFFF
        elif op == 35 and source == 28 and dest == 2:
            registers[2] = _word(data, GP + _s16(ins))
    return registers.get(2)


def recover(data):
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('exact EU-beta executable SHA-256 required')
    apps = []
    for site in range(0x3F15BC, 0x3F1B7C + 1, 4):
        if _word(data, site) != _jal(REGISTER):
            continue
        ins = _word(data, site + 4)
        if ins >> 16 != 0x2405:
            raise ValueError('nonliteral registered ID at 0x%08X' % site)
        app_id = ins & 0xFFFF
        factory, factory_site = _factory(data, site)
        if _word(data, site - 8) != (0xAC430000 | (0x17E0 + app_id * 4)):
            raise ValueError('factory table mismatch for ID %d' % app_id)
        ctor_site = factory + 0x20
        ctor_ins = _word(data, ctor_site)
        if ctor_ins >> 26 != 3:
            raise ValueError('missing constructor call for ID %d' % app_id)
        ctor = ((ctor_site & 0xF0000000) |
                ((ctor_ins & 0x03FFFFFF) << 2))
        base, phase, base_site, phase_site = _vtables(data, ctor)
        getter = _word(data, base + 8)
        text = _name_address(data, getter)
        if text is None:
            raise ValueError('missing class getter for ID %d' % app_id)
        name = _string(data, text)
        if not name.startswith('CApp'):
            raise ValueError('not a native application: %s' % name)
        apps.append({
            'id': app_id, 'registration_order': len(apps) + 1,
            'factory': factory, 'factory_site': factory_site,
            'registration_callsite': site, 'registration_id_site': site + 4,
            'factory_table_store_site': site - 8,
            'factory_table_index': app_id,
            'constructor': ctor, 'constructor_callsite': ctor_site,
            'base_vtable': base, 'phase_vtable': phase,
            'base_vtable_store_site': base_site,
            'phase_vtable_store_site': phase_site,
            'name_getter': getter, 'class_name_pointer': text,
            'class_name': name,
            'base_slots': {'0x%02x' % offset: _word(data, base + offset)
                           for offset in range(8, 0x58, 4)},
            'phase_slots': {'0x%02x' % offset: _word(data, phase + offset)
                            for offset in range(8, 0x30, 4)},
        })
    if (len(apps) != 47 or sorted(app['id'] for app in apps) != list(range(1, 48))
            or len(set(app['factory'] for app in apps)) != 47):
        raise ValueError('incomplete/duplicate application registrations')
    return apps


def verify(data, snapshot):
    apps = recover(data)
    expected = snapshot['applications']
    if (snapshot['elf_sha256'] != SHA256 or snapshot['application_count'] != 47 or
            len(expected) != 47 or
            snapshot['registration_order'] != [app['id'] for app in apps]):
        raise ValueError('registry header/order mismatch')
    by_id = {app['id']: app for app in expected}
    if len(by_id) != 47:
        raise ValueError('duplicate JSON application IDs')
    fields = ('id', 'registration_order', 'factory', 'factory_site',
              'registration_callsite', 'registration_id_site',
              'factory_table_store_site', 'factory_table_index',
              'constructor', 'constructor_callsite', 'base_vtable',
              'phase_vtable', 'name_getter', 'class_name_pointer',
              'class_name', 'base_slots', 'phase_slots')
    for app in apps:
        expected_app = by_id[app['id']]
        for field in fields:
            if expected_app[field] != app[field]:
                raise ValueError('ID %d ELF mismatch: %s' % (app['id'], field))
    # The base vtable's +0x30..+0x54 tail aliases the secondary
    # (this+4) vtable's ten callbacks at +0x08..+0x2C. Earlier
    # +0x30/+0x34 words after that secondary table were NOT callbacks.
    callbacks = {
        'initialize': 0x34, 'phase_2': 0x38, 'phase_3': 0x3C,
        'phase_4': 0x40, 'phase_5': 0x44,
        'phase_4_auxiliary': 0x48, 'shutdown': 0x4C,
        'recursive_auxiliary': 0x50, 'final_auxiliary': 0x54,
    }
    for app in apps:
        base = app['base_vtable']
        phase = app['phase_vtable']
        if any(_word(data, base + offset)
               for offset in (0x28, 0x2C)):
            raise ValueError('unexpected vtable gap for ID %d' % app['id'])
        for offset in range(0x08, 0x30, 4):
            if _word(data, base + offset + 0x28) != _word(data, phase + offset):
                raise ValueError('vtable callback alias mismatch for ID %d' %
                                 app['id'])
        by_role = {name: _word(data, base + offset)
                   for name, offset in callbacks.items()}
        if by_role != by_id[app['id']].get('callback_dispatch'):
            raise ValueError('callback dispatch mismatch for ID %d' % app['id'])

    lifecycle = snapshot.get('native_lifecycle')
    if not isinstance(lifecycle, dict):
        raise ValueError('missing exact native lifecycle evidence')
    for key, expected_word in lifecycle['instruction_signatures'].items():
        site = int(key, 16)
        if _word(data, site) != expected_word:
            raise ValueError('lifecycle instruction mismatch at 0x%08X' % site)
    switch = lifecycle['transition_phase_switch']
    for index, target in enumerate(switch['targets']):
        if _word(data, switch['table'] + index * 4) != target:
            raise ValueError('transition phase jump-table mismatch at index %d' %
                             index)
    for dispatch in (lifecycle['phase_virtual_dispatch'] +
                     lifecycle['other_virtual_dispatch']):
        site = dispatch['callsite']
        offset = dispatch['vt_offset']
        if _word(data, site) != 0x8F390000 | offset:
            raise ValueError('virtual dispatch mismatch at 0x%08X' % site)
    if len(lifecycle['phase_virtual_dispatch']) != 4:
        raise ValueError('incomplete phase callback dispatches')

    # ID 1's phase-3 and phase-4 callbacks address ID 2 directly.
    # These instructions demonstrate cross-app calls, NOT child ownership.
    cross_app = snapshot.get('cross_app_interactions', ())
    if len(cross_app) != 4:
        raise ValueError('incomplete ID 1 to ID 2 interaction evidence')
    for call in cross_app:
        if (call['source_id'], call['destination_id']) != (1, 2):
            raise ValueError('invalid cross-app identity')
        expected_source_slot = {3: '0x3c', 4: '0x40'}
        source_offset = expected_source_slot.get(call['source_phase'])
        if source_offset is None or (
                by_id[1]['base_slots'][source_offset] !=
                call['source_function']):
            raise ValueError('cross-app source function does not match vtable')
        mechanism = call['mechanism']
        site = call['callsite']
        if mechanism == 'factory_lookup':
            if (_word(data, site) != _jal(LOOKUP) or
                    _word(data, call['argument_site']) != 0x24040002):
                raise ValueError('cross-app factory lookup mismatch')
        elif mechanism == 'direct_method_call':
            if (_word(data, site) != _jal(call['callee']) or
                    _word(data, call['argument_site']) != 0x0040202D):
                raise ValueError('cross-app direct method call mismatch')
        elif mechanism == 'indirect_virtual_call':
            if (_word(data, site) != 0x0320F809 or
                    _word(data, call['vtable_load_site']) !=
                    (0x8F390000 | call['callback_vtable_offset']) or
                    _word(data, call['argument_site']) != 0x0040202D or
                    by_id[2]['base_slots']['0x38'] != call['callback_target']):
                raise ValueError('cross-app indirect vtable call mismatch')
        else:
            raise ValueError('unsupported cross-app dispatch mechanism')
        if call['runtime_executed'] or call['child_construction_proven']:
            raise ValueError('cross-app static request falsely marked executed')

    # Demo Main's exit target is a *field*, not a literal argument.
    # The default ID 3 and choice-3 override ID 6 are established by
    # their store instructions, but execution is still phase/flag-gated.
    demo = snapshot.get('demo_main_exit')
    if not isinstance(demo, dict) or demo['app_id'] != 6:
        raise ValueError('missing ID 6 conditional exit evidence')
    if by_id[6]['base_slots']['0x40'] != demo['update_callback']:
        raise ValueError('DemoMain update callback identity mismatch')
    if by_id[6]['base_slots']['0x34'] != demo['initialize_callback']:
        raise ValueError('DemoMain init callback identity mismatch')
    if ((demo['default_target_id'], demo['alternate_target_id']) !=
            (3, 6)):
        raise ValueError('DemoMain native target candidates mismatch')
    for key, expected_word in demo['instruction_signatures'].items():
        site = int(key, 16)
        if _word(data, site) != expected_word:
            raise ValueError('DemoMain exit instruction mismatch at 0x%08X' %
                             site)
    dynamic_exit = next(
        (edge for edge in snapshot['callsites']
         if edge['callsite'] == demo['transition_callsite']), None)
    if (dynamic_exit is None or dynamic_exit['target_id'] is not None or
            dynamic_exit['target_candidates'] != [3, 6] or
            dynamic_exit['api'] != 'transition' or
            dynamic_exit['argument_site'] != demo['dynamic_arg_site'] or
            not dynamic_exit['source_attribution_verified']):
        raise ValueError('DemoMain dynamic request edge mismatch')
    id6_exits = [edge for edge in snapshot['relationships']
                 if edge['type'] == 'conditional_native_transition_request'
                 and edge['source_id'] == 6]
    if sorted(edge['destination_id'] for edge in id6_exits) != [3, 6]:
        raise ValueError('DemoMain conditional edge set mismatch')
    if any(edge['request_executed'] for edge in id6_exits):
        raise ValueError('DemoMain requests are not runtime execution')

    fight = snapshot.get('fight_result_dispatch')
    if (not isinstance(fight, dict) or fight['source_id'] != 28 or
            fight['callback'] != by_id[28]['base_slots']['0x3c'] or
            fight['default_target_sentinel'] != 48):
        raise ValueError('missing exact FightResultMain dispatch identity')
    if (_word(data, fight['helper_callsite']) != _jal(fight['helper']) or
            _word(data, fight['dispatch_callsite']) != _jal(CHILD)):
        raise ValueError('FightResultMain helper-call chain mismatch')
    for site, word in fight['evidence_sites'].items():
        if _word(data, int(site, 16)) != word:
            raise ValueError('FightResultMain instruction mismatch at %s' % site)
    choices = fight['conditional_destinations']
    if [entry['target_id'] for entry in choices] != [29, 30, 34, 38]:
        raise ValueError('FightResultMain conditional destinations mismatch')
    for entry in choices:
        if _word(data, entry['register_load_site']) != (
                0x24100000 | entry['target_id']):
            raise ValueError('FightResultMain selected-ID word mismatch')
    fight_edge = next(
        (edge for edge in snapshot['callsites']
         if edge['callsite'] == fight['dispatch_callsite']), None)
    if (fight_edge is None or fight_edge['target_id'] is not None or
            fight_edge['api'] != 'child_request' or
            fight_edge['target_candidates'] != [29, 30, 34, 38] or
            fight_edge['sentinel_target'] != 48 or
            fight_edge['argument_site'] != fight['argument_site'] or
            not fight_edge['source_attribution_verified']):
        raise ValueError('FightResultMain dynamic request metadata mismatch')
    fight_relations = [
        edge for edge in snapshot['relationships']
        if edge['type'] == 'conditional_native_child_request' and
        edge['source_id'] == 28]
    if (sorted(edge['destination_id'] for edge in fight_relations) !=
            [29, 30, 34, 38] or
            any(edge['request_executed'] for edge in fight_relations)):
        raise ValueError('FightResultMain child relationship mismatch')

    # Do not turn forwarded caller arguments or sentinel 0x30 into
    # fabricated native factory IDs. Verify the source callbacks and
    # original MIPS words, including branch delay-slot arguments.
    cancel = snapshot.get('cancel_and_forward_dispatch')
    if (not isinstance(cancel, dict) or
            cancel.get('native_sentinel_id') != 0x30 or
            len(cancel.get('instruction_signatures', {})) != 54):
        raise ValueError('incomplete native cancel/forward evidence')
    for site_text, expected_word in cancel['instruction_signatures'].items():
        site = int(site_text, 16)
        if _word(data, site) != expected_word:
            raise ValueError('cancel/forward instruction mismatch at 0x%08X'
                             % site)
    forward = cancel['forwarded_child_request']
    recursive = cancel['recursive_cancel']
    if (forward['helper'] != CHILD or
            forward['lookup_site'] != 0x3DFBFC or
            forward['forward_site'] != 0x3DFC1C or
            forward['forwarded_argument_site'] != 0x3DFC14 or
            recursive['helper'] != TRANSITION or
            recursive['site'] != 0x3DFB8C or
            recursive['argument_site'] != 0x3DFB90 or
            recursive['guarded_phases'] != [1, 2, 3, 4] or
            recursive['target_id'] != 0x30):
        raise ValueError('generic native forward/cancel route mismatch')
    timer = cancel['fight_demo_end_timeout']
    single = cancel['fight_play_single_finish']
    if (timer['app_id'] != 25 or
            timer['callback_vtable_offset'] != 0x40 or
            timer['callback'] != by_id[25]['base_slots']['0x40'] or
            timer['threshold_float32_bits'] != 0x3CA3D70A or
            timer['request_site'] != 0x3E4C54 or
            timer['sentinel_setup'] != 0x3E4C30):
        raise ValueError('FightDemoEnd timeout evidence mismatch')
    if (single['app_id'] != 20 or
            single['callback_vtable_offset'] != 0x40 or
            single['callback'] != by_id[20]['base_slots']['0x40'] or
            single['jump_table'] != 0x4D7580 or
            single['state_offset'] != 0x30 or
            single['state9_entry'] != 0x3E91D4 or
            single['request_site'] != 0x3E920C or
            single['sentinel_setup'] != 0x3E9210):
        raise ValueError('FightPlaySingle state-9 evidence mismatch')
    expected_cases = (0x3E8CF8, 0x3E8D88, 0x3E8E18, 0x3E8E64,
                      0x3E8ECC, 0x3E8F78, 0x3E9074, 0x3E90B0,
                      0x3E9158, 0x3E91D4)
    if single['table_size'] != len(expected_cases):
        raise ValueError('FightPlaySingle state-table length mismatch')
    for i, target in enumerate(expected_cases):
        if _word(data, single['jump_table'] + 4 * i) != target:
            raise ValueError('FightPlaySingle native state-table mismatch')
    cancellation_calls = {edge['callsite']: edge
                          for edge in snapshot['callsites']}
    for site, kind, target in ((0x3DFB8C, 'transition', 48),
                               (0x3DFC1C, 'transition', None),
                               (0x3E4C54, 'transition', 48),
                               (0x3E920C, 'transition', 48)):
        edge = cancellation_calls[site]
        if (edge['api'] != kind or edge['target_id'] != target or
                edge['is_registered_destination'] or
                not edge['condition_verified_by_elf']):
            raise ValueError('cancel/forward callsite metadata mismatch')
    if (cancellation_calls[0x3DFC1C]['argument_site'] != 0x3DFC14 or
            cancellation_calls[0x3E4C54]['source_candidates'] != [25] or
            cancellation_calls[0x3E920C]['source_candidates'] != [20] or
            not cancellation_calls[0x3E4C54]['source_attribution_verified'] or
            not cancellation_calls[0x3E920C]['source_attribution_verified']):
        raise ValueError('cancel/forward source attribution mismatch')

    # Phase-5 root transition invokes a real factory table entry with
    # jalr and stores its result (or fallback) in active-root BSS. Static
    # proof of this path is NOT evidence that a user runtime executed it.
    root = snapshot.get('native_root_factory_dispatch')
    if (not isinstance(root, dict) or
            len(root.get('instruction_signatures', {})) != 40):
        raise ValueError('incomplete native root factory evidence')
    for site_text, expected_word in root['instruction_signatures'].items():
        site = int(site_text, 16)
        if _word(data, site) != expected_word:
            raise ValueError('root factory instruction mismatch at 0x%08X' %
                             site)
    if (root['scheduler'] != 0x3DFCF0 or
            root['phase5_virtual_callback_site'] != 0x3DFDC0 or
            root['phase5_virtual_offset'] != 0x44 or
            root['scheduler_root_handoff_callsite'] != 0x3DFF34 or
            root['scheduler_handoff_id_load_site'] != 0x3DFF38 or
            root['root_handoff_function'] != 0x3F1BA0 or
            root['registry_init_callsite'] != 0x3F1BAC or
            root['factory_registry_init'] != 0x3F1580 or
            root['pending_id_offset'] != 0x10 or
            root['parent_id_offset'] != 0x13 or
            root['parent_sentinel'] != 48 or
            root['argument_mask'] != 255 or
            root['minimum_valid_id'] != 1 or
            root['maximum_valid_id'] != 47 or
            root['factory_table_base'] != TABLE or
            root['factory_pointer_load_site'] != 0x3F1BDC or
            root['indirect_factory_callsite'] != 0x3F1BE0 or
            root['active_root_pointer_slot'] != 0x63BE38 or
            root['active_root_pointer_store_sites'] != [0x3F1C04, 0x3F1C30] or
            root['factory_fallback_pointer'] != GP - 0x289C or
            root['invalid_id_fallback_pointer'] != 0x5E1AC0 or
            root['factory_executed'] or
            root['root_pointer_written_observed']):
        raise ValueError('root factory dispatch metadata mismatch')
    if _word(data, root['scheduler_root_handoff_callsite']) != _jal(
            root['root_handoff_function']):
        raise ValueError('root scheduler handoff call mismatch')
    if _word(data, root['registry_init_callsite']) != _jal(
            root['factory_registry_init']):
        raise ValueError('root registry init call mismatch')
    if _word(data, root['indirect_factory_callsite']) != 0x0040F809:
        raise ValueError('root indirect factory call mismatch')
    provider = root['instance_provider']
    if (provider['function'] != LOOKUP or
            provider['registry_init_callsite'] != 0x3F1C4C or
            provider['id_mask_site'] != 0x3F1C54 or
            provider['maximum_exclusive_id'] != 48 or
            provider['lower_bound_test_site'] != 0x3F1C58 or
            provider['factory_table_base'] != TABLE or
            provider['factory_pointer_load_site'] != 0x3F1C74 or
            provider['indirect_factory_callsite'] != 0x3F1C78 or
            provider['installs_active_root'] or
            provider['factory_executed'] or
            len(provider['signatures']) != 9):
        raise ValueError('factory instance-provider metadata mismatch')
    for site_text, expected_word in provider['signatures'].items():
        site = int(site_text, 16)
        if _word(data, site) != expected_word:
            raise ValueError('factory instance-provider instruction mismatch'
                             ' at 0x%08X' % site)
    if (_word(data, provider['registry_init_callsite']) !=
            _jal(root['factory_registry_init']) or
            _word(data, provider['indirect_factory_callsite']) != 0x0040F809):
        raise ValueError('factory instance-provider jalr mismatch')


    api = {'transition': TRANSITION, 'child_request': CHILD,
           'factory_lookup': LOOKUP}
    verified_sites = set()
    for edge in snapshot['callsites']:
        site = edge['callsite']
        if site in verified_sites or edge['api'] not in api:
            raise ValueError('duplicate or invalid callsite 0x%08X' % site)
        verified_sites.add(site)
        if _word(data, site) != _jal(api[edge['api']]):
            raise ValueError('invalid helper call at 0x%08X' % site)
        if edge['target_id'] is not None:
            arg_site = edge['argument_site']
            if arg_site is None or _word(data, arg_site) != (0x24050000 | edge['target_id']):
                # Some callsites set a literal via addiu before the call;
                # reject mismatched words rather than trying to infer a target.
                raise ValueError('literal request mismatch at 0x%08X' % site)
    if len(verified_sites) != 110:
        raise ValueError('static callsite count mismatch')
    if by_id[42]['class_name'] != 'CAppMenuMain' or by_id[43]['class_name'] != 'CAppShenronMain':
        raise ValueError('critical ID 42/43 identity mismatch')
    return {'verified_applications': len(apps),
            'verified_callsites': len(verified_sites),
            'literal_registered_destinations': sum(
                edge['is_registered_destination'] for edge in snapshot['callsites']),
            'class_names': len(set(app['class_name'] for app in apps))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--dump-extracted-json', type=Path)
    args = parser.parse_args()
    try:
        data = args.elf.read_bytes()
        snapshot = json.loads(args.registry.read_text(encoding='utf-8'))
        summary = verify(data, snapshot)
        if args.dump_extracted_json:
            args.dump_extracted_json.write_text(
                json.dumps(recover(data), indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
