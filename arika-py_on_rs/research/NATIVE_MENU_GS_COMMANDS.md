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

The Qt editor previously sorted *all* commands by a synthetic
`geometry.depth` key, which changed the verified source call order:
the small sprites could precede the higher-depth banner and the shared
overlay could be placed below tiles despite being called afterward.
Native mode now preserves the ELF-issued sequence and paints pending
before current. It also places the item-3 particle pass immediately
after that item's other first-layer sprites. The authored 140-frame
diagnostic timeline still uses its earlier depth sorting for
comparison. This is a call-order correction, **not proof of final
pixel-level Z/alpha compositing parity**. A future GS replay may
require depth testing *on top of* the preserved submission order.

Offscreen Qt tests record sprite draws with synthetic texture-entry
tags and confirm that native submission order differs from the
diagnostic depth sort; another verifies the eight item-3 first-layer
sprites precede particle commands. No game art is committed.

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

## Still unresolved before native GS parity

- Follow the now-identified command consumer `0x19B5C0`, specifically
  graphics context vtable +0x34 and the texture-resource calls, into
  the actual GS `TEX0`,
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
