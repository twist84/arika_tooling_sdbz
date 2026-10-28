# Super Dragon Ball Z: main-menu research

Build: supplied European beta `SLES_541.61`. ELF SHA-256: `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`. This is a first static-analysis pass, not a runtime-verified complete menu reconstruction.

## Confirmed findings

The binary identifies the application as `CAppMenuMain` and its menu controller as `CMenuMainMenu`. The `dis/main_menu` resource wrapper exposes 13 resource entries; the menu itself constructs seven selectable items. These counts describe different objects.

The resource-name string is at `0x004CC8A8`. Its getter is `0x00374F00`, referenced through resource vtable `0x004F1880`. `0x00374DF0` lazily allocates the 12-byte wrapper; `0x003FDE00` creates it during menu entry. The generic polling routine `0x00372530` starts the asynchronous load and marks completion using object byte +8 bit 0.

The constructor `0x003FDD60` installs primary app vtable `0x004F6920` and lifecycle/phase table `0x004F6948`. A menu transition controller begins at app +52 and the embedded `CMenuMainMenu` at app +80.

## Function map

Names below are descriptive research labels; the two class-name strings are original binary strings. Method roles come from call/vtable analysis and remain subject to runtime confirmation.

| Role | Address |
|---|---|
| resource create | `0x00374DF0` |
| resource name | `0x00374F00` |
| resource count | `0x00374F10` |
| resource poll | `0x00372530` |
| resource entry | `0x003725E0` |
| resource release | `0x00372660` |
| app constructor | `0x003FDD60` |
| app enter | `0x003FDE00` |
| app load | `0x003FDEB0` |
| app begin exit | `0x003FDFE0` |
| app route after exit | `0x003FE020` |
| app unload | `0x003FE240` |
| app draw | `0x003FE300` |
| app type name | `0x003FE330` |
| menu create items | `0x00378860` |
| menu cleanup | `0x003798C0` |
| menu update | `0x00379A40` |
| menu input | `0x00379C80` |
| menu draw | `0x00379E60` |
| menu select | `0x00379F00` |
| menu type name | `0x0037A1E0` |

## Seven-entry routing

After its exit transition completes, `0x003FE020` reads app +272 (the embedded menu's current index), writes the mode selector through `0x0032A5F0` (manager field +12), and requests the next app through `0x003DFB00`. The exact visible labels and semantic mode names have not yet been assigned.

| Item index | Text lookup ID | Mode selector | Next app ID |
|---:|---:|---:|---:|
| 0 | 284 | 1 | 10 |
| 1 | 285 | 2 | 10 |
| 2 | 287 | 3 | 10 |
| 3 | 288 | 5 | 44 |
| 4 | 286 | 4 | 10 |
| 5 | 289 | 6 | 45 |
| 6 | 290 | 7 | 46 |

Cancellation is a separate path: app byte +293 sends control to app ID 3 and does not write the mode selector. The routine also invokes reset/transition helpers not implemented in the portable reconstruction.

## Navigation

`0x00379C80` polls input; `0x00375270` dispatches a logical direction to per-item vtable slots +0x34/+0x38/+0x3C/+0x40. The input helper masks for directions 0/1/2/3 are 8/4/1/2. These masks are an internal input representation; their physical controller labels are not established here.

| Item | Direction 0 | Direction 1 | Direction 2 | Direction 3 |
|---:|---|---|---|---|
| 0 | 3 | -1 | -1 | 1 if byte +0x710 clear; 2 if set |
| 1 | 2 | -1 | 0 | 4 |
| 2 | 6 if byte +0x830 clear; 5 if set | 4 if byte +0x830 clear; 1 if set | 0 | -1 |
| 3 | -1 | 0 | -1 | 5 |
| 4 | 2 | -1 | 1 | -1 |
| 5 | -1 | 2 | 3 | 6 |
| 6 | -1 | 2 | 5 | -1 |

`-1` means no neighbor. The dynamic offsets belong to their individual menu-item objects, not the whole menu. Their writes are now traced: these are selection-history flags, not unlock flags. Item 0's byte +0x710 is set by `0x003758F0` when the previous index is 2. Item 2's byte +0x830 is set by `0x0037A300` when the previous index is 0, 1, or 5. Both clear otherwise. `0x003751F0` stores the previous index at item +8 before invoking these selection-entry methods. This explains why the same selected item can have different directional neighbors depending on the entry path.

`0x00379F00` changes the current item at menu +192, preserves the prior index at +196, starts selection animations, resolves the item text using the table at `0x004A9FA0`, and resets menu +208. The draw path `0x00379E60` visits background/shared UI, previous and current items, and another embedded component. `0x00375100` dispatches item drawing through +0x44 and conditionally +0x48 according to item state. Final sprite rectangles/UVs and draw ordering are not decoded yet.

## State fields

| Owner | Offset | Observed use |
|---|---:|---|
| App | +0x28 | Exit/routing phase |
| App | +0x2C | Load phase |
| App | +0x30 | Unload phase |
| App | +0x110 | Selected item, alias of menu +0xC0 |
| App | +0x125 | Cancellation path flag |
| Menu | +0x24 | Start of seven item pointers |
| Menu | +0xC0 | Current index |
| Menu | +0xC4 | Previous index |
| Menu | +0xC8 | Animation/transition phase |
| Menu | +0xCC | Phase timer |
| Menu | +0xD0 | Idle timer |
| Menu | +0xD4 | Flags; bit 0 gates selection behavior, bit 1 gates idle action |

## Decompiler correction

The supplied Hex-Rays output for `0x00378860` incorrectly presents an infinite allocation loop and loses most switch cases. The machine code uses a jump table at `0x004CC8E0`, seven constructor branches, and `slti v1,s2,7` at `0x00378958`. The routes are independently extracted from jump table `0x004D85D0`. Stock MIPS disassemblers can also misidentify R5900 `lq/sq` as unrelated DSP/MSA instructions; the extractor reads only the verified scalar instruction patterns and data words.

## Tools and validation

Run from the tools folder:

```sh
python arika_menus.py SLES_541.61 main_menu_map.json
python -m unittest test_arika_menus
```

`arika_menus.py` refuses an ELF with a different SHA-256. It extracts navigation getters (including conditional `movz` returns), constructor/route tables, text IDs and addresses. Version 2 also resolves the seven help-text blocks, records selection-history flag rules, and exports arrow/composite sprite tables. It does not patch the ELF. The included JSON was generated from the supplied ELF.

`arika_menu_logic.h` is a portable C++03 behavioral reconstruction of adjacency and routing only, in Allman style. `get_neighbor(direction)` and `move(direction)` now use the stored previous index to derive the selection-history flags. Explicit-flag overloads remain available for comparison. It intentionally does not claim to implement real input gating, fades, loading, menu drawing or audio. Eight menu tests pass. The C++03 test compares every entry/direction under all four combinations of the two dynamic flags against the extracted ELF table, then checks 196 previous/current/direction combinations and initial/failed movement behavior. These comparisons validate the recovered table logic, not an instrumented in-game run.

## Asset references

Existing archive tooling already handles `dis/main_menu.pix` (index 235, 3,228,404 bytes) and menu music `sqm/menu_in.ams` / `sqm/menu_lp.ams`. There is also an earlier backup-named atlas entry `dis/.#main_menu.pix.1.9` of the same size; identical size alone does not establish identical content.

## Help descriptions and text lookup

The seven IDs are **help descriptions**, not the labels drawn in the atlas. The ELF's `.reginfo` section gives GP `0x004FF370`. The straight-line initializer `0x003A2780` writes 337 pointers into the table at `0x0060C6C0`; the extractor evaluates its LUI, ADDIU and SW instructions, including the return delay slot. For the seven menu entries, each pointer leads to a u32 line count followed by that many pointers to English strings. Other text-table entries are not claimed to share this format.

| Item | Text ID | Help block | Lines | Role indicated by the description |
|---:|---:|---|---:|---|
| 0 | 284 | `0x004FC180` | 4 | Arcade-style battles leading to Cell; Dragon Ball collection |
| 1 | 285 | `0x004FC194` | 4 | Z Survivor; requires a character card |
| 2 | 287 | `0x004FC1BC` | 3 | Matches between friends, with handicap settings |
| 3 | 288 | `0x004FC1CC` | 4 | Summon Shenron with seven Dragon Balls |
| 4 | 286 | `0x004FC1A8` | 4 | Practice moves and configure an opponent/environment |
| 5 | 289 | `0x004FC1E0` | 4 | Create/delete character cards and learn skills |
| 6 | 290 | `0x004FC1F4` | 3 | Settings and save/load |

All 26 original lines and their addresses are in `main_menu_map.json`, including the original spelling `availbale`. The descriptions support these roles; they do not prove the exact texture-rendered labels.

## Sprite data: verified subset

The arrow sprite setup at `0x00375310` selects resource entry 0. `0x003753A0` reads four signed 16-bit UV endpoints per direction from `0x004A9E60` and animates the supplied position. The endpoint setter `0x002FD9E0` and normalizer `0x002FCE20` establish that the fields are `(u0, v0, u1, v1)`, allowing reversed axes.

| Logical direction | u0 | v0 | u1 | v1 |
|---:|---:|---:|---:|---:|
| 0 | 37 | 19 | 0 | 50 |
| 1 | 0 | 19 | 37 | 50 |
| 2 | 81 | 63 | 113 | 100 |
| 3 | 81 | 100 | 113 | 63 |

Item 0's composite setup `0x00380210` selects resource entry 5 and reads seven 24-byte records at `0x004AA450`. Each contains four s16 UV fields, three float placement/depth offsets, and u32 draw flags. Records 0–4 go through the rectangle/size setter; records 5–6 go directly through the endpoint setter. The extractor preserves that distinction, all offsets, and the raw draw flags. This is one composite, not a complete static menu layout. Animation offsets, final positioning and draw-flag semantics still need tracing; no layout preview is claimed yet.

## Composite geometry update

All seven middle composite groups are now extracted: 38 records with resource-entry assignments, UV interpretation, anchor modes, base positions and per-part offset locations. `0x002FD4A0` confirms that the provisional draw-flag field selects one of nine vertex-anchor layouts. `arika_menu_layout.py` exports JSON and separate geometry diagrams; see `MENU_LAYOUT.md`. These diagrams use zero explicit animation offsets and do not reconstruct a complete menu screen.

## Next concrete work

Common label/character emphasis is now in `NATIVE_ITEM_EMPHASIS.md` and connected to the viewer. Actual activation/input/selection timing and interruption rules remain next.

DRAGON SUMMONING combined idle is now in `NATIVE_DRAGON_IDLE.md`, completing idle motion patterns for all seven items (host trig for items 3/6). Emphasis/shake and actual selection timing remain next.

OPTIONS circular idle is now in `NATIVE_OPTIONS_IDLE.md`, with explicit host-trig limits. DRAGON SUMMONING idle, native trig fidelity, emphasis and actual selection timing remain next.

VERSUS per-part idle is now recovered in `NATIVE_VERSUS_IDLE.md`. OPTIONS and DRAGON SUMMONING's trigonometric idle paths, emphasis and actual selection timing remain next.

CUSTOMIZE coupled idle is now recovered in `NATIVE_CUSTOMIZE_IDLE.md`. VERSUS, DRAGON SUMMONING and OPTIONS idle callbacks, emphasis and native selection timing remain next.

Per-part idle for items 0, 1 and 4 is now in `NATIVE_CHARACTER_IDLE.md`; remaining concrete idle callbacks, emphasis and actual selection timing are next.

Common whole-character entry/exit is now implemented in `NATIVE_ITEM_CHARACTERS.md` and connected to the textured viewer. Individual part idle/emphasis and actual activation timing remain pending.

Selected-item label entry/exit motion is now in `NATIVE_ITEM_LABELS.md` and connected to the textured viewer. Remaining selected-item work includes emphasis/shake, character-part and scenery animation, then native selection scheduling.

Shared small-component entry/bounce motion and concrete lifecycle callbacks are now implemented in `NATIVE_MENU_SMALL.md`; the integrated example enables them with `--small`. Item-specific animation and full rendering remain pending.

Shared banner entry/exit curves are now implemented in `NATIVE_MENU_BANNER.md`; the integrated example enables them with `--banner`. Small-component animation curves remain next.

Shared scheduling, staggered starts and overlay fade are now in `NATIVE_SHARED_SCHEDULER.md`; child animation curves and outer activation timing remain pending.

The inner tile/companion owner is now recovered in `NATIVE_MENU_OWNER.md`, including update gating and entry/active/exit order. Its explicit-start trace does not establish outer-menu scheduling or visibility.

1. Identify the exact texture-rendered labels, using the newly resolved descriptions as context.
2. Capture subsequent runtime writes/context RNG state and connect textured rendering. Initial positions and corrected companion heights are now in `MENU_STARTUP.md`; RNG is in `NATIVE_MENU_RNG.md`, companions in `NATIVE_MENU_COMPANIONS.md`, tile scrolling in `NATIVE_MENU_TILES.md`, rotated strips in `ROTATED_MENU_STRIPS.md`, strip clipping in `NATIVE_MENU_STRIPS.md`, plain sprites in `MENU_PLAIN_SPRITES.md`, first-group setup in `MENU_FIRST_COMPONENTS.md`, and shared draw structure in `MENU_LAYERS.md`.
3. Recover animation curves, visibility gates, and native compositing order.
4. Validate the seven routes in an instrumented native run, including cancel and disabled/alternate entries.
5. Build a menu layout preview/editor only after the texture selection and rectangle representation are verified.
