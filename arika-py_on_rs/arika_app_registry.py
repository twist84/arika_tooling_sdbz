"""EU-beta application's original EE factory ID registry.

The code at 0x3F1580 installs factory pointers in BSS at 0x6217E0
and registers their IDs through 0x3DFA60. These are *not* zero-based
indexes of class-name strings. The initial registered ID is 1.
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
ELF_FILE_BIAS = 0xFFF80

# (id, factory, constructor, class-name getter, text pointer, class name)
# All names are returned through their own native vtables, not guessed
# from neighboring strings. No claim of original boot order is made.
APP_FACTORIES = (
    (2, 0x3F2D80, 0x3F86E0, 0x3F86C0, 0x4D7F90, 'CAppTitleMain'),
    (3, 0x3F2D20, 0x3F7150, 0x3F86C0, 0x4D7F90, 'CAppTitleMain'),
    (4, 0x3F2CC0, 0x41E620, 0x41EC80, 0x4D91F8, 'CAppLogoMain'),
    (5, 0x3F2C60, 0x41ECA0, 0x41F580, 0x4D8518, 'CAppWarning'),
    (6, 0x3F2C00, 0x3E03E0, 0x3E0D10, 0x4D52F0, 'CAppDemoMain'),
    (7, 0x3F2BA0, 0x3E1BD0, 0x3E2080, 0x4D5338, 'CAppDemoMovie'),
    (8, 0x3F2B40, 0x3E2160, 0x3E26B0, 0x4D5348, 'CAppDemoMain'),
    (9, 0x3F2AE0, 0x3E0DF0, 0x3E1AE0, 0x4D5310, 'CAppDemoPlay'),
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
    2: (0x3F15CC, 0x3F15D4, 0x3F15E0),
    3: (0x3F15EC, 0x3F15F4, 0x3F1600),
    4: (0x3F160C, 0x3F1614, 0x3F1620),
    5: (0x3F162C, 0x3F1634, 0x3F1640),
    6: (0x3F164C, 0x3F1654, 0x3F1660),
    7: (0x3F166C, 0x3F1674, 0x3F1680),
    8: (0x3F168C, 0x3F1694, 0x3F16A0),
    9: (0x3F16AC, 0x3F16B4, 0x3F16C0),
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
    """A missing ID remains unknown, never inferred from list position."""
    if type(app_id) is not int:
        raise ValueError('app_id must be an integer')
    for identifier, factory, constructor, getter, text_address, name in APP_FACTORIES:
        if app_id == identifier:
            return {
                'id': identifier,
                'class_name': name,
                'factory': factory,
                'constructor': constructor,
                'name_getter': getter,
                'name_address': text_address,
            }
    return None


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


def verify_app_registry_elf(elf):
    """Exact-ELF oracle for ID→constructor→class name and child routing."""
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')

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
        'registered': [resolve_app(app_id) for app_id, *_ in APP_FACTORIES],
        'duplicate_class_names_are_distinct_factories': [
            {'ids': [2, 3], 'name': 'CAppTitleMain'},
            {'ids': [6, 8], 'name': 'CAppDemoMain'},
        ],
        'title_handoff': {
            'source_id': 2,
            'source': 'CAppTitleMain',
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
