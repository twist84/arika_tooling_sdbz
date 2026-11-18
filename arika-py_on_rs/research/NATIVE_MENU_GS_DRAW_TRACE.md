# GS per-draw register trace inspection (EU-beta SDBZ)

The repository already reconstructs native engine opcode-1 sprite
bindings and **conditional** TEX0/TEX1/CLAMP writes. Those are not a
measured GS submission, and cannot prove what PCSX2 rendered for a
specific menu sprite. The next useful artifact is an **actual ordered**
list of GS register writes and draw boundaries.

`arika_menu_gs_draw_trace.py` consumes that externally observed trace.
It does **not** capture PCSX2, read `GAME.DAT`, infer GS state from
screenshots, select a Qt per-atlas filter, or reconstruct missing writes.

## Input contract

Pass one JSON object with `format="ARIKA_GS_AD_DRAW_TRACE"`,
`version=1`, and an ordered `events` array. Events are:

- `{"kind":"write","address":"0x14","value":"0x60"}`: one
  **observed** GIF A+D register write. Both fields accept unsigned
  integers or base-prefixed numeric strings.
- `{"kind":"draw","context":1,"label":"optional note"}`: an observed
  draw boundary, with the actual GS context (1 or 2). Do **not** infer
  this from the menu item, an ELF initializer, or a texture attachment.
  The label is for human correlation only, **not** proven ownership.

All events must be in actual submission order. Record writes after
resource binding and before the relevant draw. Feed one uninterrupted
capture; the tool carries observed registers forward between draws.
A trace that starts mid-frame can omit already-live state. Such fields
remain unknown, **not** zero or hardware reset defaults. The tool
does not derive the GS context from PRIM/PRMODE; the capture must
supply it.

Asset-free synthetic example (not a real SDBZ measurement):

```json
{
  "format": "ARIKA_GS_AD_DRAW_TRACE",
  "version": 1,
  "events": [
    {"kind": "write", "address": "0x14", "value": "0x60"},
    {"kind": "write", "address": "0x3b", "value": "0x8000000000"},
    {"kind": "draw", "context": 1, "label": "synthetic draw A"},
    {"kind": "draw", "context": 2, "label": "synthetic draw B"},
    {"kind": "write", "address": "0x15", "value": "0"},
    {"kind": "draw", "context": 2, "label": "synthetic draw C"}
  ]
}
```

```sh
cd arika-py_on_rs
python arika_menu_gs_draw_trace.py trace.json > draw-states.json
python -m unittest test_arika_menu_gs_draw_trace -v
```

Draw A has observed linear TEX1_1 (`0x60`), draw B has
**unknown** TEX1_2, and draw C has observed nearest TEX1_2
(`0x00`). TEXA is a shared global register. Known per-context
registers include TEX0, TEX1, CLAMP, TEST, ALPHA and ZBUF. Their
raw values are retained and existing project decoders annotate known
fields. TEX1 minification codes 2..5 are explicitly mipmap modes and
6..7 stay reserved; a generic “bilinear” label is not assigned.

## How it relates to the other inspectors

1. Capture matching-frame EE RAM and intermediate command buffers for
   `arika_menu_gs_correlation.py`. That gives candidate opcode-1
   bindings, texture descriptors and conditional writer output.
2. Independently capture **the actual GS A+D register writes**, in
   submission order, plus reliable draw boundaries and GS context.
   Decode those observations into the format above.
3. Compare the two reports by recorded event/frame identity. A
   conditional native writer result matching a draw's TEX1/TEX0
   strengthens the case, but is **not** proof of sprite ownership.
   The link still needs a measured sprite/command callback return
   and a tracked draw submission without intervening overrides.
4. Only after such a link is validated should the Qt preview consider
   per-sprite sampling. Active TEST/ALPHA/ZBUF alone does not reproduce
   PCSX2's GS rasterization.

This milestone intentionally does **not** add a PCSX2 hook or an
automatic GIF/GS dump parser. A normal PCSX2 screenshot cannot supply
this trace. A debugger/instrumented GS event stream is needed.
**No proprietary assets, binary captures or ROM data are committed.**

See [NATIVE_MENU_GS_SAMPLING.md](NATIVE_MENU_GS_SAMPLING.md),
[NATIVE_MENU_RESOURCE_CORRELATION.md](NATIVE_MENU_RESOURCE_CORRELATION.md)
and [PCSX2_COMPARISON_RENDERING.md](PCSX2_COMPARISON_RENDERING.md).
