# EU-beta native main-menu help-panel and FFON draw owner

Scope: `SLES_541.61` (EU beta), SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
Addresses are EE virtual addresses. Only pointers, instruction summaries and
numeric configuration are documented; the executable and game assets are not
checked in.

## Owner and selection-to-text chain (instruction-verified)

The main menu's `0x00379E60` draw callback **does** dispatch the embedded
help owner at `this+0x40` through its vtable `+0x4C` at
`0x00379EAC–0x00379EB4`. The native constructor `0x003FDD60`
creates the parent menu at outer-object `+0x50` and its embedded help
component at outer-object `+0x90` (`this+0x40`), installing:

- Main-menu vtable `0x004F1C50` at `0x003FDDB0–0x003FDDBC`.
- Derived help vtable `0x004F1F30` at `0x003FDDC0–0x003FDDD0`.
- A separate sprite object at help-component `+0x10`.

**Correction to previous research:** `0x0037A200` is the *deleting
destructor*, not the live constructor. Its vtable rewrites and conditional
`0x00111020` deallocation occur during destruction. Using its base
`0x004F0EF0` vtable to resolve active help callbacks would incorrectly
identify null draw slots. The active derived vtable is `0x004F1F30`.

Selection change `0x00379F00` loads an ID from the seven-word table
`0x004A9FA0` (`0x00379F5C–0x00379F70`), calls
`0x003A3750` (text-record lookup), and passes the resulting record
pointer to help vtable `+0x50` (`0x00379F74–0x00379F84`).
The derived `+0x50` target is `0x0037C010`, which writes the
record pointer to help-component `+0x70` in its `JR RA` delay slot.

| Selection | Item | ID | Record EE VA | Lines |
| ---: | --- | --- | --- | ---: |
| 0 | ORIGINAL | `0x11C` | `0x4FC180` | 4 |
| 1 | Z SURVIVOR | `0x11D` | `0x4FC194` | 4 |
| 2 | VERSUS | `0x11F` | `0x4FC1BC` | 3 |
| 3 | DRAGON SUMMONING | `0x120` | `0x4FC1CC` | 4 |
| 4 | TRAINING | `0x11E` | `0x4FC1A8` | 4 |
| 5 | CUSTOMIZE | `0x121` | `0x4FC1E0` | 4 |
| 6 | OPTIONS | `0x122` | `0x4FC1F4` | 3 |

At `0x003A3750`, the indexed global table base is `0x60C6C0`;
the native initializer `0x003A2780` installs text-record pointers
for IDs 284–290 at `0x003A34CC–0x003A3524`. The records contain
a u32 line count followed by u32 string pointers. The actual draw
routine reads the low signed byte of the count (`LB` at `0x37C1F0`)
before looping. The separate record at `0x4FC204` has seven entries
and is **not** one of the seven help descriptions.

## Draw path and numeric layout (instruction-verified)

Help vtable `+0x4C = 0x0037BF60`:
1. Queries its state using vtable `+0x1C`; skips when false
   (`0x37BF70–0x37BF84`).
2. Reads the component's X/Y via vtable `+0x28/+0x2C`, stores these
   into the embedded sprite's X/Y (`0x37BF88–0x37BFB0`).
3. Draws the embedded sprite through its vtable `+0x10`
   (`0x37BFB4–0x37BFC0`).
4. If the component's vtable `+0x20` allows it, calls
   `0x0037C1C0` to draw the text (`0x37BFC4–0x37BFEC`).

`0x0037BEB0` initializes the panel sprite with the texture-resource
selector **4**, native sprite bounds `(0,0)–(464,176)`, and depth
**97.0f** (`LUI 0x42C2` at `0x37BF14`). This establishes the
sprite's submitted geometry, **not** a measured alpha-visible texture
rectangle or final GS pixel footprint.

`0x0037C1C0` (record rendering) is a per-line loop:
- `0x37C1E0–0x37C214`: require non-null help record, get signed
  low-byte line count, and initialize logical coordinates.
- X = component X **+64.0f**, GP float at `0x4FA79C`;
  Y = component Y **+52.0f**, GP float at `0x4FA7A0`.
- `0x37C220–0x37C244`: call native FFON text renderer
  `0x002CDCA0` for each pointer from record `+4+index*4`.
  Font context comes from `gp-0xE90`; scalar `f14` is **0.75f**
  from GP float at `0x4FA798`. Zeroes are passed in `a1/a2`.
- `0x37C248–0x37C264`: increment line index and Y by
  **25.0f** from GP float `0x4FA7A4`, including the last loop
  branch-delay increment. Coordinates advance in float32 arithmetic,
  rather than deriving all lines from a wall-clock timer.

These constants corroborate the editor's *25-unit* line separation,
but **do not prove** its absolute `(87,324)` text origin or
`(30,272,450,175)` screenshot-calibrated panel rectangle. To recover
absolute positions, trace the writes / vtable position setters for
help-component `+0x08/+0x0C` (menu-relative `+0x48/+0x4C`).
Do not infer that position from a 4:3 screenshot using a uniform
512-based scale; see `NATIVE_MENU_PHASE6_OFFLINE.md`.

## Implementation boundary

`arika_menu_help_native.py` is a pure, float32-aware geometry/record
description for these proven relative offsets and counts. It does
**not** replace the Qt help renderer's screenshot-calibrated absolute
position. The existing diagnostic timeline, actual FFON/PIX asset
loading and 4:3 presentation remain unchanged.

The precise FFON glyph placement/advance *inside* `0x2CDCA0`,
active GS blending/depth, absolute component origin, and the actual
PCM/GS capture are still outstanding. No guessed native animation
timings or copyrighted assets are introduced.
