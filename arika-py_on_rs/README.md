# Super Dragon Ball Z: INFO.DAT / GAME.DAT tools

Tested against the supplied European beta, SLES_541.61. Python 3.9+; no third-party packages required. This package documents the archive and outer resource containers. arika_models.py now exports model geometry and skeletal animations; see MODEL_FORMAT.md for commands, layouts and limits. Importing edits is now supported by arika_import.py; facial ANI editing, expression previews and automatic facial animation export are in arika_faces.py. See FACE_PLAYBACK.md for timed expressions, speech pulses, blinking and combined body/face glTF export. Automatic HandAni mesh switching and common native action tables are documented in ACTION_CONTROL.md. Start with IMPORT_AND_FACES.md for the editing workflow and its layout limits.

## Use

The textured viewer now includes a **Play shake** control and optional recovered label/character emphasis demo. Its fifteen-update amplitude decay and persistent emphasis state are documented in `research/NATIVE_ITEM_EMPHASIS.md`; the trigger timing is authored.

All seven items now have per-part idle motion in the textured viewer. DRAGON SUMMONING adds two circular paths and an eight-part sway pattern. OPTIONS and DRAGON SUMMONING use host sine/cosine approximations; see `research/NATIVE_DRAGON_IDLE.md`.

OPTIONS circular idle is now available, bringing idle support to six items. Its clock/angle/offset arithmetic is checked against native instructions; sine/cosine use a documented host approximation. See `research/NATIVE_OPTIONS_IDLE.md`. DRAGON SUMMONING remains pending.

VERSUS per-part idle is now recovered, including all nine native switch cases. Five items have verified idle motion in the textured viewer. See `research/NATIVE_VERSUS_IDLE.md`; DRAGON SUMMONING and OPTIONS idle remain pending.

CUSTOMIZE now has recovered coupled per-part idle motion, bringing the textured viewer to four verified idle items. Its secondary timer uses an explicitly authored zero phase in the preview. See `research/NATIVE_CUSTOMIZE_IDLE.md`.

Per-part idle motion is now enabled for ORIGINAL, Z SURVIVOR and TRAINING, with a comparison toggle in the textured viewer. See `research/NATIVE_CHARACTER_IDLE.md`; the other character idle callbacks and emphasis remain pending.

Selected characters now have recovered whole-group entry/bounce and exit motion in the textured viewer. Toggle **Recovered character entry/exit** to compare the static pose. See `research/NATIVE_ITEM_CHARACTERS.md`; per-part idle/emphasis remains pending.

Selected-item scenery now includes the recovered scrolling texture strips for ORIGINAL, VERSUS, TRAINING and OPTIONS, correcting the missing selected sky that exposed dimmed small panels underneath.

The textured menu now uses a shared depth-sorted draw queue, correcting character-part overlap, MAIN MENU banner visibility and foreground cloud layering against the supplied native reference. Native navigation-arrow baselines are included. See `research/TEXTURED_MENU.md`.

Selected-item labels now animate in the textured viewer: recovered directional entry/hold/bounce and exit, with a **Recovered label motion** toggle. See `research/NATIVE_ITEM_LABELS.md`; the emphasis/shake phase and character/scenery motion remain pending.

Open **`previews/menu_textured.html`** for the self-contained textured menu lab: thirteen original atlases, seven selected-item poses, shared animation playback/scrubbing, layer controls, atlas inspection and PNG export. Rebuild with `arika_menu_textured.py`; see `research/TEXTURED_MENU.md` for source provenance, checks and rendering limits.

The seven shared small components now have recovered entry/bounce motion and state-gated geometry in `arika_menu_small.py`. Enable them with `examples/menu_shared_schedule.py output.json --banner --small`. See `research/NATIVE_MENU_SMALL.md` and the included seven-component SVG; item-specific animation and textured rendering remain pending.

Shared banner motion is now recovered in `arika_menu_banner.py`. Run `examples/menu_shared_schedule.py output.json --banner` for entry/exit curves integrated with the shared scheduler and companion owner. See `research/NATIVE_MENU_BANNER.md` and the included banner SVG; small-component animation and textured rendering remain pending.

`arika_menu_shared.py` now reconstructs the shared scheduler's child-call order, staggered starts, entry/exit waits and overlay fade. A reproducible owner-integrated trace and timeline are included. See `research/NATIVE_SHARED_SCHEDULER.md`; banner/small animation callbacks remain explicit caller responsibilities.

The tile/companion owner lifecycle is available through `arika_menu_companions.py --schedule owner`: verified entry/active/exit dispatch, age wrapping, update gating and restart behavior. The default isolated active schedule is preserved. See `research/NATIVE_MENU_OWNER.md`; full outer-menu timing and rendering remain pending.

Menu exports now apply a verified startup subset: loaded zero-fill plus two menu constructors. This corrects companion heights and resolves initial geometry positions, expanding the diagrams to 66 item and 10 shared quads. See `research/MENU_STARTUP.md`; these defaults do not replace captured runtime state.

Native 64-bit RNG support is available in `arika_menu_rng.py` and `arika_menu_rng.h` (C++03). Companion exports now default to `--rng native` with an explicit diagnostic seed; `--rng python` and recorded-input replay remain available. See `research/NATIVE_MENU_RNG.md`; matching a game run still requires its context state and RNG call sequence.

`arika_menu_companions.py` traces the shared ten-slot companion pool and exports animated geometry SVGs. Random inputs are explicit/diagnostic; a replayable example is included. See `research/NATIVE_MENU_COMPANIONS.md` for native helper validation and remaining runtime/rendering limits.

`arika_menu_tiles.py` exports the shared tiled element's isolated phase/placement trace and animated geometry SVG. A full-cycle example is included. See `research/NATIVE_MENU_TILES.md`; random companion effects and full menu rendering remain unimplemented.

`arika_menu_strip_preview.py` converts strip command traces to rotated quads and animated diagnostic SVGs. Included previews now cover items 0, 2, 4 and 6. See `research/ROTATED_MENU_STRIPS.md`; the display rate is authored, and native textures/compositing remain unimplemented.

`arika_menu_strips.py` exports isolated menu strip clock and clipped sprite-command traces, including source UV changes and per-piece depth. See `research/NATIVE_MENU_STRIPS.md` and the two full-cycle example traces. Textured rendering and full menu playback remain pending.

Plain-sprite geometry is available in `arika_menu_plain.py`; the startup-baseline SVG includes 66 item quads and a separate ten-quad shared-layer panel. See `research/MENU_PLAIN_SPRITES.md` and `research/MENU_STARTUP.md` for provenance and playback limits.

`arika_menu_first.py` extracts first-group menu sprites, scaled decorations, scrolling-strip parameters and particle templates. See `research/MENU_FIRST_COMPONENTS.md` for commands and runtime gaps; special-effect playback remains unimplemented.

Menu geometry is available through `arika_menu_layout.py`: 38 sprite parts and seven item overlays, with anchors, texture indices, UVs and native positions. It exports diagnostic SVG/JSON; see `research/MENU_LAYOUT.md`. Shared setup rectangles, small components and draw-call structure are in `research/MENU_LAYERS.md`. Full background assembly and native animation playback remain unimplemented.

Main-menu research is in `research/MAIN_MENU.md`. Run `python arika_menus.py SLES_541.61 main_menu_map.json` to extract the seven-entry navigation/routes, English help descriptions, and recovered sprite tables from the supported ELF. `arika_menu_logic.h` provides partial C++03 navigation/routing logic, including selection-history flags; menu rendering and lifecycle behavior remain unimplemented.

For the material/textured scene editor, launch `arika_scene_editor.py` after installing `requirements_scene_editor.txt`. It uses WebGPU (D3D12/Vulkan/Metal), includes project/glTF material edits, and preserves the native STG transform workflow. See SCENE_EDITOR.md.

Launch `python arika_stage_editor.py` for the Tkinter scene/transform editor and collision-map preview. See STAGE_EDITOR.md.

Stage tools are now available in `arika_stages.py`: STG hierarchy inspection, HIT polygon/OBJ export, stage asset inventory, and authored glTF scene assembly with separate templates/effects/collision scenes. Start with STAGES.md. Runtime destruction, visibility controls and scripts remain unresolved; scene transform/link interpretation is explicitly marked inferred.

`arika_action_player.py` now exports automatic common-action skeletal previews: clock carry, supported startup settings, local pose blending, animated-channel dispatch, and discrete hands. It requires no authored switch schedule. See ACTION_POSES.md for commands, examples, and limits; full gameplay callbacks, overrides, root motion and IK remain outside this subset.

`arika_action_clock.py` traces automatic common-action startup, advance/replay/stop/jump, carry forwarding, and native blend countdown inheritance/reset. It derives settings from records and needs no authored switch times. See ACTION_STARTUP.md. This command remains a scalar-only view of the clock used by the skeletal player.

`arika_transitions.py` now previews explicit clip-switch schedules using the native clock/blend kernels. It keeps live poses and hand selections across motions, handles the incoming one-frame bridge in either direction, and splits ticks at authored switch times. See EXPLICIT_TRANSITIONS.md. Switch times remain user-authored; automatic native action orchestration is still unported.

Native pose sampling is available through `arika_pose.py`: component masks, live-pose translation/rotation/scale blending, native fallback values, and the isolated native segment clock. `--loop` now blends the last and first poses through the native one-frame loop gap in either direction. See NATIVE_POSE.md for commands and validation limits. Full native action orchestration remains unimplemented.

Native scalar timing research is available through `arika_clock.py`: float32 position updates, end-time carry, reverse/loop behavior and blend countdown traces. See NATIVE_CLOCK.md. The action sequence preview still uses its authored-frame clock.

Common action sequence plans, samples and animated previews are now available in `arika_sequence.py`. It follows verified stop/replay/jump/advance behavior, resolves motions through CHT, carries hand selections, and optionally runs explicit facial events. See ACTION_SEQUENCES.md for commands and the authored-frame preview timing model.

CHT action-to-animation mapping is now available through `arika_cht.py map`, `arika_actions.py resolve`, and `arika_actions.py motion-id`. Facial exports can select body motion with `--cht`, `--motion-id`, `--variant`, and explicit `--bank` packages. See MOTION_BINDINGS.md for commands and the verified layout.

Facial event schedules are now supported: `arika_faces.py timeline-sample` and `timeline-animate` start multiple ANI programs within one body-and-hands clip. `sample`/`animate` also accept `--face-start` for a single delayed program. See FACIAL_EVENT_TIMELINES.md and examples/goku_face_events.json for runnable commands and timing limits.

Keep original backups. Run these commands where INFO.DAT and GAME.DAT are located, using the path to arika_dat.py as appropriate:

```sh
python arika_dat.py list INFO.DAT --game GAME.DAT
python arika_dat.py extract INFO.DAT GAME.DAT extracted
python arika_dat.py decode-info INFO.DAT INFO.decoded.bin
python arika_dat.py encode-info INFO.decoded.bin INFO.encoded.bin
python arika_dat.py repack INFO.DAT GAME.DAT rebuilt
python arika_dat.py repack INFO.DAT GAME.DAT modified --replacements extracted
```

`repack` writes a new INFO.DAT/GAME.DAT pair in the output folder. It never overwrites either input. Replacement files are matched by relative asset name; missing replacement files retain original content. Sizes and sector offsets are recalculated. The rebuilt GAME.DAT retains the original total size, so larger replacements must fit in the available space. Preserve the pair together. Do not place the decoded index in the game: the game expects the encoded form.

An unmodified full extraction/repack of the supplied files was verified byte-for-byte against both originals. Modified resources still need testing in the game. The extracted disc backend also has file-size metadata; this tool retains the outer archive sizes so that metadata does not need changing.

Texture and motion inspection:

```sh
python arika_dat.py split-container extracted/dis/main_menu.pix menu_chunks
python arika_dat.py tim2-png menu_chunks/0000.tm2 menu.png
python arika_dat.py split-container extracted/path/to/model.mdl model_chunks
python arika_dat.py split-rfsm extracted/path/to/motion.pmt motion_chunks
python -m unittest discover -s . -v
```

Use actual paths from files.csv for models and motions. `extract --pattern "*.pix"` selects assets using a glob. Output conflicts are rejected unless `--overwrite` is supplied to extraction/splitting. TIM2 previews support the sample's single-picture, single-mipmap RGBA32, indexed4 and indexed8 formats. Alpha is expanded from PS2's 0–128 range; `--linear-clut` disables the default indexed8 palette permutation. PNG previews are not a texture import pipeline.

## INFO.DAT

The hybrid Rust backend now exposes `Archive.capacity` as a dictionary with
`active_entries`, `record_capacity`, `spare_record_slots`,
`trailing_bytes`, and `info_size`. The `arika_dat.py list` summary
shows active entries and spare INFO slots. Rebuild the hybrid native library
after updating; older compiled libraries do not export
`arika_archive_capacity`.

For the US SLUS_214.42 disc, 98,304 bytes allow 2,047 complete 48-byte
records after the 48-byte header; 1,930 are active and 117 are spare.
A published boot log prints `File Len : 2047`, but `ARKD_DVD.IRX`
has not been disassembled to establish whether this is a fixed game-side
limit or a file-size-derived value. This API reports *physical capacity*,
not a verified maximum number of loadable assets.


All integers are little-endian. The file is 98,304 bytes, containing a 0x30-byte header, 1,934 records of 0x30 bytes, then padding. The first 16 bytes are the signature and codec key: `7F 77 77 77 2E 61 72 69 6B 61 2E 63 6F 2E 6A 70` (`\x7fwww.arika.co.jp`).

For every byte at offset i >= 16, including trailing padding:

```text
swap_nibbles(x) = ((x & 15) << 4) | (x >> 4)
decoded[i] = (~swap_nibbles(encoded[i]) - key[i & 15]) & 255
encoded[i] = swap_nibbles(~(decoded[i] + key[i & 15]) & 255)
```

The first 16 bytes remain unchanged. Byte zero varies between releases (EU beta: `7F`, EU: `11`, USA: `C2`, JPN: `60`, arcade (DB1 Ver. B): `BB`); validation checks only bytes 1–15, `www.arika.co.jp`. All 16 bytes, including byte zero, remain part of the codec key. The sizes and record counts above describe the EU beta sample. The codec is reversible obfuscation. arika_info.h supplies equivalent C/C++ code and structure definitions; callers must handle little-endian conversion on other architectures.

Rebuilding INFO.DAT requires a seed INFO.DAT: the 16-byte codec key, including region-specific byte 0, exists only in INFO.DAT and is not stored in GAME.DAT, so GAME.DAT alone cannot be re-encoded. Keep an original INFO.DAT of the matching region as the seed; encode-info/repack derive the key from it.

| Header offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 16 | Signature and codec key |
| 0x10 | 28 | Seven reserved u32 values, all zero in this sample |
| 0x2C | 4 | File count, 1934 |

Records begin at 0x30:

| Record offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 32 | NUL-terminated CP932 filename |
| 0x20 | 4 | Unknown u32, all zero in this sample |
| 0x24 | 4 | Starting sector in GAME.DAT |
| 0x28 | 4 | Allocated sector count |
| 0x2C | 4 | Actual file size in bytes |

One filename contains Japanese text; use CP932 rather than ASCII. The table ends at 0x16AD0. The remaining 5,424 **encoded** bytes are 0x40. Decoding them produces nonzero repeating bytes; preserve them for exact encoding roundtrips.

Independent runtime confirmation: the complete decoded 98,304-byte buffer matches both EE RAM at 0x015CE400 and IOP RAM at 0x000BE300 in the supplied stage_stall.bin snapshot. In that snapshot ARKD_DVD is loaded at IOP 0x67800; the initialization/decoder routine begins at 0x67AC0 (module RVA 0x2C0). Nibble swaps appear at 0x67B88/0x67B8C, inversion at 0x67BBC, and key subtraction at 0x67BF4. The table pointer is stored at 0x72B04. These are revision/snapshot-specific addresses. EE lookup at 0x1C0050 walks 0x30-byte records and reads their byte sizes.

## GAME.DAT

There is no archive-wide header or compression layer. Payloads are stored directly at `sector_offset * 2048`; read `byte_size` bytes. All sample records have `sector_count = ceil(byte_size / 2048)` and contiguous extents.

The indexed region occupies 338,550 sectors / 693,350,400 bytes (0x2953B000). The full archive is 730,050,560 bytes. The final 35 MiB is zero-filled and unindexed. Padding within the final sector of an asset is often nonzero; it must be preserved for a byte-identical no-op rebuild. The repacker preserves that padding for unchanged-size assets and preserves the original tail at its absolute position.

## FPIX and FMDL containers

732 FPIX containers and 476 FMDL containers were found by signature, including backup/versioned filenames.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | char[4] | FPIX or FMDL |
| 0x04 | u32 | Total file size |
| 0x08 | u32 | Chunk count |
| 0x0C | u32 | Format value, 0x100 in sample |
| 0x10 | bytes[16] | Reserved |
| 0x20 | u32[count] | Absolute chunk offsets |

Every chunk begins with a four-byte tag and u32 size, including its header. All chunk extents were checked against the next offset/file end. FPIX contains 3,438 XPIX chunks; each has a 32-byte wrapper followed by TIM2. Of those textures, 3,431 are indexed8, six indexed4, and one RGBA32. All have TIM2 version 4, format 1, one picture and one mipmap. Indexed palettes contain RGBA32 entries. Indexed8 CSM1 palette addressing swaps index bits 3 and 4. The preview uses the conventional PS2 CLUT permutation; see ps2dev/gsKit ee/toolkit/src/gsToolkit.c for a related implementation.

FMDL tags include DMOD, DMAT, XTEX, XMON, XCUD, XMTX, DHIE and XNON. The splitter exports them intact. Geometry, hierarchy, palettes, material assignments and vertex encodings are documented in MODEL_FORMAT.md and handled by arika_models.py.

## RFSM / L3 motion packages

57 .pmt packages contain 1,399 raw MOT2 motions. L3 is a tag here, not evidence of compression.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | char[4] | RFSM |
| 0x04 | char[2] | L3 |
| 0x06 | u16 | Motion count |
| 0x08 | u32 | Shared block offset, 16 + count * 32 |
| 0x0C | u32 | Shared block end |

Each 32-byte directory record contains a 16-byte CP932 name, absolute motion offset, motion size, an unknown u32 (zero in sample), and a format value (0x10006 in sample).

The shared block begins with u16 motion count, u16 bone count, then three u32 absolute offsets: bone names, variable binding data, and bone flags. Bone names occupy fixed 16-byte records. There is one flag byte per bone; these are **not established parent indices**. The first MOT2 starts after the shared block, aligned to 16 bytes. MOT2 begins with its magic and total size. Inner motion tracks and the variable binding data are now decoded by arika_models.py; see MODEL_FORMAT.md. Keep shared.bin and motion_archive.json alongside exported motions; a MOT2 alone omits that context.

Other assets include ASE sound-effect banks, AMS music streams, ANI facial timelines, EBZ, SPT, CHT hit/collision data, HIT, STG, PAS, ICO, FFON and a CP932 text file. ANI facial timelines are documented in IMPORT_AND_FACES.md. ACTION_CONTROL.md corrects the earlier ASE/AMS script classification and documents common native action tables and HandAni control. ASE/AMS WAV export is available through arika_audio.py; see AUDIO_EXPORT.md. SPT token decoding and the native facial slot trace are documented in SCRIPT_CONTROL.md. CHT motion bindings and nested block extents are now decoded by arika_cht.py; see MOTION_BINDINGS.md. Collision payload semantics and the other resource formats listed here remain outside this release. files.csv/files.json enumerate every asset and signature.

## Verification

validation.json records the original SHA-256 values, full extraction checks, container counts, and exact unmodified rebuild result. Six unit tests cover the codec, extraction/repacking including replacements, unsafe paths/extents, FPIX, RFSM and TIM2 fixtures. The C/C++ codec was also checked against the original INFO.DAT. previews/menu_0000.png is a decoded menu atlas from the uploaded game.

Audio WAV import is available through `arika_audio_import.py`; see `AUDIO_EXPORT.md` for rebuilding ASE/AMS and repacking GAME.DAT.
