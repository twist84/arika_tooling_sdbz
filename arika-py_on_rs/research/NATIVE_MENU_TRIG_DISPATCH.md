# EU-beta native sine/cosine dispatcher (offline milestone)

Verified target: `SLES_541.61`, EU beta, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
The original ELF is user-owned and is never committed.

## Exact call graph

The OPTIONS `0x37FC00` and DRAGON SUMMONING `0x380450`
per-part character idle callbacks call the same native
float32 trig wrappers:

| Address | Function | Shared dependencies |
| --- | --- | --- |
| `0x1859D8` | cosine wrapper | `0x183DE0` cosine leaf; `0x184798` sine leaf |
| `0x185C78` | sine wrapper | same leaves |
| `0x182900` | angle reducer | used by both wrappers for large angles |
| `0x183DE0` | cosine polynomial/kernel | takes the high/low reduced remainder |
| `0x184798` | sine polynomial/kernel | takes the high/low remainder plus integer mode |

Both wrappers construct the absolute-value bit mask
`0x7FFFFFFF` and compare `input_bits & mask`
to the literal `0x3F490FD8` (**float32 π/4**).
The immediate is assembled at cosine `0x1859EC`/
`0x1859F8` and sine `0x185C90`/`0x185C98`.

For `abs(input) <= pi/4`, the cosine wrapper
directly calls `0x183DE0(input, +0.0f)`; the
sine wrapper directly calls `0x184798(input, +0.0f, mode=0)`.
For greater input magnitudes the wrapper first calls
`0x182900`, which returns an integer quadrant and
two f32 remainder values in the caller's stack slots
+0 and +4. The selected leaf receives that pair.

## Native `quadrant & 3` route table

The following applies **only after** the native reducer has
supplied both the quadrant and reduced high/low words:

| q & 3 | Cosine | Sine |
| --- | --- | --- |
| 0 | +cosine kernel | +sine kernel (mode 1) |
| 1 | −sine kernel (mode 1) | +cosine kernel |
| 2 | −cosine kernel | −sine kernel (mode 1) |
| 3 | +sine kernel (mode 1) | −cosine kernel |

The sign changes use the native `NEG.S` instruction,
including in branch delay slots. The recovered
`arika_menu_native_trig.py` models this as an IEEE
sign-bit XOR, **including signed zero**. It never calls
host `math.sin`/`math.cos` or computes a guessed
quadrant. Unknown reducer outputs are rejected.

Source sites: cosine direct leaf JAL `0x185A10`,
reducer JAL `0x185A20`, quadrant leaf calls
`0x185A60 / 0x185A78 / 0x185A88 / 0x185A98`,
negations `0x185A84 / 0x185A94`.
Sine direct leaf JAL `0x185CB0`, reducer JAL
`0x185CC0`, quadrant calls
`0x185D04 / 0x185D1C / 0x185D34 / 0x185D48`,
negations `0x185D40 / 0x185D50`.
The branch selection is not a table lookup in the
binary; it is explicit branch/branch-likely control flow.

## Code, validation and fidelity boundary

`arika_menu_native_trig.py` exports
`trig_dispatch(wrapper, angle_bits, reduced_quadrant)`
and `apply_native_neg_s(result_bits, dispatch)`.
Both use exact 32-bit bit patterns rather than
rounding source floats through host 64-bit trig.
The core unit tests cover:

- Direct vs reduced path at π/4 and signed π/4,
  including positive and negative zero.
- All four native quadrant routes for both
  wrappers; negative and larger reducer quadrants
  are masked with `&3`.
- IEEE negative-zero and normal result bit signs.
- Rejection of unknown reducer quadrants instead
  of fabricating a quadrant from the host library.

An **optional exact-ELF verification test** uses
`SDBZ_EU_BETA_ELF=/path/to/SLES_541.61`
to SHA-256-check the user-owned file and verify all
JAL destinations, the two π/4 immediates and the
four `NEG.S` instruction sites directly.
CI runs the asset-free tests and skips that opt-in
file-backed test when the ELF is absent.

**This is a concrete recovery of the wrapper, not the
whole PS2 libm implementation.** The reducer
`0x182900` itself has multiple argument ranges
and compensated f32 high/low remainders. The leaf
polynomial/accumulator behavior also needs recovery
and EE FPU semantics before the Qt editor can
replace its host `math.sin/math.cos` calls. The
angle domain of the menu idle curves is finite,
but assuming host angle reduction or math quality
matches EE libm would remain guesswork.

The next static target is `0x182900`'s normal
menu-angle range and its return-high/low pair.
The existing native menu clocks and 140-frame
diagnostic preview remain untouched.
