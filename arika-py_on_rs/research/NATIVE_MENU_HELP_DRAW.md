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

The **settled native component position is now independently verified**.
The help vtable `+0x40 = 0x0037C160` state setter writes state 2's
coordinates at `0x37C19C–0x37C1A8`:
X = **24.0f** (`gp-0x4C00 = 0x4FA770`) and
Y = **272.0f** (`gp-0x4BFC = 0x4FA774`).
Accordingly the settled frame sprite occupies logical **(24,272)–(488,448)**,
and the first four text origins are **(88,324)**, **(88,349)**,
**(88,374)** and **(88,399)**, as computed by the native FFON loop.
The existing screenshot-calibrated `x=30` was close to the *visible
opaque artwork*, not the sprite's source coordinate: atlas entry 4's
alpha begins at source X≈6, so a source-correct sprite at X24 yields
visible content around X30. **Do not** use the cropped alpha bounds to
translate the native frame rectangle, and do not infer the display
mapping from atlas dimensions.

**Entry and exit curves are now recovered**; see the state-machine
section below. GS compositing and the complete FFON glyph metrics
remain outside this milestone.

## Implementation boundary

`arika_menu_help_native.py` is a pure, float32-aware geometry/record
description for these proven offsets, counts and **settled** origin.
The editor can select the native settled layout without modifying the
existing diagnostic timeline and its screenshot-calibrated comparison.
The actual FFON/PIX asset loading and 4:3 presentation remain unchanged.

The precise FFON glyph placement/advance *inside* `0x2CDCA0`,
active GS blending/depth, absolute component origin, and the actual
PCM/GS capture are still outstanding. No guessed native animation
timings or copyrighted assets are introduced.

## State machine: entry, visibility, exit (new native-word trace)

The common component dispatcher `0x0035F820` uses help-component `+0x04`
as phase: **0 hidden**, **1 entry**, **2 settled**, **3 exit**.
Its class vtable at `0x4F1F30` has:

| Slot | Target | Verified role |
| --- | --- | --- |
| `+0x08` | `0x35F7C0` | set phase 1 through `+0x40` |
| `+0x10` | `0x35F800` | set phase 3 through `+0x40` |
| `+0x14` | `0x35F820` | update phase and transition on callback return |
| `+0x1C` | `0x3369F0` | draw panel iff phase != 0 |
| `+0x20` | `0x336980` | draw FFON text iff phase == 2 |
| `+0x34` | `0x37C020` | entry age, curve, completion |
| `+0x38` | `0x35F900` | settled no-op |
| `+0x3C` | `0x37C0F0` | exit age, curve, completion |
| `+0x40` | `0x37C160` | phase setter, clear age and initialize pose |

Each phase setter resets `+0x74` float age. On entry start
(`0x37C194/0x37C198`) it writes Y=**-448** and retains the prior X.
On state 2, it explicitly writes **(24,272)**.
Each entry/exit update adds **1.0f** to component age, independent
of the global preview sample clock.

Entry callback `0x37C020` calls `0x2C2C10` with exactly two
fixed interpolation keys:

- Times at `0x4FA778`: **(10,15)**.
- Values at `0x4FA780`: **(224,0)**, added to settled Y=272.
- Once `age >= 15` it adds a second 13-key curve with times
  `0x4AA130 = (0,1,...,12)` and values at `0x4AA170`:
  `(0,3,6,3,0,2,4,2,0,1,2,1,0)`.
  This curve's input is `age-15`.
- At age **27** (`15+12`, computed by native `ADD.S`
  `0x37C058`), the callback returns 1. `0x35F820` then sets
  phase **2**, resets age and writes (24,272).
  Text becomes visible at that transition.

Exit callback `0x37C0F0` uses times `0x4FA788=(0,5)` and
values `0x4FA790=(0,224)`. It increments Y from 272 to 496;
at age **5** it returns 1, and `0x35F820` sets phase **0**.
The panel is visible through phase 3, but text is **not**:
the draw callback first calls `0x3369F0` (phase!=0)
and gates the text callback with `0x336980` (phase==2).

The generic parent update invokes the embedded component's vtable
`+0x14` at `0x379A88–0x379A94` **after** shared, pending and
current item updates; the parent phase transition and input processing
occur afterward (`0x333920`). The native ready callback
`0x379970` invokes the main-menu selection callback first, then the
embedded help `+0x08` entry at `0x379990–0x37999C`.
On either confirm or cancel, `0x3799B0` converges at
`0x3799E4–0x3799F0` to call help `+0x10` and start exit.
This is not tied to individual selection changes; those only replace
the text record through help `+0x50`.

`arika_menu_help_lifecycle.py` advances these recovered phases,
ages and float32 interpolation curves once per native parent update;
the Qt preview reads the resulting snapshot without mutating it.
`test_arika_menu_help_lifecycle.py` tests the exact state clocks,
all key values (when the user's ELF is supplied), and entry/exit
render-text gating; synthetic offscreen tests also ensure the
diagnostic timeline remains independent.

**Still outstanding:** the actual `0x2CDCA0` FFON glyph-run
rendering metrics, PS2 GS blend and per-pixel depth state,
and live original console/PCSX2 framebuffer capture.

## Font cell metrics and downstream glyph path (next checkpoint)

The actual font object is **not** initialized by the help panel. The
global startup constructor at `0x004E2E60` calls `0x0019A120`
for the resident font object `0x0063BE80`, installing
vtable `0x004E3390`. The resource startup path `0x00326488–0x003264AC`
then installs the loaded `font/5-24-2.fon` data and writes
**24.0f** (instruction `LUI 0x41C0` at `0x32648C`) to
the font object's `+0x04` and `+0x08` size fields.
The source FFON header also describes 24×24 cells.

The menu's `0x0037C240` direct call to `0x002CDCA0`
is a **text API wrapper**, not the low-level bitmap blitter.
It saves the incoming coordinates/font scale, builds a four-channel
color, then dispatches the resident font object's vtable
**`+0x20`** (at `0x2CDF14–0x2CDF54`).
The menu supplies a null color pointer and the wrapper uses its
four-float default at `0x00439FB0 = (1,1,1,1)`.
The font object's verified vtable slots are:

| Vtable offset | ELF callback | Purpose |
| --- | --- | --- |
| +0x10 | `0x19A1B0` | Measure a text run, handle special input characters |
| +0x14 | `0x199DC0` | Space advance: 0.5× font `+4` |
| +0x18 | `0x199DE0` | Line height: font `+8` |
| +0x1C | `0x19A030` | Advance per codepoint |
| +0x20 | `0x199EE0` | Font drawing/command emission path |

At `0x19A030–0x19A05C`, the native code masks the codepoint
to 16 bits and returns **font width ×0.5 for codes below
0x100**, otherwise full font width. This is a branch
(`SLTI 0x100` at `0x19A034`), not a proportional advance
calculated from a glyph's opaque pixel bounds. `0x199DC0`
independently implements the same half-width for the space.
`0x19A1B0` iterates string bytes, accumulates these advances
with native `MUL.S`/`ADD.S`, and treats newline, `$` escape
sequences and multibyte characters specially. The seven original
main-menu descriptions have **only ordinary printable ASCII**
and spaces, no escape sequences or multibyte characters.

Consequently, the native text **origin-to-origin advance** for
every existing help glyph and space is **12.0 units** before
the menu's `0.75f` scale: **9.0 logical units** between glyph
origins at menu scale. No per-glyph bounding-box trim, 3-pixel
tracking constant, or author-defined max-width fit is present in
this recovered font-width path.

`arika_menu_ffon_native.py` now implements these fixed advances
and a *host preview* raster using the decoded FFON bitmaps.
In **native mode only**, the editor uses it instead of the prior
`render_text(..., spacing=3)` proportional/trimmed preview.
The old renderer and 140-sample timeline remain available in
diagnostic mode, with independent caches. Native placement is
validated with synthetic 24×24 cells and an optional exact-ELF
opcode/vtable oracle.

**Boundary of proof:** `0x199EE0` submits text via the engine
command path `0x112780`, with downstream resource and glyph
rendering not yet reconstructed. The Python/Pillow raster still
uses full 4-bpp glyph bitmaps, and exact UV selection, source
clipping, PS2 filtering, coverage and alpha compositing are
**host approximations**; matching a 12-unit *advance* does not
prove pixel-exact native bitmap compositing. Do not infer FFON
glyph UVs, source cropping, multiline escape semantics or GS
blend modes from the width callback alone.

### Original FFON bitmap half-cell cross-check (asset-backed, regional caveat)

A separately supplied `sdbz_eu_beta.7z` archive was inspected **locally**
without committing its assets. Despite its archive filename, its root
contains a **`SLUS_214.42`** executable, so this is *not* proof that its
font bytes exactly match the target EU-beta disc. It contains
`GAME.DAT` with one FFON at byte offset `0x032E8800`.
The 340,192-byte `5-24-2.fon` has SHA-256
`95a3bd0cc002ea619adc12bd916fcddffc98c1e512605704eeadf29251230db9`.

All **95 mapped printable ASCII cells** in that supplied font have no
nonzero nibble in source columns **12..23**; their visible bits lie
entirely within columns **0..11** of each 24×24, 4-bpp glyph record.
The space glyph (ID 1) has no ink. Representative raster bounds:
`A` and `B` X=0..10; lowercase `m` and `n` X=0..11;
`I` X=3..7. This independently explains why a 12-unit ASCII
advance can place glyphs without ink overlap, while a
bbox-trimmed/3-pixel-spaced preview cannot replicate the native
measurement. It does **not** establish the EU-beta resource's
byte identity or original GS filtering/blending.

`test_arika_menu_ffon_native.py` provides an opt-in
`SDBZ_FFON_FONT` source-column oracle. CI uses synthetic bitmaps
and does not distribute or require game assets. The original
EU-beta ELF's `0x19A030` half-width instruction remains the
authoritative advance evidence regardless of regional resource
differences.

**Next:** trace the text command consumer reached through
`0x199EE0 → 0x112780` and the resource-specific FFON raster
path; compare the positions of several glyph edges with a
runtime GS capture to prove original UV bounds.
