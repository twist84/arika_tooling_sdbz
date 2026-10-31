# Importing edits and working with expressions

This pass adds working importers, not just resource inspection. All tools require Python 3.9+ and use only its standard library. Always use the original asset as the import template; output goes to a different file. This release edits existing topology and channel layouts. It does not build new meshes or motion-channel bindings from scratch.

## Model editing through glTF

Export with this version, edit, then import:

```sh
python arika_models.py model-gltf extracted/ply/p01/p01a.mdl goku.gltf --mesh MeshBody --mesh MeshHair --mesh ShapeHeadAB --mesh MeshLHandA --mesh MeshRHandA
# Edit goku.gltf in an editor which retains custom vertex attributes.
python arika_import.py model-gltf extracted/ply/p01/p01a.mdl goku_edited.gltf p01a_modified.mdl
```

The exporter adds a `_ARIKA_VERTEX` custom scalar attribute identifying each original vertex. Keep it through the editor's import/export cycle. The importer uses it to handle vertex and face reordering, and requires unchanged oriented triangle topology and material-section grouping. If a source vertex is split into several editor vertices, their imported values must agree. Missing source vertices are retained unchanged. Missing `_ARIKA_VERTEX` produces an error; the importer does not guess vertex correspondence. The previous release's glTF files do not have this attribute and must be exported again.

This workflow has been tested with the tools' own glTF files and synthetic accessor mutations. A particular editor's handling of custom attributes, skinning and morph targets still needs checking; an editor roundtrip is not claimed as validated.

Supported inputs are glTF 2.0 JSON and GLB, embedded or adjacent external binary buffers, interleaved accessors, and normalized integer attributes. Required extensions/compressed geometry and sparse accessors are rejected. Import positions, normals, UVs, existing vertex colors, joint weights, and existing morph endpoint geometry. Object transforms on rigid meshes are converted back to the source bone's local space. For skinned meshes keep the original armature rest transforms and inverse bind matrices, and apply mesh-object transforms before exporting.

Keep topology, mesh identities, and material groups. Shader/material/texture edits in the glTF are not imported: edit material fields through JSON and edit/rebuild textures separately. Nonzero default morph-pose weights are runtime expression controls, so those preview files are rejected for geometry import. Edit morph target geometry with the preview weight reset to zero. Negative-weight prop exports that needed clamping are also rejected for glTF import; use JSON to preserve their authored weights.

Changes below roughly 1e-6 relative/absolute float precision are treated as conversion noise. Untouched normals, quaternion signs, normalized weights and clamped color previews are restored to their original float values when equivalent. This allows byte-identical no-op imports rather than baking export normalization into the game data.

## Model editing through JSON

```sh
python arika_models.py model-json extracted/ply/p01/p01a.mdl goku.json
# Edit goku.json.
python arika_import.py model-json extracted/ply/p01/p01a.mdl goku.json p01a_modified.mdl
```

Editable fields:

- `meshes[].vertices[]`: position, normal, uv, color_ps2 where present, joints/weights where present, and morph_position/morph_normal where present.
- `nodes[]`: scale, translation, and either euler_degrees or rotation quaternion. Do not edit both rotation representations at once.
- `materials[]`: color_a, color_b, and an existing texture index.

Keep mesh/vertex counts, names, flags, topology, ADC/orientation, hierarchy links and palettes unchanged. Joint references are hierarchy-node indices; when a nonzero influence needs a bone absent from a mesh palette, the importer fills an unused palette slot and updates its palette mask. Maximum 32 palette slots. Signed weights are allowed in JSON and must sum to one. Existing indices and packet bytes remain intact.

When positions/endpoints change, the importer recomputes that mesh's XCUD sphere to cover both endpoints. Other unknown fields and padding are preserved. JSON source checksums reject a different source revision. The completed output is parsed again before it is written.

## Animation editing

JSON path:

```sh
python arika_models.py motion-json extracted/ply/p01/p01sel.pmt selection.json
# Edit selection.json: motions[].nodes[].tracks.<component>.values.
python arika_import.py motion-json extracted/ply/p01/p01sel.pmt selection.json p01sel_modified.pmt
```

An individual MOT2 file is also accepted by both JSON commands. Edit `nodes[].tracks.translation/rotation/scale.values`; rotation is unit XYZW. Preserve frame count, fps, node descriptors, animated flags, channel identities, key counts and bone bindings. `constant_vectors` and descriptor indices are inspection fields; edit component values instead. JSON can change the shared time array only when all animated channels in that component group receive the same replacement times.

Shared constant vectors use copy-on-write: changing a constant component clones its vector and changes only that node's reference. Other components sharing the old vector remain untouched. A cloned pool may grow MOT2 by multiples of 16 bytes. The RFSM importer updates motion sizes and aligned payload offsets, preserving shared bone metadata. Unmodified package imports return the original bytes exactly, including original padding.

glTF path:

```sh
python arika_models.py model-gltf extracted/ply/p01/p01a.mdl animated.gltf --motion extracted/ply/p01/p01sel.pmt --mesh MeshBody --mesh MeshHair --mesh ShapeHeadAB --mesh MeshLHandA --mesh MeshRHandA
# Edit its named animation curves.
python arika_import.py motion-gltf extracted/ply/p01/p01sel.pmt animated_edited.gltf p01sel_modified.pmt --animation m01075m0l.mot
```

Without --animation, all animations present in the glTF are imported by their exact source names. The flag can be repeated. Bone names map through the original RFSM tables. LINEAR and STEP curves are sampled at the original component-group key times. Rotation sampling uses shortest-path quaternion interpolation. Curves must cover the original times. New animated channels, changed duration/frame count, and CUBICSPLINE samplers are not supported in this pass. A previously constant component can be changed to another constant but cannot become time-varying. Missing curves/motions remain unchanged. Texture, visibility, morph-weight and scene-control channels are outside MOT2 and rejected by this importer.

## Repack into INFO.DAT / GAME.DAT

The game reads its internal archives, so editing files under `extracted` alone does not change what it loads. Put changed assets into a replacement tree using their original relative names:

```text
replacements/
  ply/p01/p01a.mdl
  ply/p01/p01sel.pmt
  ply/p01/p01.ani
```

Then:

```sh
python arika_dat.py repack INFO.DAT GAME.DAT rebuilt --replacements replacements
```

Use the rebuilt INFO.DAT/GAME.DAT pair together in the disc folder, keeping originals as backups. The archive repacker adjusts internal sizes/sectors while retaining the original outer DAT sizes. Motion growth therefore fits in the existing unindexed capacity. These tools do not modify the source ELF or regenerate recompilation code for asset-only edits.

Validation included a modified FMDL vertex, a modified constant causing MOT2/RFSM growth, and a changed facial record. Repacking and reading all 1,934 assets recovered the three exact replacements; all 1,931 other payloads were byte-identical. GAME.DAT retained its original 730,050,560-byte size. This was a binary/container test; actual playback in the game has not been tested.

## Facial ANI files

Export/edit/import:

```sh
python arika_faces.py json extracted/ply/p01/p01.ani face.json
# Edit records[].time, expression or behavior inside programs[].
python arika_faces.py import-json extracted/ply/p01/p01.ani face.json p01_modified.ani
```

The parser handles all 20 supplied .ani files, including ply/sel.ani and p22's extra group. They contain 325 unique programs and 4,865 records. Some program offsets are shared; JSON lists each physical program once, so aliases cannot accidentally receive conflicting edits. Keep groups, offsets, record counts and END flags unchanged. Times are seconds and execute in file order, not sorted order. A few original programs contain nonmonotonic timestamps, so those are preserved rather than “fixed.”

| File offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | u32 | Group count |
| 0x04 | bytes[12] | Reserved in sample |
| 0x10 | group[count] | u32 program_count, u32 absolute offset of u32 program pointers |

Each program consists of 8-byte records:

| Record offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | float | Due time in seconds |
| 0x04 | u8 | Expression selector |
| 0x05 | u8 | Behavior selector |
| 0x06 | u16 | Flags; 0x1000 ends the program |

All supplied flags are 0 or 0x1000. The runtime has additional branch/jump handling for 0x4000, but it does not occur in these samples and is rejected rather than inferred by the tool.

Evidence from the original ELF:

- 0x3A1D10 relocates group pointers and each program pointer; 0x3A1DE0 returns a group's table.
- 0x1E60A0 starts a program in the player controller.
- 0x1E6674–0x1E66C8 compares record times, reads END/jump flags and advances record indices.
- 0x1E6838 reads the previous record's expression and behavior bytes.
- Table 0x47C1D0 maps expression indices 0..7 to pair states `[1,3,2,4,5,0,0,0]`.
- Table 0x47C1F0 maps behavior indices to amplitudes `[0.7,0.1,0.3,0.5,1,0,0,0]`. Behaviors 5 and 6 have dedicated logic: timed pulses versus repeated randomized pulses. They are not ordinary amplitude-zero events.
- 0x1D5A50 selects a head pair, blend and normal/super branch; 0x1D5BB0 selects left/right hand variants. Blinking also has independent controller state, so an ANI timeline alone is not the entire facial system.

## Expression previews

The six ordinary pair states are AB, AC, AD, BC, BD and CD. Super variants use SAD aliases. The actual available meshes vary by model. Preview an existing pair:

```sh
python arika_faces.py pose extracted/ply/p01/p01a.mdl face.gltf --pair AC --blend 0.5
python arika_faces.py pose extracted/ply/p01/p01a.mdl blink.gltf --pair AB --blend 1
python arika_faces.py pose extracted/ply/p01/p01a.mdl super_face.gltf --pair SAD --blend 0.5 --super-hair
```

`--left-hand B` and `--right-hand C` choose available hand variants. This produces a textured static glTF expression with a morph weight. Runtime 0x1D5B44–0x1D5BA0 selects a texture endpoint by rounding blend + 0.5; the preview follows the resulting endpoint material's texture through the HeadTex control mesh. Thus changing AB can close Goku's eyelids even when its two geometry copies are identical. AC/AD also deform his mouth, as shown in previews/expression_endpoints.png.

Automatic facial playback now exports timed expressions, randomized speech pulses, idle blinks and texture switches, optionally combined with skeletal motion. See FACE_PLAYBACK.md for commands and validation. External gameplay triggers and script-driven hair/form transitions remain explicit export choices. HandAni-driven hand switching is now supported; see ACTION_CONTROL.md.

## Checks

- 476/476 model JSON roundtrips bit-identical.
- 57/57 RFSM JSON roundtrips bit-identical, covering all 1,399 MOT2 motions.
- 20/20 facial ANI JSON roundtrips bit-identical.
- Selected and all-variant Goku glTF geometry/animation roundtrips plus rigid stage/shadow/effect samples checked.
- Mutation tests exercise vertex edits/culling bounds, source IDs, dynamic keys, shared-constant isolation, RFSM relocation, alias programs, malformed structure, and source-file protection.
- 38 unit tests pass. C/C++ structure sizes compile with static assertions.

The ZIP retains the earlier archive tools and research notes. import_validation.json, gltf_import_validation.json and import_integration.json record this pass.
