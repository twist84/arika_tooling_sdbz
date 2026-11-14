# Native stage background / clear colour (four regional ELF builds)

The sky/background colour is **not derived from a PIX texture edge**. The native
stage classes return explicit RGBA float vectors through virtual-table slot 29
(zero-based, offset `0x74`). The accessor is `CStageXX`-specific. A 16-byte
RGBA vector stores channels as values corresponding to `R/255, G/255, B/255, 1`.
The next accessor, at slot 31, identifies the end of the contiguous colour
vector table; that establishes **16 vectors across 13 stage classes**.

The bytes and ordering below were independently extracted from all four ELF
files (retail Europe, Europe beta, Japan and USA). All four match.

| Native class | Asset(s) | RGB presets (decimal) | Hex |
|---|---|---|---|
| CStage00 | s00a.stg | (31,31,31) | #1F1F1F |
| CStage01 | s01a.stg | (30,164,212) | #1EA4D4 |
| CStage02 | s02a.stg | (31,159,234) | #1F9FEA |
| CStage03 | s03a.stg / s03b.stg | (235,221,255), (0,215,218) | #EBDDFF, #00D7DA |
| CStage04 | s04a.stg / s04b.stg | (196,89,243), (196,89,243) | #C459F3 (both) |
| CStage05 | s05a.stg (two states) | (90,164,54), (31,71,40) | #5AA436, #1F4728 |
| CStage06 | s06a.stg | (35,176,230) | #23B0E6 |
| CStage07 | s07a.stg | (125,167,217) | #7DA7D9 |
| CStage08 | s01a.stg (alternate class) | (20,4,29) | #14041D |
| CStage09 | s02a.stg (alternate class) | (19,32,94) | #13205E |
| CStage10 | s10a.stg | (31,31,31) | #1F1F1F |
| CStage11 | s11a.stg | (30,164,212) | #1EA4D4 |
| CStage12 | s12a.stg | (235,132,235) | #EB84EB |

## Reproducibility

Follow the in-ELF `CStage00` through `CStage12` class-name string references
to the getter method (vtable slot 2). Read slot 29 (offset `0x74`) from its
vtable; the getter constructs a base address from `lui` and `addiu`, adds
`state_index * 16`, and returns the address. Decode the little-endian RGBA
floats there. The number of entries is the distance to the slot 31 table
divided by 16.

| Class | US table RVA | EU beta | EU retail | Japan |
|---|---|---|---|---|
| CStage00 | 0x488E40 | 0x486930 | 0x489D40 | 0x4876B0 |
| CStage01 | 0x48D2C0 | 0x48ADB0 | 0x48E1C0 | 0x48BB30 |
| CStage02 | 0x488510 | 0x486000 | 0x489410 | 0x486D80 |
| CStage03 | 0x48C8A0 | 0x48A390 | 0x48D7A0 | 0x48B110 |
| CStage04 | 0x488EE0 | 0x4869D0 | 0x489DE0 | 0x487750 |
| CStage05 | 0x48A5F0 | 0x4880E0 | 0x48B4F0 | 0x488E60 |
| CStage06 | 0x489E60 | 0x487950 | 0x48AD60 | 0x4886D0 |
| CStage07 | 0x489710 | 0x487200 | 0x48A610 | 0x487F80 |
| CStage08 | 0x48D070 | 0x48AB60 | 0x48DF70 | 0x48B8E0 |
| CStage09 | 0x489590 | 0x487080 | 0x48A490 | 0x487E00 |
| CStage10 | 0x4902D0 | 0x48DDC0 | 0x4911D0 | 0x48EB40 |
| CStage11 | 0x490420 | 0x48DF10 | 0x491320 | 0x48EC90 |
| CStage12 | 0x490980 | 0x48E470 | 0x491880 | 0x48F1F0 |

Addresses in the table are virtual addresses, not file offsets; the ELF PT_LOAD
segment maps file offset `0x80` to virtual address `0x100000` for these builds.
Thus the conversion for these ELFs is `file_offset = vaddr - 0xFFF80`.

## Editor behaviour and limitations

- Automatic normal stage colour when loading a native stage, including virtual
  archive browsing. `s03b` and `s04b` select state 1 by default.
- `Viewport > Stage background…` chooses the native class/state for ambiguous
  assets such as `s01a`, `s02a`, and `s05a`.
- Selection persists in the version 1 `.arika-scene.json` project as an optional
  `stage_background` field and participates in undo/redo; **it is not written
  into the `.stg` file**, because the game selects it at runtime.
- The existing `Background color…` control remains a temporary per-viewport
  manual override. Existing projects without the new field use normal defaults.
- The renderer already converts sRGB picker colours to linear when clearing
  sRGB attachments; use the recovered byte values without gamma-compensating twice.

**Still to validate visually:** screenshots from actual gameplay under both
normal and alternate runtime states against the Qt editor. This research covers
the flat background/clear colour, not all possible textured sky geometry,
fog, lighting, or environmental effects.
