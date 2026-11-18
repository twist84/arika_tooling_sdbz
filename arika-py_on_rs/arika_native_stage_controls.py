"""EE-backed initial kind-6 stage state masks and opt-in editor preview.

Original object+0x28 bits 0x300 are cleared on the primary target and
set on the secondary target by 0x240290; 0x240860 gates its callback
when both bits are set. This is NOT a complete rendering/collision
visibility solver. The opt-in preview suppresses secondary subtrees
as an editor interpretation, without mutating STG or glTF authored state.
"""
import hashlib
import struct

ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
ELF_BIAS = 0xFFF80
INITIAL_MASK = 0x300
FLAG_WORD_OFFSET = 0x28
ELF_INITIAL_WORDS = {
    0x2402B4: 0x2403FCFF,  # addiu v1,zero,-0x301
    0x2402C0: 0x00831024,  # and v0,a0,v1 (primary clears)
    0x2402C4: 0xACA20028,  # sw v0,0x28(a1)
    0x2402F4: 0x34420300,  # ori v0,v0,0x300 (secondary sets)
    0x2402F8: 0xAC620028,  # sw v0,0x28(v1)
    0x240750: 0x34420300,  # alternate stage event sets primary
    0x240754: 0xAC620028,
    0x240788: 0x00831024,  # stage event clears secondary
    0x24078C: 0xAD020028,
    0x240864: 0x24020300,  # completion gate constant 0x300
    0x240874: 0x8C830028,  # lw v1,0x28(a0)
    0x240878: 0x30630300,  # andi v1,v1,0x300
    0x24087C: 0x14620003,  # bne v1,v0,0x24088C
    0x240A64: 0x2402FCFF,  # reset event clears primary
    0x240A6C: 0x00621024,
    0x240A70: 0xAC820028,
    0x240A9C: 0x34420300,  # reset event sets secondary
    0x240AA0: 0xAC620028,
}


def verify_native_stage_control_elf(data):
    """Validate exact EU-beta EE opcode evidence, not a runtime execution."""
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('exact EU-beta ELF SHA-256 required')
    for address, word in ELF_INITIAL_WORDS.items():
        offset = address - ELF_BIAS
        if offset < 0 or offset + 4 > len(data):
            raise ValueError('native kind-6 opcode outside ELF')
        if struct.unpack_from('<I', data, offset)[0] != word:
            raise ValueError('native kind-6 opcode mismatch at 0x%08X' % address)
    return {'verified_original_instruction_words': len(ELF_INITIAL_WORDS),
            'mask': INITIAL_MASK, 'runtime_execution_proven': False}


def _descendants(nodes, index):
    stack = [index]
    seen = set()
    while stack:
        i = stack.pop()
        if i in seen or not 0 <= i < len(nodes):
            raise ValueError('invalid or cyclic stage hierarchy')
        seen.add(i)
        stack.extend(reversed(nodes[i].get('children', ())))
    return seen


def inspect_native_initial_stage_state(scene):
    """Report exact bit operations plus conservative *optional* preview roots.

    Native state targets are resolved in parse_stg() via original first
    depth-first name match. Template controls are excluded by default:
    only EFFECT and STAGE live roots participate in this diagnostic.
    Conflicting primary and secondary targets are not preview-hidden.
    """
    if not isinstance(scene, dict) or scene.get('format') != 'ARIKA_STG':
        raise ValueError('expected parsed ARIKA_STG document')
    nodes = scene['nodes']
    active = set()
    for root in (scene['effect_root'], scene['stage_root']):
        active.update(_descendants(nodes, root))
    actions = []
    primary = set()
    secondary = []
    warnings = []
    controllers = 0
    for node in nodes:
        if node['index'] not in active or 'state_control' not in node:
            continue
        controllers += 1
        control = node['state_control']
        for role, mode, site in (
                ('primary', 'clear', 0x2402C0),
                ('secondary', 'set', 0x2402F4)):
            target = control.get(role + '_node')
            name = control.get(role + '_name')
            if name is None:
                continue
            if target is None:
                warnings.append('control %d: %s %r unresolved' %
                                (node['index'], role, name))
                continue
            if type(target) is not int or target not in active:
                warnings.append('control %d: %s outside live roots' %
                                (node['index'], role))
                continue
            if target not in _descendants(nodes, node['index']):
                warnings.append('control %d: %s target outside original subtree' %
                                (node['index'], role))
                continue
            actions.append({
                'controller_node': node['index'],
                'target_node': target,
                'target_name': name,
                'role': role,
                'operation': mode,
                'mask': INITIAL_MASK,
                'runtime_flag_offset': FLAG_WORD_OFFSET,
                'elf_instruction_site': site,
                'original_target_lookup': 'first_depth_first',
            })
            if role == 'primary':
                primary.add(target)
            else:
                secondary.append((node['index'], target))
    suppressed = []
    for controller, target in secondary:
        descendants = _descendants(nodes, target)
        if descendants & primary:
            warnings.append(
                'control %d: secondary %d overlaps a primary target; '
                'no automatic preview hiding' % (controller, target))
            continue
        if target not in suppressed:
            suppressed.append(target)
    hidden = set()
    for target in suppressed:
        hidden.update(_descendants(nodes, target))
    return {
        'native_control_count': controllers,
        'native_mask_actions': actions,
        'preview_suppressed_root_nodes': sorted(suppressed),
        'preview_suppressed_stage_nodes': sorted(hidden),
        'conflicts_or_unresolved': warnings,
        'mask': INITIAL_MASK,
        'runtime_flag_offset': FLAG_WORD_OFFSET,
        'scope': ('original first-depth-first targets under live '
                  'EFFECT/STAGE roots; excludes authored templates'),
        'preview_only': True,
        'native_render_visibility_proven': False,
        'native_collision_suppression_proven': False,
    }


def native_stage_preview_hidden_nodes(scene, document, suppressed_roots,
                                      inspected):
    """Map proposed STG root suppression to exact, unique glTF source nodes.

    Source offsets, kind and name must all match. This is deliberately shared
    by the initial and phase-switched preview; neither mutates the document.
    A collision duplicate is not a visually suppressed source object.
    """
    if not isinstance(scene, dict) or scene.get('format') != 'ARIKA_STG':
        raise ValueError('expected parsed ARIKA_STG document')
    doc_nodes = document.get('nodes', ())
    if not isinstance(doc_nodes, list):
        raise ValueError('expected glTF nodes list')
    if not isinstance(suppressed_roots, (list, tuple)):
        raise ValueError('expected preview root sequence')
    by_offset = {}
    for i, node in enumerate(doc_nodes):
        extras = node.get('extras', {})
        if not isinstance(extras, dict):
            continue
        offset = extras.get('stg_offset')
        if (type(offset) is int and
                not node.get('name', '').startswith('collision:')):
            by_offset.setdefault(offset, []).append(i)
    hidden = set()
    skipped = []
    original_nodes = scene['nodes']
    for original in sorted(set(suppressed_roots)):
        if type(original) is not int or not 0 <= original < len(original_nodes):
            raise ValueError('invalid original stage target')
        source = original_nodes[original]
        matches = [
            i for i in by_offset.get(source['offset'], ())
            if (doc_nodes[i].get('name') == source['name'] and
                doc_nodes[i].get('extras', {}).get('kind') == source['kind'])
        ]
        if len(matches) != 1:
            skipped.append(
                'STG node %d has %d matching glTF source objects; skipped' %
                (original, len(matches)))
            continue
        hidden.update(_descendants(doc_nodes, matches[0]))
    return {
        'hidden_gltf_nodes': sorted(hidden),
        'stage_state': inspected,
        'skipped_mappings': skipped,
        'preview_only': True,
        'source_document_mutated': False,
    }


def native_initial_preview_hidden_nodes(scene, document):
    """Resolve original initial secondary target flags into a visual preview.

    The native collision and GS consumers are not completely established.
    A hidden object in this diagnostic is NOT an observed game visibility.
    """
    inspected = inspect_native_initial_stage_state(scene)
    return native_stage_preview_hidden_nodes(
        scene, document, inspected['preview_suppressed_root_nodes'], inspected)
