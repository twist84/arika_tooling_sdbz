# EU-beta main-menu draw commands and sprite render-state boundary

ELF: `SLES_541.61`, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
All addresses are PS2 EE virtual addresses. This report uses verified
instruction bytes, not a captured PCSX2 GS trace. **The engine's
intermediate draw-command opcodes are not automatically GS register
values.** Do not infer a QPainter composition mode from an untraced
opcode.

## First correction: QPainter depth sorting is not native call order

The already recovered shared function `0x378170` issues draw calls for:

1. Background sprite (shared +0x10, texture entry 1).
2. Banner (callback `0x3786A0`, texture entry 2).
3. Tile owner (callback `0x376290`, two tile sprites and ten active
   companion slots, texture entry 2).
4. Seven small sprite owners (callback `0x376C20`, texture entry 3).
5. Conditional overlay (shared +0x70, texture entry 8, only when
   shared +0xE0 is zero).

At `0x379E60`, the parent calls shared draw, then **pending old
item**, **current item**, and finally the arrow-owner vtable +0x4C
at parent +0x40. In its item-3 first-layer draw `0x37A910`, the
original callback draws two literal sprites, six decorations, then
calls `0x37AEE0` for the six-slot particles. The scalar depth values
used by these sprites do **not** provide proof that the engine sorts
the callbacks or that the GS depth-test is disabled.

The Qt editor originally sorted commands by `geometry.depth`,
then briefly changed to painting in strict EE submission order. That
recovered call order but introduced a **visible regression**: the
`MAIN MENU` title disappeared. In the user-provided PCSX2/Qt
comparison from 15 November 2026, the PCSX2 capture (958×719) shows
the title, while the corresponding Qt capture (706×529) lacks it;
the two images share an approximately 4:3 presentation ratio.

The recovered geometry explains why: banner `0x3786A0` is
`[0,16]–[264,64]` at Z **99**, while shared small sprite #2
covers `[0,0]–[320,152]` at Z **5**. The small sprite
is submitted **after** the banner in `0x378170`, and opaque
QPainter source-over would cover the entire title. The PCSX2 image
demonstrates that *native draw submission order is not equivalent
to the game's final compositing/occlusion order*.

The fix separates these two concepts: `render()` builds its
`draw_queue` in native EE submission order (shared, pending, current,
arrows; first-layer decorations before particle submission). The
pure `software_painter_order()` then returns a **stable, ascending
depth** order for the Qt-only rasterization fallback, without
mutating the source command queue. Equal depths preserve native
submission order. This brings the banner in front of small sprite #2
in the editor without hardcoding a title overlay, offset, texture
or animation timing. It is a **software approximation** rather
than a reconstruction of GS `TEST`, `ZBUF`, `ALPHA` or its
per-pixel depth writing rules; blending and semitransparent
overlaps may still require further recovery.

Offscreen Qt regressions record the unchanged ELF call order,
verify the stable painter-depth order and test the banner/small
overlap using synthetic blue/red atlases at the native coordinates.
No game artwork or supplied screenshots are committed. The
independent 140-frame diagnostic timeline remains functional.

## Generic sprite reset: `0x2FDA00`

This method writes the raw sprite instance state below. Its 35
file-backed R5900 words are interpreted by
`test_arika_menu_gs_state.py`, including the `JR $ra` delay-slot
write at `0x2FDA88`.

| Sprite-relative fields | Reset value | Evidence and scope |
| --- | --- | --- |
| +0x10/+0x14/+0x18 | f32 zero | Presentation XYZ |
| +0x1C/+0x20/+0x24 | f32 one | Three presentation scale values |
| +0x28/+0x2A/+0x2C/+0x2E | s16 zero | Endpoint UVs: left/right/top/bottom |
| +0x30/+0x34/+0x38/+0x3C | f32 one | Four vertex modulation fields; +0x3C is used for the overlay fade |
| +0x40 | byte zero | Selects native sprite vtable draw branch |
| +0x44 | null pointer | Texture resource attachment |
| +0x48..+0x4B | bytes 0, 1, 0, 0 | Resource/sampler flags; decoding incomplete |
| +0x4C | byte 2 | Unnamed engine mode A, emitted as packet opcode 3 |
| +0x4D | byte 1 | Unnamed engine mode B, emitted as packet opcode 2 |
| +0x4E/+0x50/+0x52/+0x54 | s16 0, 512, 0, 448 | Default raster bounds (not a GS display-register capture) |
| +0x58 | u32 3 | Unnamed primitive-type/mode field, emitted as opcode 4 |
| +0x5C | byte 1 | Unnamed engine mode field, emitted as opcode 5 |

The `0x2FD8F0` texture-attachment method stores the resource handle
at +0x44 and **four independent bytes** at +0x48..+0x4B. The fourth
byte is a return delay-slot store, not a missing field. A native-word
oracle checks all five writes over several non-default combinations.
An attached texture's dimensions are subsequently obtained via vtable
+0x40/+0x44 and used to normalize the UVs by `0x2FCE20`, as tested
in `test_arika_menu_particle_uv.py`.

## Draw dispatch and intermediate engine packets

The common sprite vtable at `0x4EDCF0` has +0x10 =
`0x2FD8A0`, +0x28 = `0x2FDA90` and +0x30 = `0x2FDDB0`.
The menu particle subclass at `0x4EDCB0` has +0x10 =
`0x2FD8A0`, +0x28 = `0x2FCF60` and +0x30 =
`0x2FD150`. The `0x2FD8A0` branch is:

```text
if (sprite[0x40] == 0)
    call sprite.vtable[0x28];
else
    call sprite.vtable[0x30];
```

This dispatch is verified through all 18 native instruction words
for both zero and nonzero byte values. The subclass +0x28
(`0x2FCF60`) allocates/copies a 0x90-byte sprite and passes it
through `0x2FE8E0`; the +0x30 (`0x2FD150`) constructs a
command stream using the sprite's current vertex fields.
Neither method is an independently verified immediate *GS* drawing
mode. The host Qt renderer is not switched between arbitrary
blend modes based on this byte.

The intermediate packet writers expose the following *observed
command encoding*, not a decoded GS state:

| Intermediate command | Producer | Payload |
| --- | --- | --- |
| 1 | `0x2FE920` | Texture resource, four sampler/mode bytes |
| 2 | `0x2FEA70` | Raw sprite +0x4D byte |
| 3 | `0x2FEAD0` | Raw sprite +0x4C byte |
| 4 | `0x2FD150` / `0x2FDDB0` | Sprite +0x58 field |
| 5 | `0x2FD150` / `0x2FDDB0` | Sprite +0x5C field |
| 6 | `0x2FEB30` | Raw bounds from +0x4E/+0x52/+0x50/+0x54 |

The generic/textured command builders also pass the sprite
+0x30..+0x3C color to `0x2FEBF0`, and geometry/UV vertices
to `0x19B0A0`. The shared overlay fade function
`0x377F40` stores its recovered float in
`shared+0xAC = overlay_sprite+0x3C`, linking the previously
recovered fade directly to the fourth vertex modulation field.
This supports the Qt model's evolving tint alpha **as a
presentation approximation**, but does not establish the
underlying GS ALPHA blending equation.

## Recovered command consumer: `0x19B5C0`

The next consumer is **now identified**. `0x19B5C0` obtains the
graphics context through `0x199C60`, copies the 10-byte current
render state from context +0x5C through `0x199500`, then reads the
sprite command-buffer header. The header's **u32 at +0x04 is the
record count**, with records starting at +0x08. At `0x19B614`, a
`SLTIU` range check accepts only opcodes 0..8, and
`0x19B620..0x19B634` jumps through the nine-entry
little-endian table at `0x004C02C0`.

| Opcode | ELF jump target | Verified consumer effect / length |
| --- | --- | --- |
| 0 | `0x19B658` | Calls context vtable +0x34 with the local state, processes its opaque data, and advances 8 + payload byte length from record +0x04 |
| 1 | `0x19B688` | Uses selector u16 at +0x04 and byte at +0x06 to index two GP-relative resource tables, calls `0x104820` and `0x10DA20` on the resource pointer at +0x08; advances 12 |
| 2 | `0x19B6E8` | Copies signed halfword at +0x02 into local state halfword +0x00; advances 4 |
| 3 | `0x19B6F8` | Copies the low byte from +0x02 into local state byte +0x02; advances 4 |
| 4 | `0x19B6C8` | Copies signed halfword at +0x02 into local state halfword +0x06; advances 4 |
| 5 | `0x19B6D8` | Copies signed halfword at +0x02 into local state halfword +0x08; advances 4 |
| 6 | `0x19B708` | Advances 12 bytes in this dispatcher; no direct local-state update here |
| 7 | `0x19B710` | Advances 12 bytes in this dispatcher; no direct local-state update here |
| 8 | `0x19B640` | Refreshes local state from the graphics context via `0x199500`; advances 4 |

This confirms the earlier producer-side opcode numbering, and
**narrows the next research target** from generic sprite drawing
to the graphics context vtable +0x34 callback, the resource
operations `0x104820`/`0x10DA20`, and the actual GS packet
emission downstream. It still does *not* identify GS blending, Z
testing, texture filtering, or active framebuffer/display settings.

The new standard-library
`arika-py_on_rs/arika_menu_gs_packet.py` can decode captured
**intermediate command-buffer bytes**, retaining all unknown payloads
and exposing only proven local-state mutations. It takes an explicit
optional initial state from a real context; absent values stay
`null`, rather than silently initializing them to guessed modes.

```sh
cd arika-py_on_rs
python arika_menu_gs_packet.py path/to/captured_sprite_packet.bin
python arika_menu_gs_packet.py path/to/captured_sprite_packet.bin --initial-state '{"word0":1}'
```

`test_arika_menu_gs_packet.py` validates the extracted nine
switch targets, each opcode's record length, mixed command/state
sequences, opcode-8 reset, and truncation/unknown-input rejection.
No game files or command-buffer captures are included.

## Renderer context translation: `0x199500` and `0x199340`

`0x199C60` constructs a renderer singleton at `0x00566500`
with vtable `0x004E3300`. The opcode-0 consumer invokes its
vtable +0x34, which resolves to **`0x00199340`**. That method
takes an optional six-field local state, translates several fields
through file-backed tables, and invokes backend setters
`0x00104920` (three integer arguments) and
`0x00104840` (four integer arguments). The latter return
paths cache their **engine setter inputs**, not GS register
contents. The dispatcher also copies the chosen state to
renderer +0x66..+0x6E.

The state copier `0x00199500` consists of 13 MIPS words,
including a return-delay-slot short store. It copies these
ten-byte context fields:

| Source renderer | Destination local state | Type |
| --- | --- | --- |
| +0x5C | +0x00 | signed 16-bit |
| +0x5E | +0x02 | signed 8-bit |
| +0x5F | +0x03 | signed 8-bit |
| +0x60 | +0x04 | signed 8-bit |
| +0x62 | +0x06 | signed 16-bit |
| +0x64 | +0x08 | signed 16-bit |

The **constructor's direct** stores in `0x199CDC..0x199D14`
initialize +0x5C=1, +0x5E=2, +0x5F=0, +0x62=3,
+0x64=1. A direct initialized write to +0x60 was **not**
observed in that function; it is treated as unknown rather
than presumed zero, and runtime writes to any fields remain
possible. These defaults correspond to raw backend setter
inputs `0x104920(2,3,0)` and `0x104840(7,1,3,0)`
when translation is invoked on a matching state.

The first call resolves state word0 through three separate
eight-element u32 tables at `0x4630F0`, `0x463110`,
`0x463130`. The second call resolves word6 through
`0x463150` (four verified values), word8 through the
table at `GP-0x7FC0` (only the first two entries are
treated as a verified array), and byte2 through
`0x463160` (eight values) and `0x463180` (six verified
values). The last two u32s after `0x463180` may be
neighboring data, so their mere presence does not
authorize extending the table. Invalid/unobserved indices
are rejected, not masked into a guessed enumeration.

The pure decoder `arika_menu_gs_context.py` exposes
`decode_render_context(bytes)` for ten bytes copied by
`0x199500` and
`resolve_backend_arguments({word0,byte2,byte3,byte4,word6,word8})`
for the *raw* values used at the two backend call sites.
Its validation suite interprets all 13 copier instructions
over several signed fields, tests the table ranges and
verifies that missing values remain unresolved. The
tables and result arguments are **not** identified as PS2
GS mode enums or final command-register values.

Backend calls now have clear targets for further analysis:
`0x104920` caches and sends three values via `0x104210`;
`0x104840` caches and sends four via `0x103F20`.
The latter routines and their IOP/DMAC/GS effects still
require tracing before any change to alpha, depth or filtering
is justified.

## GS register emission recovered: `0x103F20` / `0x104210`

**This crosses the earlier research boundary.** The `0x104920`
three-parameter caching wrapper calls `0x104210` with context
selector `a7=2`; the `0x104840` four-parameter caching
wrapper calls `0x103F20` with context selector `a8=2`.
Both writers request aligned packet memory through `0x103B00`,
construct DMA/GIF headers, and submit via `0x102C90`.

The emitted 16-byte packet header is
`(u64 0xF0000000 | (N+1), u32 0x13000000, u32
0x50000000 | (N+1))`. At offset +0x10 the actual
GIF tag is `0x1000000000008000 | N`, at +0x18
the register descriptor is `0x0E` (**GIF A+D**),
and from +0x20 onward there are N pairs
`(u64 register_value, u64 GS_register_address)`.
Context mode 0 emits context 1 only; 1 emits context 2;
2 emits both. These address definitions are independently
documented in the
[PCSX2 GSRegs.h](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/GS/GSRegs.h)
and [PS2SDK libgs.h](https://github.com/ps2dev/ps2sdk/blob/master/ee/libgs/include/libgs.h).

| Emitter | GS A+D destination(s) | Source and conversion |
| --- | --- | --- |
| `0x103F20` | `ZBUF_1=0x4E`, `TEST_1=0x47`, `ZBUF_2=0x4F`, `TEST_2=0x48` | `ZBUF` depends on runtime BSS `0x4FF3BC` and `0x4FF3B0`, plus incoming z-write selector. `TEST` uses two native jump tables at `0x4B4B90` and `0x4B4BB0`, and normalized AREF. |
| `0x104210` | `ALPHA_1=0x42`, `ALPHA_2=0x43` | `A,B,C,D,FIX` come from one of three five-byte lookup tables at `0x439290`, `0x439350`, `0x439410`. First byte `0xFF` skips emission. |

`0x103F20` maps native Z-test selector 0..7 to GS
`ZTST = [0,1,1,1,1,1,3,2]` and alpha comparator
selector 0..7 to `ATST=[0,1,4,7,2,3,5,6]`.
It sets `ATE=1`, `ZTE=1`, `AFAIL=0` and
`ZMSK=0` only if incoming z-write selector is exactly 1.
For alpha reference `a7`, 0 stays 0, 255 becomes 128,
and nonzero other values are shifted right one with a
lower bound of 1. The game startup-derived selector tuple
`(z_test=7,z_write=1,alpha_compare=3,alpha_reference=0)`
produces **GS TEST = `0x0005000F`**, decoded as
`ATE=1, ATST=7 (NOTEQUAL), AREF=0, ZTE=1,
ZTST=2 (GEQUAL)`. This is a **verified ELF selector
translation**, not proof that the live game retains it
without later state changes.

The startup-derived ALPHA selector tuple
`(a4=2,a5=3,a6=0)` indexes file-backed bytes
`(0,1,0,1,0)` at `0x4392DB`, yielding
**GS ALPHA = `0x44`** in both contexts:
`A=Cs, B=Cd, C=As, D=Cd, FIX=0`. The GS
equation is `(Cs-Cd)*As+Cd` (source-alpha blending).
The game's TIM2 RGBA decoder doubles 0..128 PS2 alpha
to 0..255 for Qt; that remains an approximation to the
actual PS2 blend/texture process.

`arika-py_on_rs/arika_menu_gs_registers.py` implements
a pure source-to-GS translator and strict GIF A+D
packet serializer/decoder, with native selector tables
and an opt-in, SHA-256-verified `extract_alpha_preset()`
that reads the user's *own* EU-beta ELF; no ROM data
or full lookup table bytes are committed. It leaves
ZBUF values **`null`** until actual BSS words from the
running graphics context are provided. It rejects
unknown table indices rather than silently inventing
GS modes. A six-test regression module covers 64
native TEST selector combinations, the AREF special
case, two-context GIF/DMA layout, ALPHA pack/unpack,
invalid inputs and banner occlusion consistency.

To inspect the recovered startup selector path with an
exact user-owned executable:

```sh
cd arika-py_on_rs
python arika_menu_gs_registers.py --elf path/to/SLES_541.61
```

The latest PCSX2 screenshot shows the banner Z=99
visible over the later-submitted small sprite Z=5.
An active GS `GEQUAL` depth test is consistent with
that result. It is not proof that all menu draws use
these exact mode settings, or that the Qt stable-Z
fallback correctly simulates semitransparent pixel
writes in all cases.

### Texture resource chain located, not yet captured

The next texture-related intermediate packet opcode reaches
`0x104820`, whose 6-instruction body stores two
resource-selection words at `0x4FF470` and `0x4FF474`.
`0x10DA20` then loads these words, resolves the current
resource through `0x10D7C0`, and passes the texture handle
plus mode/table pointers to `0x10C3E0`.
The latter checks the resolved texture object and packs
texture-dependent bit fields from offsets including
`+0x02/+0x04/+0x06/+0x08/+0x0E/+0x10/+0x14/+0x16/+0x18`.
Those fields are from **runtime objects**, so their values
cannot be inferred from the ELF's startup data. A future
texture capture or more complete `0x10C3E0` trace is needed
before declaring the menu's `TEX0/TEX1/CLAMP`, sampling
and alpha expansion state. This is the next hardware
investigation target.

### Remaining hardware evidence

- Obtain runtime values for `0x4FF3BC` and
  `0x4FF3B0` and confirm the actual allocated
  ZBUF base and pixel format. They are BSS and
  **cannot be read from file-backed ELF bytes**.
- Record the active `TEST/ALPHA/ZBUF` and
  texture/resource setup across a complete menu frame
  with PCSX2 GS dump or emulator instrumentation;
  call-site defaults are not a whole-frame trace.
- Recover texture `TEX0/TEX1/CLAMP/TEXA`,
  framebuffer/alpha-write state and any other engine
  overrides before changing Qt's alpha and
  depth compositing. Do not infer active GS state
  from the startup selector mapping alone.

## Still unresolved before native GS parity

- The GS `TEST/ALPHA/ZBUF` emitters are now identified
  (`0x103F20`, `0x104210`). Follow the texture-resource
  calls and remaining backend functions into `TEX0`,
  `TEX1`, `CLAMP`, `ALPHA`, `TEST`, `ZBUF`, `PRIM`,
  `RGBAQ`, `XYZ`, and `UV/ST` setup. Avoid assigning names
  to the engine's mode bytes until those consumers are traced.
- Confirm texture sampling (nearest/linear), vertex modulation,
  texture alpha expansion and opacity treatment against a real
  game capture and/or a PCSX2 GS dump. Opening the source ELF does
  **not** constitute a live GS capture.
- Check scene/viewport GS display registers separately: the default
  sprite bounds 512×448 are not proof of the active output mode.
- Retain native command submission order while implementing the
  verified depth test and blend equation, if the game uses them.
  A QPainter source-over call alone is not a GS emulator.
- Preserve the game texture/font loading, 4:3 presentation settings,
  diagnostic timeline and Qt editor functionality.

The companion, particle, banner, small-sprite and parent update clocks
remain deterministic, isolated from repaint, and seeded only with an
explicit diagnostic RNG state. No animation timing was guessed.
