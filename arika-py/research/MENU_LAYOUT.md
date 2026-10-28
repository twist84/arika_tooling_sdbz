# Main-menu composite geometry

Supported build: the same SHA-256-guarded `SLES_541.61` used by `arika_menus.py`. This extends the static menu research; it does not implement an animated menu renderer.

## Run

```sh
python arika_menu_layout.py SLES_541.61 menu_layout.svg --json menu_layout.json
python -m unittest discover -p 'test_arika_menu*.py'
```

The SVG contains seven **separate** auto-fitted diagrams. Each rectangle is a native sprite quad at zero explicit animation offsets, labeled with its part number and resource texture entry. The diagrams do not assume a native viewport size and do not assemble the seven composites into one screen. `previews/menu_composite_layout.svg` is the supplied build's example.

The JSON stores native coordinates, UV orientation, depth values, anchor modes and evidence addresses. `arika_menus.py` also embeds this data in `composite_layout` in its version 3 report. Twelve menu tests pass, including the existing navigation/text tests and four geometry/diagram tests. The source ELF was used to regenerate the report and diagram. These are host-side checks, not an in-game rendering comparison.

## Recovered composites

The native item constructor assigns a three-part component group to each item. This pass covers the middle composite component: 38 sprite records across all seven items. Other components, shared UI and backgrounds remain outside this extraction.

| Item | Composite vtable | Setup | Draw | Sprite table | Parts | Resource entries | Base X,Y |
|---:|---|---|---|---|---:|---|---|
| 0 | `0x004F2250` | `0x00380210` | `0x00380100` | `0x004AA450` | 7 | 5 | 288, 144 |
| 1 | `0x004F22D0` | `0x00380BD0` | `0x00380AC0` | `0x004AA620` | 4 | 5 | 72, 250 |
| 2 | `0x004F2350` | `0x00381530` | `0x00381380` | `0x004AA740` | 9 | 6 | 256, 224 |
| 3 | `0x004F2290` | `0x003807A0` | `0x00380690` | `0x004AA520` | 8 | 6 and 7 | 512, 0 |
| 4 | `0x004F2310` | `0x00380FD0` | `0x00380EC0` | `0x004AA6A0` | 5 | 5 and 6 | 312, 304 |
| 5 | `0x004F21D0` | `0x0037FAB0` | `0x0037F9A0` | `0x004AA370` | 3 | 7 | 516, 148 |
| 6 | `0x004F2210` | `0x0037FE40` | `0x0037FD30` | `0x004AA420` | 2 | 8 | 204, 204 |

Item 3 parts 1, 2 and 6 use entry 7; its remaining parts use 6. Item 4 part 1 uses entry 6; its remaining parts use 5. These assignments come from the setup switches. Resource entries are indices within the loaded `dis/main_menu` resource, not indices in GAME.DAT.

Each record is 24 bytes: four signed 16-bit UV fields, three float32 placement/depth offsets, and one u32 anchor mode. Item 0 records 5 and 6 contain direct UV endpoints; all other records contain X/Y/width/height. The endpoint distinction preserves the reversed U direction in item 0 record 6. The size setter adds width/height to the UV origin before dispatching to the endpoint setter.

The old report field `draw_flags` was a provisional name for the anchor mode. Its consumer is `0x002FD4A0`, which selects a four-vertex unit rectangle through pointer table `0x0049A8E0`, then scales it by the absolute UV extent. The mode changes the geometry's origin; it does not change the UV direction.

| Mode | Horizontal anchor | Vertical anchor |
|---:|---|---|
| 0 | Center | Center |
| 1 | Left | Top |
| 2 | Center | Top |
| 3 | Right | Top |
| 4 | Left | Center |
| 5 | Right | Center |
| 6 | Left | Bottom |
| 7 | Center | Bottom |
| 8 | Right | Bottom |

The extractor reads all nine four-vertex layouts directly from the ELF instead of deriving them from the table above.

## Animation inputs and placement

For items other than 2, the draw routine adds the component's X/Y animation offset to its base position, then adds the table placement and per-part animation offset. Item 2 subtracts the component offset, then adds the table and per-part offsets. Depth is component depth + 15 + record depth. `pose_part()` accepts these offsets explicitly and rounds its scalar operations to float32. It supports unrotated, unit-scale sprite geometry only.

Each composite has a separate per-part X/Y animation array. Its component-relative starting offsets are 1040, 608, 1328, 1184, 752, 464 and 320 for items 0 through 6. Each pair occupies eight bytes. The zero-offset diagram does not claim that every part is visible at that pose or that every gameplay state settles there.

The old decompilation marks item 2's draw routine as an infinite loop. The ELF has a nine-iteration bound: `slti v1,s3,9` at `0x003814EC`, followed by the backward conditional branch at `0x003814F4`. The extractor uses nine records.

## Shared-layer update

The diagnostic SVG now includes the seven third-group item overlay sprites: 45 quads in total, retaining the original 38-part count separately. Version 4 of the main report also records shared setup rectangles, seven small components and draw-call structure. Seventeen menu tests pass. See `MENU_LAYERS.md` for addresses, the unresolved runtime position, and the distinction between shared plain sprites and component sprites. The earlier twelve-test count above describes the preceding geometry pass.

## Remaining work

First-group setup data is in `MENU_FIRST_COMPONENTS.md`; resolvable plain-sprite geometry is now ported in `MENU_PLAIN_SPRITES.md`. The latest SVG has 63 item quads plus nine shared-layer quads. Finish strip/tiled-element playback, then trace runtime positions, animation curves, visibility gates, depth ordering, clipping, and texture sampling. A textured, animated reconstruction needs those pieces and a comparison with a native capture. The SVG is a geometry diagnostic only.
