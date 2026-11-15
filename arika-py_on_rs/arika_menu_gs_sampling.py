"""EU-beta native sprite-command texture sampling selector recovery.

Opcode 1 of the engine command interpreter at 0x19B688:
  - lhu +4 indexes GP-0x7FA8 (EE 0x4F73C8) for filter flag
  - lbu +6 indexes GP-0x7FA0 (EE 0x4F73D0) for clamp flag
  - 0x104820 installs both globals 0x4FF470 and 0x4FF474
  - 0x10DA20 calls 0x10C3E0, which emits GS TEX1 = 0x60 or 0.

These are file-backed two-entry selector tables. We DO NOT assume every
menu sprite binds either selector, that the resource lookup succeeds,
or that callbacks leave GS state untouched. These interpretations are
for captured *engine command buffers*, not the PIX texture indices.
"""
import copy

from arika_menu_gs_packet import decode_packet
from arika_menu_gs_texture import decode_tex1


ELF_FILTER_SELECTOR_TABLE_ADDRESS = 0x004F73C8
ELF_CLAMP_SELECTOR_TABLE_ADDRESS = 0x004F73D0
FILTER_BY_SELECTOR = (0, 1)
CLAMP_BY_SELECTOR = (1, 0)
SET_FLAGS_ADDRESS = 0x00104820
BIND_RESOURCE_ADDRESS = 0x0010DA20
EMIT_TEXTURE_ADDRESS = 0x0010C3E0


def _resolve_selector(table, raw):
    if type(raw) is not int or not 0 <= raw < len(table):
        return None
    return table[raw]


def resolve_texture_binding(command):
    """Decode one opcode-1 binding, leaving out-of-range selectors unknown.

    Opcode-1 payload field +2 is a *different* selector. The actual
    filtering index comes from +4, and the clamp index from +6.
    GS TEX1 is only emitted if the separately looked-up texture
    descriptor passes the native writer's validation.
    """
    if not isinstance(command, dict) or command.get('opcode') != 1:
        raise ValueError('expected a decoded opcode-1 texture binding')
    selectors = command.get('selectors')
    options = command.get('options')
    if (not isinstance(selectors, list) or len(selectors) != 2 or
            not isinstance(options, list) or len(options) != 2):
        raise ValueError('decoded texture binding has missing selectors')
    filter_selector = selectors[1]
    clamp_selector = options[0]
    filter_flag = _resolve_selector(FILTER_BY_SELECTOR, filter_selector)
    clamp_flag = _resolve_selector(CLAMP_BY_SELECTOR, clamp_selector)
    # Do not guess one flag from the other: their table indices are
    # independent fields in the native 12-byte binding command.
    tex1 = None if filter_flag is None else (0x60 if filter_flag else 0)
    return {
        'filter_selector': filter_selector,
        'clamp_selector': clamp_selector,
        'filter_flag': filter_flag,
        'clamp_flag': clamp_flag,
        'texture_filter': ('linear' if filter_flag else 'nearest')
                          if filter_flag is not None else None,
        'tex1_if_texture_writer_succeeds': tex1,
        'tex1_fields_if_emitted': decode_tex1(tex1) if tex1 is not None else None,
        'resource_pointer': command.get('resource_pointer'),
        'complete': filter_flag is not None and clamp_flag is not None,
        'note': ('Selector decoding is exact for valid indices; actual '
                 'runtime resource binding and active GS state are not captured.'),
    }


def annotate_packet_sampling(decoded):
    """Annotate texture binding and callback entry in a decoded packet.

    Opcode 0 calls an *indirect* engine callback at 0x19B658. Its
    side-effects are unverified, so any known sampling state becomes
    unknown AFTER that callback. Opcodes 2..8 do not call 0x104820,
    so they do not modify these two flags directly.
    """
    if not isinstance(decoded, dict) or 'commands' not in decoded:
        raise ValueError('expected a decoded native engine command packet')
    commands = []
    binding = None
    for command in decoded['commands']:
        annotated = dict(command)
        if command['opcode'] == 1:
            binding = resolve_texture_binding(command)
            annotated['texture_binding'] = copy.deepcopy(binding)
        elif command['opcode'] == 0:
            annotated['binding_at_callback_entry'] = copy.deepcopy(binding)
            # Callback may set another texture/filter; no post-callback
            # inference without tracing the target vtable.
            binding = None
        commands.append(annotated)
    result = dict(decoded)
    result['commands'] = commands
    result['sampling_analysis'] = {
        'filter_selector_table': hex(ELF_FILTER_SELECTOR_TABLE_ADDRESS),
        'clamp_selector_table': hex(ELF_CLAMP_SELECTOR_TABLE_ADDRESS),
        'filter_values': list(FILTER_BY_SELECTOR),
        'clamp_values': list(CLAMP_BY_SELECTOR),
        'initial_binding': 'unknown',
        'post_indirect_callback': 'unknown',
        'limitations': [
            'Engine command selector values are not PIX atlas indices.',
            'No runtime sprite-to-resource mapping has been supplied.',
            'TEX1 writes require a valid runtime texture descriptor.',
            'Indirect opcode-0 callback may modify native GS state.',
        ],
    }
    return result


def decode_packet_sampling(data, initial_state=None, allow_padding=False):
    return annotate_packet_sampling(
        decode_packet(data, initial_state=initial_state,
                      allow_padding=allow_padding))
