# Stage scene and collision tools

`arika_stages.py` inspects STG scene records and HIT collision resources, exports collision polygons to OBJ, and assembles static stage glTF previews from their sibling MDL/PIX assets. Python 3.9+, standard library only. `arika_stages.h` provides the checked disk structure sizes for C/C++.

The exporter preserves authored mesh instances and separates template roots from the live scene. Runtime visibility, spawning, destruction and stage scripts are not executed. In particular, opaque control records are retained in JSON and represented as identity groups in previews. This is a stage-research tool, not a complete recreation of the stage runtime.

## Commands

First extract the stage assets:

```sh
python arika_dat.py extract INFO.DAT GAME.DAT extracted --pattern "stg/*"
python arika_stages.py list extracted stage_inventory.json
python arika_stages.py scene-gltf extracted/stg/s01/s01a.stg stage.gltf
```

The final command finds the matching `.mdl`, `.pix`, and `.hit`. `--model`, `--textures`, and `--hit` override them. Explicit missing overrides are errors. Without a sibling HIT or PIX, the exporter can still write model geometry. A sibling model is required.

The self-contained glTF has these scenes:

| Scene | Contents |
| --- | --- |
| Stage | The authored STAGE root and its mesh instances; default scene |
| Effects | The separate EFFECT root, without runtime effect simulation |
| Templates | Prototype roots, when present; kept out of the default scene |
| Collision | Placed collision polygon edges, when HIT is present |
| Stage + collision | Geometry and collision edges together |

Some importers combine glTF scenes or import only the default scene. Select the desired scene in a viewer that supports multiple scenes. Collision is wireframe line geometry, preserving n-gon boundaries without guessed triangulation. There is no collision solver. Base meshes not referenced by the authored scene are reported and are not automatically placed at the origin.

Inspect full records or export resource-local collision:

```sh
python arika_stages.py stg-json extracted/stg/s01/s01a.stg scene.json
python arika_stages.py hit-json extracted/stg/s01/s01a.hit collision.json
python arika_stages.py hit-obj extracted/stg/s01/s01a.hit collision.obj
```

`hit-obj` retains polygon winding and n-gons, one named object per HIT object range. Its coordinates are resource-local; no STG placement is applied. Overlapping/grouped HIT object ranges can produce repeated polygons intentionally. Use `scene-gltf` for placed collision diagnostics. Existing `arika_models.py model-gltf` remains available for raw stage model inspection.

Stage `.ase` files are audio banks, handled by the existing audio tools. They are not assumed to be stage behavior scripts. Folders s08/s09 contain model/texture assets without matching STG/HIT files in this archive; this tool does not invent a scene for them. The example inventory records all indexed files in numbered stage folders. Archive folder IDs are retained without guessed stage display names.

## STG structure: inferred authored layout

The header contains version `0x00000100`, `STG ` at +4, a name count at +8, and a template-root count at +12. Fixed 16-byte CP932 names follow at +16. Variable node records follow the names.

| Node field | Offset / size |
| --- | --- |
| Kind, inline-reference count, links, flags | Four bytes at +0 |
| Name index | u32 at +4 |
| Kinds 1/2/3 translation, rotation, scale | Nine floats at +8; base record size 44 |
| Kind 3 inline name-index / raw flags pairs | Eight bytes each after the base record |
| Kinds 4/6 | Fixed 60 bytes; payload remains opaque |
| Kind 5 | Fixed 96 bytes; payload remains opaque |

The authored forest parses with link bit 0 meaning child and bit 1 meaning sibling. There are `template_count + 2` roots: the prototype roots, then EFFECT and STAGE. All source extents, names, link obligations and root names are validated. Kinds 2 bind model meshes by exact name; kind 3 references HIT objects by exact name. These mappings resolve throughout the supplied stage corpus.

TRS values are interpreted as local translation, Euler radians and scale, using the existing XYZ quaternion composition equivalent to `T * Rz * Ry * Rx * S`. Radian values and the child/sibling interpretation are inferred from authored data, including repeated pi rotations and coherent simple-stage placement. The native STG reader/transform construction has not yet been independently instruction-validated. Raw flags and opaque payload words are preserved rather than assigned invented behavior names. Preview visibility includes authored mesh records under the selected root; alternate runtime states can still overlap.

## HIT structure: native resource binding confirmed

The version is `0x00020000`, followed by `HIT `. The 32-byte header stores object count at +8 and object/polygon/vertex offsets at +12/+16/+20. Names are fixed 16-byte entries after the header. Objects are 64 bytes, polygon descriptors 32 bytes, and vertices float4 (16 bytes).

An object contains raw flags, polygon count, first polygon, a radius, and three float4 vectors. Polygon descriptors contain vertex count, first vertex, two unknown words and a float4 normal. The parser verifies polygon and vertex ranges, complete vertex coverage, and all finite float fields. Object ranges may overlap. It retains all vectors/flags without treating their unknown fields as editable gameplay properties.

Native `0x1ABAB0` binds header offsets to the resource's names/objects/polygons/vertices. `0x1AB840` searches 16-byte object names, indexes 64-byte object records, and selects the stored polygon count and 32-byte polygon range. This confirms the resource layout and name lookup. It does not validate a full collision solver or all STG placement semantics.

## Validation

All 13 STG/HIT pairs parse, covering 8,059 scene nodes, 3,746 mesh references, 4,799 collision references, 2,886 named HIT objects, 20,206 polygons and 66,301 vertices. Every scene mesh/collision name resolves to the matching sibling resource. All 13 base stage models are rigid and have no skeleton hierarchy. Unresolved names, invalid record kinds, truncated records, malformed ranges and unfulfilled hierarchy links are errors.

The supplied snapshot contains all 89,200 bytes of `s06a.hit` unchanged at EE `0x01784C00`. Its STG name table and 1,279 original node tags match at `0x0179AC00`, masking the extra runtime link-byte flags. Opaque STG payloads are modified at runtime, so whole-file byte equivalence and behavioral equivalence are not asserted.

All 139 package tests pass, including nine stage tests. Two exported examples pass the package's accessor, primitive-index, scene/node graph, finite-transform and binding checks. The Khronos validator was not run on these new assembled exports. `previews/stage_layouts.png` shows an inspected top-down geometry/collision diagnostic for s00 and s01; it is not a textured gameplay comparison.

Included examples: `stage_s00_scene.gltf`, `stage_s01_scene.gltf`, and `stage_inventory.json`. Counts and runtime evidence are in `stage_validation.json`.

```sh
python -m unittest discover -s .
python validate_stages.py extracted stage_validation.json --snapshot stage_stall.bin --gltf examples/stage_s00_scene.gltf --gltf examples/stage_s01_scene.gltf
```

Next research targets are native STG transform/flag validation, opaque control records and template instantiation, destruction/visibility transitions, and any external stage-runtime scripts or tables.
