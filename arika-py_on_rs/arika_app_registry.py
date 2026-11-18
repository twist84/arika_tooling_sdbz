"""EU-beta application's original EE factory ID registry.

The code at 0x3F1580 installs factory pointers in BSS at 0x6217E0
and registers *all IDs 1..47* through 0x3DFA60, in a nonnumeric
registration order. The entries catalogued below have independently
verified factory, constructor and original class-name getter evidence;
all 47 constructors, getter strings and top-level vtable slots are catalogued.
The legacy 'factory lookup' name at 0x003F1C40 describes an instance
provider: it DOES call a BSS factory through jalr and returns the
result. The root handoff at 0x003F1BA0 also invokes a factory but installs
its returned pointer at global BSS 0x0063BE38. Neither static call path
proves that a particular user runtime executed it.
Lifecycle callback semantics remain under investigation.
"""
import hashlib
import json
from pathlib import Path
import struct

from arika_logo_runtime import ELF_SHA256


APP_FACTORY_INIT = 0x003F1580
APP_FACTORY_LOOKUP = 0x003F1C40
APP_FACTORY_TABLE = 0x006217E0
APP_FACTORY_REGISTER = 0x003DFA60
APP_TRANSITION_REQUEST = 0x003DFB00
APP_CHILD_REQUEST = 0x003DFBD0
APP_REGISTRY_COUNT = 47
APP_REGISTRY_FIRST = 0x003F15BC
APP_REGISTRY_LAST = 0x003F1B7C
ELF_FILE_BIAS = 0xFFF80

# The JSON is the single source of truth for all native application IDs.
# Preserve APP_FACTORIES and APP_REGISTRATION_SITES for existing callers.
APP_NATIVE_REGISTRY_PATH = (Path(__file__).with_name('research') /
                            'native_app_registry_eu_beta.json')
APP_NATIVE_REGISTRY = json.loads(APP_NATIVE_REGISTRY_PATH.read_text(encoding='utf-8'))
APP_ENTRIES = {app['id']: app for app in APP_NATIVE_REGISTRY['applications']}
# Independent exact-ELF argument audit for all 37 provider callsites.
# Keep this separate from the 73 transition/child requests: a provider may
# invoke a factory without requesting a native application transition.
APP_NATIVE_PROVIDER_AUDIT_PATH = (Path(__file__).with_name('research') /
                                  'native_factory_provider_calls_eu_beta.json')
APP_NATIVE_PROVIDER_AUDIT = json.loads(
    APP_NATIVE_PROVIDER_AUDIT_PATH.read_text(encoding='utf-8'))
APP_NATIVE_PROVIDER_CALLS = tuple(APP_NATIVE_PROVIDER_AUDIT['callsites'])
_expected_provider_sites = {
    edge['callsite'] for edge in APP_NATIVE_REGISTRY['callsites']
    if edge['api'] == 'factory_lookup'
}
if (len(APP_NATIVE_PROVIDER_CALLS) != 37 or
        len({edge['callsite'] for edge in APP_NATIVE_PROVIDER_CALLS}) != 37 or
        {edge['callsite'] for edge in APP_NATIVE_PROVIDER_CALLS} !=
        _expected_provider_sites):
    raise ValueError('factory-provider audit must cover exactly 37 sites')


if (len(APP_ENTRIES) != APP_REGISTRY_COUNT or
        sorted(APP_ENTRIES) != list(range(1, APP_REGISTRY_COUNT + 1))):
    raise ValueError('invalid native application registry: missing or duplicate IDs')
APP_FACTORIES = tuple(
    (app['id'], app['factory'], app['constructor'], app['name_getter'],
     app['class_name_pointer'], app['class_name'])
    for app in APP_NATIVE_REGISTRY['applications']
)

# CCardDemo is a helper class, not an application-factory entry.
# IDs 6 and 8 both identify as CAppDemoMain in the exact original
# binary, but have DIFFERENT factories, constructors and vtables.
DEMO_HELPER_STRINGS = {
    0x4D5300: 'CCardDemo',
}

# Additional ID-specific constructor-pointer, singleton-factory,
# registration site and registration table-address evidence.
APP_REGISTRATION_SITES = {
    app['id']: (app['factory_site'], app['factory_table_store_site'],
                app['registration_id_site'])
    for app in APP_NATIVE_REGISTRY['applications']
}

# The *ID 6* CAppDemoMain's native 0x3E0830 update can request
# these children via 0x3DFBD0 based on the previous choice this+0x28.
DEMO_MAIN_CHILD_CHOICES = (4, 7, 8, 9)
DEMO_MAIN_CHOICE_SITES = (0x3E08B4, 0x3E08CC, 0x3E08E4, 0x3E08F4)


def _word(elf, address):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + 4 > len(elf):
        raise ValueError('invalid mapped ELF address: 0x%08X' % address)
    return struct.unpack_from('<I', elf, offset)[0]


def _cstring(elf, address, max_length=64):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + max_length > len(elf):
        raise ValueError('invalid mapped ELF string: 0x%08X' % address)
    raw = elf[offset:offset + max_length].split(b'\0', 1)
    if len(raw) != 2:
        raise ValueError('unterminated ELF string at 0x%08X' % address)
    return raw[0].decode('ascii')


def resolve_app(app_id):
    """Resolve exact native identity; never infer it from registration order."""
    if type(app_id) is not int:
        raise ValueError('app_id must be an integer')
    app = APP_ENTRIES.get(app_id)
    if app is None:
        return None
    return {
        'id': app['id'],
        'class_name': app['class_name'],
        'factory': app['factory'],
        'constructor': app['constructor'],
        'name_getter': app['name_getter'],
        'name_address': app['class_name_pointer'],
        'registration_order': app['registration_order'],
        'factory_table': APP_FACTORY_TABLE + 4 * app_id,
        'registration_callsite': app['registration_callsite'],
        'constructor_callsite': app['constructor_callsite'],
        'base_vtable': app['base_vtable'],
        'phase_vtable': app['phase_vtable'],
        'base_slots': dict(app['base_slots']),
        'phase_slots': dict(app['phase_slots']),
        'callback_dispatch': dict(app['callback_dispatch']),
        'factory_executed': False,
    }


def registered_native_requests(source_id=None, request_kind=None):
    """Read statically recovered native helper callsites.

    These include transition requests, child requests, and an historical
    'factory_lookup' label for the factory-*invoking* instance provider.
    Source ownership may be provisional. Recording a callsite does NOT
    establish that the native runtime took the branch or ran a factory.
    """
    if source_id is not None and (type(source_id) is not int or
                                  source_id not in APP_ENTRIES):
        raise ValueError('invalid native source application ID')
    if request_kind is not None and request_kind not in (
            'transition', 'child_request', 'factory_lookup'):
        raise ValueError('invalid native request kind')
    requests = APP_NATIVE_REGISTRY['callsites']
    return tuple(edge for edge in requests
                 if (request_kind is None or edge['api'] == request_kind) and
                 (source_id is None or source_id in edge['source_candidates']))



def registered_factory_providers(target_id=None, argument_kind=None):
    """Return static provider argument evidence, NOT execution events.

    `target_id` filters only proved literal IDs; mutable child/pending ID
    arguments are returned by `argument_kind` or in the full listing.
    """
    if target_id is not None and (
            type(target_id) is not int or target_id not in APP_ENTRIES):
        raise ValueError('invalid literal provider target ID')
    kinds = ('literal', 'child_id_byte', 'pending_id_byte',
             'requested_child_id')
    if argument_kind is not None and argument_kind not in kinds:
        raise ValueError('invalid native provider argument kind')
    return tuple(
        edge for edge in APP_NATIVE_PROVIDER_CALLS
        if (target_id is None or edge['target_id'] == target_id) and
           (argument_kind is None or edge['argument_kind'] == argument_kind))


def title_handoff_request(title_result):
    """Translate only an actual completed title call to a named request.

    This does not execute 0x3DFB00 or the registered constructor and
    never claims the destination child was already instantiated.
    """
    if not isinstance(title_result, dict):
        raise TypeError('expected c_title_runtime.step result')
    if not title_result.get('finished'):
        return None
    for call in title_result.get('calls', ()):
        if call.get('address') == '0x3dfb00' and call.get('arguments') == [6]:
            return {
                'request_address': APP_TRANSITION_REQUEST,
                'target': resolve_app(6),
                'executed': False,
            }
    return None


def recover_registered_app_ids_elf(elf):
    """Count every native registration call, including uncatalogued IDs.

    A registration must use the exact 0x3DFA60 JAL with its immediate
    ID argument and the expected ID-indexed BSS factory-table store.
    This does not execute a constructor or infer a class from its ID.
    """
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')
    registration_call = 0x0C000000 | (APP_FACTORY_REGISTER >> 2)
    registered = []
    for address in range(APP_REGISTRY_FIRST, APP_REGISTRY_LAST + 1, 4):
        if _word(elf, address) != registration_call:
            continue
        immediate = _word(elf, address + 4)
        if immediate & 0xFFFF0000 != 0x24050000:
            raise ValueError('nonliteral factory ID at 0x%08X' % address)
        app_id = immediate & 0xFFFF
        table_store = _word(elf, address - 8)
        if table_store != (0xAC430000 | (0x17E0 + 4 * app_id)):
            raise ValueError('factory table index mismatch at ID %d' % app_id)
        registered.append(app_id)
    if (len(registered) != APP_REGISTRY_COUNT or
            sorted(registered) != list(range(1, APP_REGISTRY_COUNT + 1))):
        raise ValueError('the complete native factory register set changed')
    return tuple(registered)


def verify_app_registry_elf(elf):
    """Exact-ELF oracle for ID→constructor→class name and child routing."""
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')

    native_ids = recover_registered_app_ids_elf(elf)
    # Native registry lookup guards ID < 0x30 then calls
    # *(0x6217E0 + id * 4). No executable BSS table is faked.
    dispatch_words = {
        0x3F1C5C: 0x28410030,   # bound check ID < 48
        0x3F1C64: 0x00021880,   # ID*4
        0x3F1C6C: 0x244217E0,   # 0x6217E0
        0x3F1C74: 0x8C420000,   # load factory
        0x3F1C78: 0x0040F809,   # jalr v0
    }
    for address, value in dispatch_words.items():
        if _word(elf, address) != value:
            raise ValueError('app lookup word mismatch at 0x%08X' % address)

    for app_id, factory, constructor, getter, text_address, name in APP_FACTORIES:
        factory_site, register_site, id_site = APP_REGISTRATION_SITES[app_id]
        if _word(elf, factory_site) != 0x24630000 | (factory & 0xFFFF):
            raise ValueError('factory mismatch for ID %d' % app_id)
        # sw v1, (0x17e0 + ID*4)($v0), with high word 0x62.
        if _word(elf, register_site) != (
                0xAC430000 | (0x17E0 + 4 * app_id)):
            raise ValueError('factory table store mismatch for ID %d' % app_id)
        if _word(elf, id_site) != (0x24050000 | app_id):
            raise ValueError('registration ID mismatch at ID %d' % app_id)
        jal_word = 0x0C000000 | ((constructor >> 2) & 0x03FFFFFF)
        # The singleton creator's first constructor call is at +0x20.
        if _word(elf, factory + 0x20) != jal_word:
            raise ValueError('constructor call mismatch for ID %d' % app_id)
        if _cstring(elf, text_address) != name:
            raise ValueError('class name mismatch for ID %d' % app_id)

        # The factory constructs a type whose base vtable carries
        # the getter at +8. Check the vtable from the constructor.
        # Exact pointer pairs are checked independently below.
    for address, literal in DEMO_HELPER_STRINGS.items():
        if _cstring(elf, address) != literal:
            raise ValueError('demo helper string mismatch')

    expected = {
        0x4FC820: 0x4D8518,  # ID 1 getter loads this GP-relative pointer
        0x4F6868: 0x3FAED0,  # ID 1 base name getter
        0x4F6898: 0x3FAAB0,  # ID 1 load callback
        0x4F68A0: 0x3FAC20,  # ID 1 update callback
        0x3FABFC: 0x24040002, # ID 1 begins ID 2 child
        0x4F6928: 0x3FE330,  # ID 42 base getter: CAppMenuMain
        0x4F6958: 0x3FDEB0,  # ID 42 load callback
        0x4F6960: 0x3FE020,  # ID 42 native update
        0x4F69B8: 0x4030D0,  # ID 43 getter: CAppShenronMain
        0x3F7868: 0x2405002A,  # Press Start request ID 42
        0x41F074: 0x24050001,  # Warning To Game requests ID 1
        0x3E03FC: 0x24425E00,  # DemoMain base vtable
        0x3E0410: 0x24425E28,  # DemoMain phase vtable
        0x3E1BEC: 0x24425ED0,  # DemoMovie base vtable
        0x3E1C00: 0x24425EF8,  # DemoMovie phase vtable
        0x4F5E00 + 8: 0x3E0D10,  # DemoMain name getter
        0x4F5ED0 + 8: 0x3E2080,  # DemoMovie name getter
        0x3E0D18: 0x244252F0,   # CAppDemoMain string
        0x3E2088: 0x24425338,   # CAppDemoMovie string
        0x4F7258: 0x41EC80,    # LogoMain name getter
        0x41EC88: 0x244291F8,  # LogoMain name pointer
        0x3F89CC: 0x24050006,   # Title requests app 6
        0x3F716C: 0x24636670,   # ID 3 ctor: alternate title base
        0x3F7170: 0x24426698,   # ID 3 ctor: alternate title phase
        0x4F6678: 0x003F86C0,   # ID 3 base name getter
        0x3F86C8: 0x24427F90,   # shared CAppTitleMain name pointer
        0x3E217C: 0x24425F30,   # ID 8 ctor: own base vtable
        0x3E2190: 0x24425F58,   # ID 8 ctor: own phase vtable
        0x4F5F38: 0x003E26B0,   # ID 8 class getter
        0x3E26B8: 0x24425348,   # ID 8 name -> CAppDemoMain
        0x3E0E0C: 0x24635E70,   # ID 9 ctor: own base vtable
        0x3E0E10: 0x24425E98,   # ID 9 ctor: own phase vtable
        0x4F5E78: 0x003E1AE0,   # ID 9 class getter
        0x3E1AE8: 0x24425310,   # ID 9 name -> CAppDemoPlay
    }
    for address, value in expected.items():
        if _word(elf, address) != value:
            raise ValueError('app vtable/handoff mismatch at 0x%08X' % address)

    for site, child in zip(DEMO_MAIN_CHOICE_SITES, DEMO_MAIN_CHILD_CHOICES):
        if _word(elf, site) != (0x24050000 | child):
            raise ValueError('demo child ID mismatch at 0x%08X' % site)

    return {
        'format': 'ARIKA_EU_BETA_APP_REGISTRY',
        'elf_sha256': ELF_SHA256,
        'factory_init': hex(APP_FACTORY_INIT),
        'factory_lookup': hex(APP_FACTORY_LOOKUP),
        'factory_table': hex(APP_FACTORY_TABLE),
        'transition_request': hex(APP_TRANSITION_REQUEST),
        'child_request': hex(APP_CHILD_REQUEST),
        'registered_ids': list(native_ids),
        'registered_count': len(native_ids),
        'registered': [resolve_app(app_id) for app_id, *_ in APP_FACTORIES],
        'screen_handoff_evidence': {
            'warning_to_game': {'request_id': 1, 'factory': '0x3f2de0',
                                'wrapper_class_name': 'CAppWarning'},
            'press_start_confirm': {'request_id': 42,
                                    'factory': '0x3f1f40',
                                    'class_name': 'CAppMenuMain'},
            'adjacent_id_43': {'class_name': 'CAppShenronMain'},
        },
        'duplicate_class_names_are_distinct_factories': [
            {'ids': [12, 13], 'name': 'CAppSelectWorld'},
            {'ids': [6, 8], 'name': 'CAppDemoMain'},
        ],
        'title_handoff': {
            'source_id': 2,
            'source': 'CAppCRISofdec',
            'destination_id': 6,
            'destination': 'CAppDemoMain',
            'next_child_choices': list(DEMO_MAIN_CHILD_CHOICES),
        },
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    try:
        result = verify_app_registry_elf(args.elf.read_bytes())
    except (OSError, ValueError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
