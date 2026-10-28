# Menu startup defaults and constructor correction

The version 12 report adds a `startup` model: the ELF's loaded zero-fill region plus two verified menu constructors. Positions and companion templates are now read from that model instead of file bytes alone. This recovers initial values; it does not capture a running game or execute every global constructor.

**Correction:** earlier companion examples used the templates' raw, pre-constructor Y bases of zero. Startup changes them to **320, 324 and 352**. The current Python/native RNG examples and SVGs have been regenerated with those values. Their random streams are unchanged; their geometry and startup/reset-state metadata are corrected.

## Startup evidence

The entry code beginning at `0x0010011C` clears `[0x004FC900, 0x0063C380)` before entering main. This matches the first PT_LOAD segment's file-to-memory tail. `0x00420160` calls `0x001718C0`, which supplies constructor table `[0x004E3150, 0x004E32A8)` to walker `0x00171D20`. The walker invokes its 86 entries in increasing address order.

Entries 73 and 74, at `0x004E3274`/`0x004E3278`, reference:

| Constructor | Verified effect |
|---|---|
| `0x004E2370` | Writes companion Y bases 320, 324 and 352 into the three template records |
| `0x004E23B0` | Writes item-3's second Y offset as 204 and particle clipping boundary as 239 |

The constructor evaluator reads and executes the actual scalar initializer words, including their JR delay slots. It supports only the required straight-line operations and fails on unsupported instructions. The report records function words, input constants, every write's old/new bits and affected positions.

## Recovered initial values

| Address | Initial value | Source |
|---|---|---|
| `0x004FDC30` / `0x004FDC34` | 0, 0 | Zero-fill; item-0 base |
| `0x004FDC38` / `0x004FDC3C` | 0, 0 | Zero-fill; item-0 strip offsets |
| `0x004FDC40` / `0x004FDC44` | 0, 0 | Zero-fill; item-4 strip offsets |
| `0x004FDC50` / `0x004FDC54` | 0, 0 | Zero-fill; small shared component 2 base |
| `0x004FDC58` | 0 | Zero-fill; first item-3 sprite Y offset |
| `0x004FDC5C` | 204 | Constructor; second item-3 sprite Y offset |
| `0x004FDC60` | 239 | Constructor; item-3 particle clipping boundary |
| `0x004FC990` / `0x004FC994` | 0, 0 | Zero-fill; initial inactive-slot reset position |

The loaded image distinguishes `file_backed`, `startup_zero_fill` and `startup_constructor` provenance. Reads outside declared loaded segments still fail. The raw `c_elf_image` reader continues to reject addresses outside file-backed segments; only the explicit startup-memory model supplies mapped zero-fill bytes.

## Preview/export changes

The static geometry diagrams now contain **66 item quads and 10 shared quads**. All 21 first-group literal/decoration sprites have initial positions. Item 3's first one-pixel-high sprite uses its fixed scale of 204; the second begins at the constructor-derived Y offset 204. The previously omitted small shared component is included at its initial base.

All four scrolling strips can now use recovered startup origins without authored overrides:

| Item | Initial strip origin |
|---:|---|
| 0 | 0, 0 |
| 2 | 128, 86 |
| 4 | 0, 134 |
| 6 | 208, 230 |

`--origin` remains available for an explicit runtime/diagnostic override. New full-cycle item-0/item-4 traces and SVGs are included. Their final two samples verify phase wrap to 0 and 1. The companion exporters use the startup template heights and reset positions, and record `startup_model` in their version 3 traces.

Both companion RNG modes were regenerated and replayed from their recorded integer arrays; every frame and final companion state matched. This supersedes the earlier pre-constructor geometry, not the underlying RNG algorithm or random-value streams.

## Validation and scope

Fifty-seven menu tests pass. New cases check file/BSS boundary reads, loaded-range bounds, constructor return-delay writes, comparison against the independently interpreted native initializer words, and corrected preview values. The expanded geometry set also passes 159 plain-sprite endpoint comparisons.

Only zero-fill and the two listed menu constructors are modeled. Other global constructors, menu entry callbacks and subsequent runtime writes are not simulated. The values are a reproducible **startup baseline**, not proof that these globals never change during gameplay. Native context RNG state, textures, owner animation/visibility and full compositing still require separate work.
