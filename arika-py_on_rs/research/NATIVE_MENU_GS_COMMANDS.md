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

## Still unresolved before native GS parity

- Follow intermediate command consumers to the actual GS `TEX0`,
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
