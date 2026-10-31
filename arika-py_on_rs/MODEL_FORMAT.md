# FMDL geometry and MOT2 animation: second research pass

Scope: the supplied European beta SLES_541.61. This extends the archive research with a working model and skeletal-animation exporter. Python 3.9+, standard library only. C/C++ layout declarations are in arika_models.h.

## Commands

First extract INFO.DAT/GAME.DAT with arika_dat.py. Then, from the tools directory:

```sh
python arika_models.py model-gltf extracted/ply/p01/p01a.mdl goku.gltf --motion extracted/ply/p01/p01sel.pmt --mesh MeshBody --mesh MeshHair --mesh ShapeHeadAB --mesh MeshLHandA --mesh MeshRHandA
python arika_models.py model-obj extracted/ply/p01/p01a.mdl goku.obj --mesh MeshBody --mesh MeshHair --mesh ShapeHeadAB --mesh MeshLHandA --mesh MeshRHandA
python arika_models.py model-json extracted/ply/p01/p01a.mdl goku_geometry.json
python arika_models.py motion-json extracted/ply/p01/p01act.pmt goku_moves.json
```

The glTF is one self-contained .gltf file with embedded buffers and PNG textures. It includes an editable hierarchy, skin joints/weights, and animations. A sibling .pix matching the .mdl basename is detected automatically; `--textures path.pix` overrides it. `--motion` accepts an RFSM .pmt and can be repeated. By default all its motions are included; `--motion-index 1` selects a package index and can also be repeated. Without --motion, the exporter writes the authored bind pose.

`model-obj` exports a static world-space bind pose with UVs/normals; it does not include materials, skinning or animations. `model-json` preserves decoded vertex records, raw skin weights, palettes, hierarchy links, local SRT, material fields and triangles. `motion-json` accepts either a whole RFSM .pmt or an individual MOT2 .mot; the package is needed to obtain bone names. Quaternion components/signs are retained in JSON; glTF rotations are normalized and sign-adjusted for shortest-path interpolation.

Without `--mesh`, every authored mesh variant is included. Player models contain alternate hands, hair and facial parts which overlap when all displayed. Repeat --mesh to select names or quoted globs. Inspect model-json or the glTF node names to choose variants. The example command selects a coherent Goku variant; it does not attempt to reproduce the game's runtime variant-switching scripts.

The included examples/goku_selection.gltf contains that selection and all three selection-package motions. previews/model_bind_pose.png and previews/motion_preview.gif were rendered from the exported glTF, including its embedded textures, skeleton, inverse bind matrices and animation accessors.

## Validation

Every one of the 476 FMDL payloads parsed successfully, covering 14,800 mesh records, 4,824,347 stored vertices, and 2,425,131 triangles. These totals include duplicate character variants and backup assets. The parser matches each XMOD's stored vertex and triangle counts, every DMA material assignment, and every VIF packet's record extent.

All 57 RFSM packages / 1,399 MOT2 motions passed channel extent, time order, descriptor, and forward/reverse bone-binding checks. They contain 64,364 motion-node records, 49,759 constant vectors, 2,843 animated translation channels and 33,743 animated rotation channels. No animated scale channels occur in this sample, so dynamic-scale support follows the same header structure but has not been exercised on real assets.

Five glTF exports were checked with Khronos glTF Validator: selected Goku with three selection motions, all Goku variants with an action motion, a rigid shadow, a stage model, and a skinned stage prop. All five report zero errors and zero warnings. Ten unit tests cover archive/texture tools plus packet continuation, winding, skeleton transforms/cycles, key tracks, malformed data, and glTF skin/animation output. model_validation.json and gltf_validation.json record the checks.

A textured bind pose and 24 sampled animation frames were inspected. This is not a frame-for-frame comparison against original gameplay, nor a complete reproduction of the game's renderer.

## FMDL hierarchy

DHIE is a directory chunk with a normal 0x20-byte header and u32 child offsets. Its XHIE child contains a 0x20-byte header followed by 0x40-byte node records. XNON holds the corresponding sequential NUL-terminated CP932 node names after its 0x20-byte header.

| Record offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | i32 | Node index |
| 0x04 | i32 | Parent index, -1 for a root |
| 0x08 | i32 | First child index, -1 for none |
| 0x0C | i32 | Next sibling index, -1 for none |
| 0x10 | float4 | Local scale XYZ, padding W |
| 0x20 | float4 | Local Euler angles XYZ in degrees, padding W |
| 0x30 | float4 | Local translation XYZ, padding W |

Local transforms use T * Rz * Ry * Rx * S in column-vector notation. World transforms compose parent * local. The quaternion half-angle formula is confirmed in the original ELF at EE 0x1A0244–0x1A0300, within the node creation routine at 0x1A0100. That code converts degrees to radians and calculates quaternion XYZW; it is not an Euler-order guess based only on appearance.

XMTX contains a 0x20-byte header followed by 32 i32 hierarchy indices per mesh (0x80 bytes). -1 denotes an unused slot. A rigid mesh attaches to slot zero's hierarchy node. Skinned vertex joint addresses select this palette. XMON contains sequential NUL-terminated mesh names.

## XMOD geometry

DMOD is a directory of XMOD chunks. The first DMA tag in each XMOD is at +0x1A0. XMOD +0x30 stores the vertex count, +0x34 the triangle count. +0x0C holds vertex flags, copied at +0x20. Other prefix fields are preserved/described conservatively in arika_models.h.

Each DMA RET tag is 16 bytes, with a QWC in its low 16 bits. Its following QWC * 16 bytes form a VIF stream. Additional material sections follow as additional RET blocks in the same XMOD. All observed streams use NOP, STCYCL, UNPACK V4-32, and MSCNT. Each UNPACK has two float4-sized control/GIF vectors, then the vertex records. Its vertex count is the GIF tag's low 15 bits. This count and the flag-derived record stride exactly account for every UNPACK payload.

| Flags | Vertex stride | Layout in 16-byte vectors |
| --- | --- | --- |
| 0 / 1 | 48 | position, normal, STQ |
| 2 / 3 | 80 | position, normal, STQ, palette addresses, weights |
| 4 | 64 | position, normal, color, STQ |
| 6 | 96 | position, normal, color, STQ, palette addresses, weights |
| 11 | 80 | position, normal, STQ, second position, second normal |

Position XYZ and normal XYZ are floats. Position W is read as a u32: bit 15 suppresses a triangle at that vertex (ADC). A non-suppressed vertex forms a triangle with the two preceding vertices, including when they lie in the preceding UNPACK packet. Resetting strip history for each packet loses triangles. Normal W carries the authored orientation sign; swap the first two indices when it is negative. The exporter writes explicit triangle lists.

STQ stores texture coordinates; the samples use the first two components as UV. The vertex-color vector contains PS2-scale RGBA floats (128 represents full scale). The exporter converts these to [0,1]. Skin palette addresses are u32 values divisible by four; divide by four and index the mesh's XMTX row to obtain a hierarchy node. The following float4 supplies corresponding weights. Weights sum to one within float precision. Skinned positions are already in the authored model bind space. glTF inverse bind matrices are inverse hierarchy world matrices; rigid positions remain local to their attached node.

One prop, stg/sgmk01/sgmk01.mdl, contains 20 vertices with negative weights / compensating weights above one. JSON preserves these. glTF requires nonnegative weights, so the exporter rejects that asset unless `--clamp-skin-weights` is supplied. With that option it clamps negative weights to zero, renormalizes, prints a warning and annotates the mesh extras. Its animation is consequently an approximation.

Flags 11 contain alternate position/normal data rather than bone addresses/weights. The exporter retains these and exposes the difference as a glTF morph target, initially at zero weight. Many are copies of the base data; others differ. The facial controller is now decoded and can drive these morphs and texture endpoints in baked glTF animations; see FACE_PLAYBACK.md. The general model exporter leaves them at zero weight unless requested.

## Materials and textures

DMAT is a directory containing XMAT and XMAL. XMAT has a 0x20-byte header and 0x30-byte records: two float4 color vectors followed by an i32 texture index and 12 further bytes. The complete shading meaning of the color vectors and remaining fields is not established; JSON calls them color_a and color_b. The glTF preview uses white base color and ordinary rough, nonmetallic shading.

XMAL contains 32 i32 material indices per mesh, with -1 in unused slots. Each nonnegative index corresponds in order to one DMA block of that mesh. This correspondence holds across every model. The XMAT texture index selects an XPIX texture in the sibling FPIX file. Textures are decoded by the existing TIM2 exporter and embedded in glTF. Native outlines, cel shading, material animation, additive effects and precise transparency modes are not reproduced. Materials use double-sided alpha masking for inspection.

## MOT2

All offsets below are relative to the MOT2 start. Integers are little-endian.

| Header offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | char[4] | MOT2 |
| 0x04 | u32 | Total size |
| 0x08 | float | Frames per second, 60 in supplied motions |
| 0x0C | u16 | Frame count |
| 0x0E | u16 | Motion-node count |
| 0x10 | u16 | Constant float4 count |
| 0x12 | u16 | Total animated channel count |
| 0x14 | u32 | Node descriptor array offset |
| 0x18 | u32 | Constant float4 pool offset |
| 0x1C | channel[1] | Translation channel group |
| 0x28 | channel[1] | Rotation channel group |
| 0x34 | channel[1] | Scale channel group |

Each 12-byte channel group contains u16 channel_count, u16 key_count, u32 vectors_offset, u32 times_offset. All channels in a group share a float time array, measured in seconds. Values are float4 and stored channel-major: all keys of channel zero, then all keys of channel one, etc. When channel_count is zero, key_count/time offsets may contain unused values and must not be dereferenced.

Each 8-byte node descriptor contains u16 flags, translation_index, rotation_index, scale_index. Flag bits 1/2/4 select animated translation/rotation/scale. For an animated component, its index is a **vector index** into that group's array (channel_number * key_count). For a constant component, its index selects a float4 in the shared constant pool. Translation/scale use XYZ; rotations are XYZW quaternions. The constant pool ends exactly where the node descriptor table begins in every sample.

The loader at EE 0x1B12F0 relocates the eight offsets at +0x14/+0x18/+0x20/+0x24/+0x2C/+0x30/+0x38/+0x3C. It computes duration as frame_count / fps. The last authored frame is normally at (frame_count - 1) / fps. Component sampling reads the descriptor flags and indices, choosing a constant float4 or adjacent animated float4 values. Translation uses linear interpolation; the quaternion interpolation routine at 0x1B2C80 performs shortest-path slerp with a near-parallel linear fallback. The glTF exporter uses LINEAR rotation samplers, normalizes values, and fixes successive quaternion signs. It holds shorter/constant channels through the last authored frame. Looping behavior belongs to the game's caller and is not encoded as a glTF loop setting.

## RFSM bone bindings

The previously unknown variable area between bone names and bone flags begins with **12 bytes per motion**:

| Record offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | u32 | Unknown/runtime pointer field, zero on disk in sample |
| 0x04 | u32 | Absolute channel-to-bone u16 array offset |
| 0x08 | u32 | Absolute bone-to-node i16 array offset |

The forward array has one entry per animated channel: translation channels, then rotation channels, then scale channels. Each entry selects a shared RFSM bone name. The reverse array has one i16 per shared bone name: a MOT2 node index, or -1 if that bone is absent from this motion. Every animated channel's forward entry maps back to its node through the reverse table; this was validated for all 1,399 motions. Reverse mappings also name some nodes whose components are entirely constant.

The glTF exporter matches these names to FMDL hierarchy names, preserving the model's rest transforms for unnamed/unmapped helper nodes. Names not found in the model are listed in animation extras. Raw standalone MOT2 files retain node indices but do not contain these shared names or the model hierarchy.

## Remaining work

CHT logical-motion bindings and nested block extents are now decoded by arika_cht.py; see MOTION_BINDINGS.md. Collision payload semantics remain unimplemented.

The geometry and skeletal track layers are decoded and exportable. arika_import.py now imports edits back into FMDL/MOT2 with existing topology/channel layouts; see IMPORT_AND_FACES.md. arika_faces.py also edits ANI records, previews expression pairs and exports automatic facial playback; see FACE_PLAYBACK.md. The tools do not reproduce the game's shader pipeline, decode collision data in CHT, reconstruct external gameplay facial/hair/form triggers, or apply game-specific root-motion/IK rules. Those control layers are separate from the float tracks exported here.

Automatic hand selection from the motion HandAni track and common native action table inspection are now supported; see ACTION_CONTROL.md. Hand control uses stepped keys, not skeletal interpolation.

ASE/AMS audio export is also available; see AUDIO_EXPORT.md.
