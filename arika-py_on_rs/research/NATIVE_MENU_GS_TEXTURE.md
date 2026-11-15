# EU-beta GS texture registration: native writer and replay

**Game:** SLES_541.61, EU beta, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
Addresses below are EE virtual addresses from the user-owned ELF.
The repository contains only derived formulas, scalar replay tools and
asset-free tests: **not** the ELF, PIX art, or a live GS capture.

## End-to-end call path

```text
0x19B5C0 engine sprite command opcode 1
  -> 0x104820: cache two renderer-selection words
     GP/BSS 0x4FF470 and 0x4FF474
  -> 0x10DA20: resolve texture-resource handle via 0x10D7C0
     -> 0x10C3E0: validate resource ID and read 48-byte descriptor
        at 0x4FF8F0 + (id-1)*0x30
        -> write six 64-bit register words into template at
           0x439E90, 0x439EA0, 0x439EB0, 0x439EC0,
           0x439ED0, 0x439EE0
           -> optionally call 0x10C7C0 for mipmap block allocation
     -> 0x103E70: send fixed source template at 0x439E70
        -> 0x103B00 DMA allocator
        -> 0x1002B0 packet copy
        -> 0x102C90 hardware queue submission
```

The `0x10C3E0` function rejects resource IDs 0 and >=256, a
descriptor with `+0x02` equal to zero, or one with a nonzero
`+0x14` while `+0x04` is zero. It returns one on valid
completion and zero on these paths. A native instruction replay
confirms these predicates, rather than assuming every TIM2 decoded
by the editor has an active GS resource allocation.

## Descriptor fields read by native instructions

**Input is exactly 48 bytes from running EE memory**, not the
on-disc XPIX/TIM2 header. The scalar writer does not read all fields
of the record, and the record's complete object schema remains
partially unknown.

| Offset | Native access | Writer interpretation |
| --- | --- | --- |
| +0x02 | signed halfword | GS TEX0 TBP0 / initial mip base |
| +0x04 | signed halfword | CLUT base address CBP (required when +0x14 nonzero) |
| +0x06 | signed halfword | GS TEX0 TW (log₂ width) |
| +0x08 | signed halfword | GS TEX0 TH (log₂ height) |
| +0x0E | unsigned halfword | GS TEX0 PSM and mip-format selector |
| +0x10 | unsigned halfword | GS TEX0 CPSM for CLUT textures |
| +0x12 | signed halfword | Mipmap-level count |
| +0x14 | signed halfword | Branch selecting CLUT-backed versus direct texture |
| +0x16 | signed halfword | Texture width / texture-buffer-width calculation |
| +0x18 | signed halfword | Texture height / clamp endpoint calculation |

The descriptor table base is `0x4FF8F0`, and indexing is **one-based**:
`entry_address = 0x4FF8F0 + (resource_id - 1)*48`.
Its values live in runtime memory; a file-backed ELF provides the
instruction formula but **not those descriptors**.

## Actual GS GIF A+D template

At ELF `0x439E70`, the file-backed template contains:

| Entry | Destination register | GS meaning |
| --- | --- | --- |
| 1 | `0x3B` | TEXA |
| 2 | `0x14` | TEX1_1 |
| 3 | `0x06` | TEX0_1 |
| 4 | `0x08` | CLAMP_1 |
| 5 | `0x34` | MIPTBP1_1 |
| 6 | `0x36` | MIPTBP2_1 |

The original memory template begins with 64-bit `0x70000007`,
a 16-byte GIF tag `0x1000000000008006, 0xE`,
and six 16-byte value/address pairs. `0x103E70`
updates the copied DMA header to
`(u64 0xF0000007, u32 0x13000000, u32 0x51000007)`
before submission. It is a **128-byte** packet, with one
six-register GIF A+D sequence. This differs from the
`0x500000xx` header branch used in TEST/ALPHA emission;
the two paths must not share an assumed packet header.

### Recovered register packing

`TEXA` always sets `TA1=0x80`, `AEM=0`. It sets
`TA0=0x80` when `CPSM==1` on the nonzero-CLUT branch,
or when `PSM==1` on the direct branch; otherwise `TA0=0`.

`TEX1_1` is `0x60` (MMAG=1, MMIN=1) if renderer
BSS word `0x4FF470` is nonzero; otherwise it is zero.
This identifies the **filter selector's register effect**,
not which value the game holds throughout a live menu frame.

`TEX0_1` contains descriptor TBP0 at bits 0+, buffer width
`TBW=trunc(width/64)` with a minimum of 1 at bits 14+,
`PSM` at 20+, `TW` at 26+, `TH` at 30+, and
`TCC=1` at bit 34. For CLUT-backed textures, the
writer additionally packs `CBP` at bit 37, `CPSM`
at bit 51, and `CLD=2` at bits 61+. The native code
uses 64-bit shifts/ORs on its signed and unsigned
halfword loads; the decoder preserves that behavior
for tested, nonoverflowing descriptors.

`CLAMP_1` is zero when renderer BSS word `0x4FF474`
is zero. Otherwise it is
`5 | (width << 14) | (height << 34)`,
giving `WMS=WMT=1`, `MINU=MINV=0`,
`MAXU=width` and `MAXV=height` (subject to
the GS field widths). Both flags are *external*
to the 48-byte texture descriptor.

For mip counts below 2, `MIPTBP1_1/MIPTBP2_1` are zero.
For 2..7, the writer calls `0x10C7C0` with pixel format,
TBP0, successively halved dimensions and an incrementing
`count`, packing up to six mip TBP/TBW pairs (three per register).
The calculation is **not** the obvious monotonically increasing
mip allocator: for one synthetic RGBA descriptor at
TBP0=0x100, width=512, height=256, levels=4,
the native mip base outputs are `0x300, 0x1A0, 0x12A`.
It restarts from TBP0 for each call while passing already
halved width/height. Both recovered outputs and the Python
implementation agree instruction-for-instruction.
More than six mip entries would exceed the observed native
stack scratch; the decoder rejects such unverified inputs.

## Reproducible testing and optional capture decoding

`arika_menu_gs_texture.py` converts an explicitly captured
descriptor and the two renderer flags into six raw GS register
values, with TEX0/TEX1/TEXA/CLAMP field decoders and exact GIF
A+D packet serialization. For a **user-owned runtime memory dump**:

```sh
cd arika-py_on_rs
python arika_menu_gs_texture.py texture_record_48.bin \
  --slot 1 --filter-flag 0x1 --clamp-flag 0x1 \
  --gif-output reconstructed_texture_packet.bin
```

Those flags and slot are **examples**, not a claim about actual
game state. To get a real output the values must be read from the
same PCSX2 game frame as the 48-byte descriptor.

The asset-free CI tests use synthetic descriptors for direct
and CLUT branches, early returns, filtering/clamping, TEXA
alpha constants, mipmap calculations, and exact 128-byte GIF/DMA
layout. Two optional tests run with:

```sh
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 \
  python -m unittest test_arika_menu_gs_texture -v
```

One checks the original six-register template against its
SHA-256-verified ELF bytes. The other uses
`arika_menu_gs_texture_elf_oracle.py`, a tiny scoped
R5900 scalar interpreter that dynamically reads actual
`0x10C3E0/0x10C7C0` instruction words. This test compared
**240 deterministic synthetic resource descriptors** covering
valid and invalid allocations, mipmapping, indexed/direct
formats and both renderer flags. The resulting six 64-bit
register values were **bit-for-bit identical** for all
successful native returns; invalid native paths matched
the decoder's explicit `None`. The replay handles the
R5900 *three-operand MULT writing RD*, rather than using
ordinary two-operand MIPS assumptions. The scalar interpreter
does not model DMA, VU, PS2 FPU or the full GS.

## Still unresolved before changing the Qt sampling mode

- Capture live records and resource selector indices from the
  menu, including the renderer BSS words `0x4FF470`
  and `0x4FF474`, and confirm when each is changed.
- Validate real GS `TEX0/TEX1/CLAMP/TEXA` during a
  frame, the texture data/CLUT upload and the timing of
  any later per-sprite overrides.
- Recover `TEX2` and alpha-write/texture sampling details
  if other render paths require them.
- Compare final output with PCSX2 GS captures. The screenshot
  verifies an occlusion result but not per-pixel alpha,
  filtering, texel rounding or active resource values.
- Do **not** silently replace the functioning Qt editor's
  depth/texture renderer with values inferred from a
  synthetic descriptor. The user-provided PIX/FFON,
  4:3 framing and 140-frame diagnostic timeline remain intact.
