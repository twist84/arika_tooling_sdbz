# First menu-component group: sprites and effects

This is a static setup extraction for the SHA-256-guarded `SLES_541.61`. The version 5 main-menu report includes `first_components`; the standalone command writes just that section:

```sh
python arika_menu_first.py SLES_541.61 first_components.json
python -m unittest discover -p 'test_arika_menu*.py'
```

All seven first-group components are now represented. This pass recovers nine literal sprite rectangles, twelve decoration records, four scrolling-strip descriptors and four particle templates used by a six-slot system. These are setup records, not a recovered frame or an integrated effects player. The existing geometry SVG remains at 45 quads from the other two component groups.

Twenty-one menu tests pass. New checks cover the decoration scale format, explicitly partial setup scans, float arguments in call delay slots, and known report counts/runtime gaps. The report was regenerated from the supplied ELF. This is not a native runtime/rendering comparison.

## Component map

| Item | Vtable | Setup | Draw | Resource | Literal rectangles | Decorations | Strip |
|---:|---|---|---|---:|---:|---:|---|
| 0 | `0x004F17B0` | `0x00374530` | `0x00374430` | 9 | 1 | 0 | Yes |
| 1 | `0x004F1800` | `0x00374800` | `0x00374760` | 9 | 1 | 0 | No |
| 2 | `0x004F1D30` | `0x0037A700` | `0x0037A600` | 11 | 1 | 0 | Yes |
| 3 | `0x004F1D80` | `0x0037AA90` | `0x0037A910` | 11 | 2 | 6 | No; particle system |
| 4 | `0x004F1840` | `0x00374B60` | `0x00374980` | 10 | 2 | 2 | Yes |
| 5 | `0x004F1E10` | `0x0037B740` | `0x0037B620` | 10 | 1 | 4 | No |
| 6 | `0x004F1EF0` | `0x0037BDE0` | `0x0037BCE0` | 12 | 1 | 0 | Yes |

The literal rectangles are extracted from scalar setup arguments, including call delay slots. For items 3, 4 and 5, constant propagation stops before the decoration loop's conditional branch. The corresponding fixed tables are decoded separately. Item 4's strip initializer is extracted from the straight-line suffix after its loop. This does not imply the extractor executed the loop or recovered arbitrary branch behavior.

## Decoration records are scaled sprites

The first group's 24-byte decoration records differ from the middle group's records:

| Offset | Type | First-group meaning |
|---:|---|---|
| +0 | s16[4] | UV X/Y/width/height |
| +8 | f32[2] | X/Y placement |
| +16 | f32[2] | X/Y scale |

Tables are `0x004A9FD0` (six records, item 3), `0x004A9E30` (two, item 4), and `0x004AA0D0` (four, item 5). Native setup writes the last two fields into sprite +32/+36, establishing the scale interpretation. Item 4's first decoration has X scale **21.5**, demonstrating why treating these fields as depth/anchor data would produce incorrect geometry.

The report includes each decoration's component-relative offset and texture entry. These are plain sprites with a different native draw path from the component sprites already diagrammed; this pass does not generate guessed quads for them.

## Scrolling-strip helper

`0x00373FF0` stores a four-s16 UV descriptor, an orientation byte, start/end coordinates, a period and a zero phase counter. Orientation 1 selects anchor mode 3 and a rotation of approximately pi/2; orientation 0 selects anchor mode 1 and zero rotation. Float parameters below come from the setup instructions' FPR arguments.

| Item | UV X,Y,W,H | Orientation | Start | End | Period |
|---:|---|---:|---:|---:|---:|
| 0 | 442, 0, 70, 450 | 1 | 0 | 400 | 3150 |
| 2 | 412, 0, 100, 280 | 1 | 132 | 395 | 2520 |
| 4 | 442, 31, 70, 330 | 1 | 0 | 320 | 2970 |
| 6 | 0, 0, 350, 94 | 0 | 214 | 512 | 2450 |

The update helper `0x003740D0` adds 1 to the float phase counter, then subtracts the period once if the new counter is at least the period. The draw helper `0x00374110` clips two consecutive strip pieces against the start/end range and adjusts the source rectangle. This update records the inputs and function addresses; it does not port that clipping/draw loop or establish a wall-clock tick rate.

## Particle system

Item 3 allocates six 176-byte slots through `0x0037AC10`. Initialization `0x0037ADB0` initializes all six, activates the first five, and applies five seed X/Y positions from `0x004AA0A0`. The template selector uses a random value shifted right by 5 and masked with 3, selecting four records at `0x004AA060` with a 16-byte stride. Each record contains a four-s16 UV rectangle followed by float speed-base and random-span values.

| Template | UV X,Y,W,H | Speed base | Random span |
|---:|---|---:|---:|
| 0 | 0, 320, 256, 112 | 0.1 | 0.2 |
| 1 | 256, 320, 160, 87 | 0.1 | 0.2 |
| 2 | 0, 432, 136, 72 | 0.1 | 0.2 |
| 3 | 136, 432, 112, 56 | 0.2 | 0.2 |

These decimal values summarize the float32 values preserved in JSON. Sprite initialization is `0x0037B0A0`; particle update `0x0037B210` decreases X by its speed, clips its UV range against a runtime boundary, and clears exhausted slots. Drawing `0x0037AEE0` visits the six slots through `0x0037B370`, which draws active ones. RNG state/call ordering and respawning are not simulated.

## Runtime gaps

Startup recovery now establishes item 0's initial base as (0, 0), item 3's extra Y offsets as 0 and 204, and its particle clip boundary as 239. Its first sprite has fixed Y scale 204. See `MENU_STARTUP.md`; later writes and the allocated particle-array pointer at `0x004FDC64` still depend on runtime state.

The diagrams now contain 66 item and ten shared startup-baseline quads. Strip clipping and rotated geometry are ported; native owner animation, textures and compositing remain pending.
