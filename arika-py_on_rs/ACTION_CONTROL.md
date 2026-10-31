# Action control and animated hands

This pass identifies common motion-sequence tables in the original executable and adds automatic hand selection to glTF playback. It does not yet reconstruct a complete gameplay action, its branches, or the logic that chooses its facial program and transformations.

## Format correction

ASE and AMS are audio resources. The reference executable contains the class names `CSEDataASE` and `CBGMDataAMS` at `0x4C0678` and `0x4C0668`. Their files contain audio block data, rather than player action commands. Earlier descriptions of ASE/AMS as animation-control scripts were incorrect. CHT belongs to the hit/collision system (`CHitchtData`, `CHitchtHandle`); it is not an ordinary animation script either.

Player action playback uses native code and motion-sequence tables in the executable. Other script resources and native gameplay handlers still need tracing before facial triggers, branches and form changes can be exported as coordinated actions.

## Export a motion with automatic hand changes

Run from the tools folder, with the archive extracted under `extracted`:

```sh
python arika_actions.py motion extracted/ply/p01/p01act.pmt goku_hands.gltf --model extracted/ply/p01/p01a.mdl --motion-index 4 --no-blink
```

This exports Goku's `m01210m0.mot` with its authored skeletal movement and hand changes. No ANI program is selected by this command. The face is neutral with optional automatic blinking; `--no-blink` disables it. Duration defaults to the motion's duration. Options include `--duration`, `--rate`, `--loop-motion`, `--seed`, `--super-form` and `--textures`. The sibling `.pix` supplies textures automatically. `examples/goku_hand_motion.gltf` and `previews/hand_playback_contact.png` show this example.

To add automatic hands to an explicitly selected facial program:

```sh
python arika_faces.py animate extracted/ply/p01/p01.ani face_and_hands.gltf --model extracted/ply/p01/p01a.mdl --motion extracted/ply/p01/p01act.pmt --motion-index 4 --duration 0.6 --auto-hands
```

The ANI program and body motion start together by explicit user choice. This does not establish that gameplay normally pairs them. `--auto-hands` requires `--motion` and replaces manual hand selection.

Inspect hand indices without exporting geometry:

```sh
python arika_actions.py hands extracted/ply/p01/p01act.pmt hands.json --motion-index 4 --rate 60
```

## HandAni semantics

The RFSM bone binding names a control node `HandAni`. Its translation X and Z components select the left and right hand mesh indices. Y is not used by the hand-selection call examined here. This control node is not a physical translation to apply to the hand itself.

| Index | Mesh variant |
| --- | --- |
| 0..9 | A..J for the corresponding `MeshLHand` / `MeshRHand` prefix |
| Negative converted integer | Keep the current hand selection |
| Missing HandAni track | Request index zero for both hands |

Missing variants carry forward the preceding available mesh, starting with the unsuffixed `MeshLHand` / `MeshRHand` fallback. Indices of ten or greater are rejected by the exporter.

Evidence chain in SLES_541.61:

- `0x1D6F70` locates the HandAni binding using the string at `0x4C1090`.
- `0x1D7C24..0x1D7C4C` samples its translation through `0x1B7E30`, passing `t1=1`.
- `0x1B7E88..0x1B7EA4` makes that argument disable interpolation. The key search snaps within float32 `1e-5` seconds of an authored key.
- `0x1CD9A4..0x1CD9C4` converts X/Z to integers and calls `0x1D5BB0`.
- `0x1D5BB0` changes left/right visibility, skipping negative indices.
- `0x1D55B4..0x1D5628` constructs ten-entry carry-forward fallback tables.

The exporter uses stepped selection, including the key-search tolerance, rather than interpolating through intermediate mesh indices. Playback starts with index zero selected. It does not import a previous gameplay action's retained hand state.

The glTF uses STEP animation for visibility. For skinned variants, each switched mesh receives an independent copy of the joint hierarchy and a common visibility parent. Scaling that parent to zero collapses the hidden geometry; body animation channels are shared with the cloned joints. Scaling the mesh node alone would be ignored by glTF skinning. Rigid variants use their geometry node directly. These are baked playback exports and cannot be imported as model-edit templates.

## Inspect common action tables

Supported common-table sequence playback previews are now available through `arika_sequence.py`; see ACTION_SEQUENCES.md. The transition graph is checked against the native branch-selection prefix. Preview timing remains separate from native tick/blend behavior and event-driven action changes.

The following CHT lookup layer is now decoded. `arika_actions.py resolve` maps common action segments to exact package entries, and `motion-id` exports a logical motion/variant without a manual package index. See MOTION_BINDINGS.md. Complete action sequencing and native overrides remain separate from this lookup.

```sh
python arika_actions.py tables SLES_541.61 common_actions.json
```

The reference ELF is required; the tool checks its SHA-256 before using fixed addresses. It reads the 1,000-slot pointer table at `0x49E5C0`, copied into player offset `+0x800` by `0x1CE300..0x1CE35C`. There are 153 populated slots pointing to 150 distinct tables. Physical table boundaries and zero alignment padding are validated. The JSON retains aliases, addresses and raw flags.

Each sequence record is 20 bytes:

| Offset | Type | Meaning |
| --- | --- | --- |
| +0x00 | u16 | Logical motion ID |
| +0x02 | u16 | Motion subindex passed to the resource lookup |
| +0x04 | float | Playback speed |
| +0x08 | float | Start frame |
| +0x0C | float | End frame; negative uses the motion's last frame |
| +0x10 | u32 | Sequencer flags, including control-flow behavior |

`0x1CD860` selects a slot; `0x1D6FE0` selects its segment. `0x1D78C4` reads the motion ID/subindex, and `0x1D7AF4` forwards speed/start/end to playback setup. `0x1D7120` advances or redirects the sequence. Its `0x10000` branch ends sequencing by setting the segment index to -1; `0x20000` retains the current segment for replay. Other flags are preserved as raw bits and are not fully reconstructed by this tool.

For the Goku example, common slot 210 points to `0x49D890`: motion ID 210, subindex 0, speed 1, start 0, end -1, flags `0x10000`. Goku's action package includes the corresponding named motion `m01210m0.mot` at package index 4. Its HandAni keys change the left hand from A to C to B while the right stays A. The example exports that motion; it does not execute the character's full native gameplay handler.

Character-specific native handlers can override the common pointers through `0x1CD850`. Therefore the common table dump is not a complete per-character action map. One concrete override registration is `0x1F5DAC`, which registers the table at `0x47D570` for slot 240. The table is independently inspectable with an explicit record count:

```sh
python arika_actions.py table SLES_541.61 sequence_240.json --address 0x47D570 --count 5
```

The explicit-count command makes no automatic boundary claim for arbitrary override addresses. It checks ELF bounds and finite float fields. No code here patches the executable or writes inferred control scripts back into the game.

## Validation

- 38 unit tests cover the existing archive/model/import/facial tools plus action-table bounds, key stepping/tolerance, retained hand state, looping, missing variants and hand visibility export.
- 70,432 requested left/right hand-index samples across all 1,107 motions with HandAni matched a research interpreter executing the original `0x1B7E30` sampler. Checks include authored keys, nearby times on either side, and interior times. Integer conversion is applied by the checker; this is not a full gameplay replay or a PS2 hardware capture.
- Both new glTF examples have zero Khronos validator errors or warnings.
- 7,512 skinned hand vertex poses were checked: visible variants match the original animated skeleton, and hidden variants collapse to a single point. Maximum position error was zero in that check.

Reports: `hand_reference_validation.json`, `hand_skinning_validation.json`, `action_gltf_validation.json`. Common and override table examples are included under `examples`.
