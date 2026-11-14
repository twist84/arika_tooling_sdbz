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

| Class | US table vaddr | EU beta | EU retail | Japan |
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

An executable extractor is checked in as `elf_tooling/elf_stage_background.py`.
It discovers table addresses from the CStage class methods, so it does not need
hardcoded regional offsets:

```sh
python elf_tooling/elf_stage_background.py --check-regions EUBETA.elf EU.elf JP.elf US.elf
```

The extractor prints a JSON report and returns a nonzero status if the recovered
per-class RGB tables disagree across the supplied ELFs. No game binaries are
included in the repository.

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

The user compared the new native background presets to gameplay and confirmed
the editor result looks correct. Alternate runtime states have not all been
checked individually. This research covers the flat background/clear colour,
not all possible textured sky geometry, fog, lighting, or environmental effects.

## Actual PIX texture-colour comparison

An independent investigation decoded every numbered-stage `.pix` texture from
a user-supplied `sdbz_eu_beta.7z` archive. **Despite its filename, the
archive contains `SLUS_214.42` and a US (`0xC2`) INFO.DAT signature.**
The unpacked GAME.DAT includes 15 stage PIX packs, with **550 decoded
XPIX/TIM2 textures**, no decode failures. The results below refer to this
archive, not an assumed EU-beta asset set.

All 550 RGBA textures were compared to their stage class's recovered ELF
background RGB using Euclidean distance in **decoded 8-bit RGB**. Only
visible pixels (alpha >= 16) were counted; the edge test samples the outermost
four pixels on each side. The near-match threshold is distance <= 3.

| PIX / state | ELF RGB | Nearest visible pixel distance | Pixels within 3 | Edge pixels within 3 |
|---|---|---:|---:|---:|
| s00a / 0 | #1F1F1F | 137.35 | 0 | 0 |
| s01a / 0 | #1EA4D4 | 2.83 | 48,844 | 3,789 |
| s02a / 0 | #1F9FEA | 2.24 | 1,419 | 0 |
| s03a / 0 | #EBDDFF | 1.41 | 6 | 0 |
| s03b / 1 | #00D7DA | 1.41 | 43,041 | 3,045 |
| s04a / 0 | #C459F3 | 1.41 | 3,601 | 932 |
| s04b / 1 | #C459F3 | 1.41 | 9,540 | 2,768 |
| s05a / 0 | #5AA436 | 2.24 | 6,063 | 849 |
| s05a / 1 | #1F4728 | **0.00** | 1,849 | 838 |
| s06a / 0 | #23B0E6 | 2.83 | 44,758 | 3,225 |
| s07a / 0 | #7DA7D9 | 2.24 | 275 | 41 |
| s08a / 0 | #14041D | 1.00 | 64,612 | 4,013 |
| s09a / 0 | #13205E | 2.24 | 420 | 0 |
| s10a / 0 | #1F1F1F | 1.00 | 257 | 84 |
| s11a / 0 | #1EA4D4 | 2.83 | 48,844 | 3,789 |
| s12a / 0 | #EB84EB | 1.41 | 5,294 | 924 |

**15/16** presets have at least one near-matching texture pixel; **12/16**
have matching edge pixels; only `s00a` has no near-matching pixel.
For `s05a` state 1, **107 individual pixels match exactly**.
Texture `s08a.pix[42]` contains a large star-field background whose predominant
dark-purple colour matches ELF `#14041D` within one unit.
`s01a.pix[42]` and `s11a.pix[42]` are cloud/blue-sky textures with
predominant `#20A2D4`, close to ELF `#1EA4D4`.
`s03b.pix[4]` is a cyan sky image strongly matching `#00D7DA`.

Counterexamples matter: `s02a` and `s09a` have some internally matching
pixels in a building/urban texture atlas but **zero matching pixels on
texture borders**. `s03a` only has six near-matching pixels spread among
cloud and scenery textures. `s00a` has only three textures, none remotely
matching its dark-grey clear colour. These cases refute a single universal
"sample a PIX edge" rule.

Whole-chunk checks: the `s01a` and `s11a` packs contain the same 49 unique
XPIX/TIM2 chunks, although indices are reordered (27 match at the same index).
`s01a` versus `s08a`, and `s02a` versus `s09a`, share **no identical
texture chunks** despite related scene layouts. Their differing stage presets
therefore make artistic sense.

**Interpretation:** the explicit ELF constants appear deliberately chosen to
blend with sky textures or other art, but the runtime getter uses a static
stage/state table. Correlation with texture pixels is **not** evidence of
runtime colour computation. Avoid replacing the ELF-derived presets with a
texture-edge heuristic.

### Reproducing the PIX comparison

After extracting assets from your own GAME.DAT:

```sh
python elf_tooling/stage_texture_color_compare.py extracted/stg --output stage_color_audit
```

This can use the original `s01a.pix` files (with a built Rust backend) or
pre-decoded `s01a.pix.000.png` PNG dumps (without the backend).
It emits per-texture measurements in `stage_texture_pixels.csv` and the
per-stage report in `stage_texture_summary.json`. The game archives and
copyrighted textures are not committed to this repository.

