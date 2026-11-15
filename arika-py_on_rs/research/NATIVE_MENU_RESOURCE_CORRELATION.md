# Native sprite/resource/GS correlation — EU beta

Target: EU-beta `SLES_541.61`, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
The instruction observations below were independently checked in the
original **4,180,784-byte EU-beta** executable, not the retail EU/US ELF.

## Newly verified pointer provenance

The previous static attachment inventory established how a sprite's
`+0x44` resource pointer and `+0x48..+0x4B` sampler bytes reach the
generic producer. The important intermediate indirection is now verified:

| Native instruction(s) | Meaning |
| --- | --- |
| `0x2FD078/0x2FD07C` | Read sprite `+0x44`, skip binding when null |
| `0x2FD084..0x2FD094` | Load four individual sampler bytes and invoke `0x2FE920` |
| `0x2FE930/0x2FE934` | Save producer (`a0`) and resource object (`a1`) |
| `0x2FE990..0x2FE99C` | Call **resource-object vtable +0x4C** |
| `0x2FE9A4` | Store the callback's `v0` into opcode-1 command **+0x08** (branch-delay slot) |
| `0x19B6B4/0x19B6BC` | Load command `+0x08`, then **+0x38 of that returned object** into `a0` |
| `0x19B6B8` | Call `0x10DA20` with that texture identifier |
| `0x10DA30/0x10DA60/0x10DA84` | Preserve the original identifier through the resource check and forward it to `0x10C3E0` |
| `0x10C3E0` | Resolve the one-based 48-byte descriptor at `0x4FF8F0+(id-1)*0x30` |

**There are two different pointers.** Sprite `+0x44` contains the
resource object passed as `a1` to `0x2FE920`, while the opcode-1
command `+0x08` contains the result of **that object's vtable +0x4C
callback**. The latter is dereferenced at `+0x38` for the texture ID.
It is incorrect to compare sprite `+0x44` directly to command
`+0x08` or to use the sprite pointer as a texture-descriptor ID.

The callback's target depends on the live resource object's vtable.
Neither the callback result nor the object's lifetime can be
reconstructed from the four known initializers alone.

## Producer binding cache — exact path and addresses

`0x2FE920` checks the resource-object pointer for null at
`0x2FE938`. On a non-null pointer it reads the most recently bound
pointer at `gp-0x1F64` (`0x4FD40C`) at `0x2FE940`, then:

- If the pointer differs, emit a binding, caching new pointer and bytes.
- If the pointer matches, compare **all four** cached bytes at
  `0x4FD410..0x4FD413` against the new `a2..a5`. Mismatching
  any one byte emits another binding.
- If pointer **and all four bytes** match, branch past command creation
  to the epilogue (`0x2FEA38`). This is an **elided opcode-1**, not
  evidence that the sprite was untextured.

For emitted bindings, `0x2FE974..0x2FE98C` writes the 12-byte
opcode-1 record to the producer cursor `+0x24`, with opcode 1 at +0,
the sampler fields at +2/+4/+6/+7, and the callback return at +8.
The producer then advances its cursor by 12 and increments the
packet header's command count through the header pointer at producer
`+0x00` (`0x2FE9D8..0x2FE9F4`).

The initial cached pointer and sampler values are **runtime memory**.
Absent a capture, it is not correct to assume the first draw emits a
binding. `binding_cache_decision` therefore returns an unknown result
when a necessary cache input has not been observed. Different known
resource pointers force emission independently of the cached byte values.

## Capture-driven inspector (no proprietary data committed)

`arika_menu_gs_correlation.py` joins the existing native command
decoder and texture-register replay **only when the caller supplies
actual runtime memory**. It takes a native **intermediate command
buffer** and a contiguous low-address EE RAM snapshot covering the
resource-return object and descriptor table. Both should correspond
to the **same frame and resource-binding moment**.

Example (replace the addresses and files with actual PCSX2 observations):

```sh
cd arika-py_on_rs
python arika_menu_gs_correlation.py native_commands.bin ee_ram.bin \
  --sprite 0x00123400 \
  --observed-return 0x00123400:0x00234500
```

The `--observed-return` option is **not** a static prediction. It
must be a measured vtable +0x4C return for the listed sprite, from
the same execution. Without it, the inspector can still resolve an
opcode-1 returned pointer's `+0x38` ID to a runtime descriptor and
conditional GS register words, but **cannot name its owning sprite**.
If several sprites match, it preserves all candidates rather than
asserting unique ownership. The parser never invents such a return.

For a proposed PCSX2 trace, capture these separately:

1. At sprite draw's `0x2FD094` call (or the second established
   sprite path at `0x2FDB78`), record the sprite EE address, its
   `+0x44..+0x4B` bytes, and the current pointer/flag cache at
   `0x4FD40C..0x4FD413`. A cache hit may suppress a binding.
2. At `0x2FE998`, record the resource-object argument and the
   return from its vtable +0x4C callback. The return goes to
   opcode-1 `+0x08` via `0x2FE9A4`.
3. At `0x19B5C0` entry, record `a0`: the **intermediate command
   packet** begins there with 8-byte header, then a counted list of
   variable-size commands. This is **not** a GIF packet or PIX data.
4. At the corresponding `0x10C3E0` entry (after
   `0x10DA20` calls resource checker `0x10D7C0`), capture the
   descriptor at `0x4FF8F0+(id-1)*0x30` and globals
   `0x4FF470/0x4FF474`. A RAM snapshot taken **before** resource
   residency checks may not reflect the record used by the writer.
5. Capture actual emitted GIF/DMA packets and GS register states near
   the affected draws to validate the conditional replay. The
   inspector cannot prove successful submission, override-free GS
   state, or the final screenshot from the descriptor alone.

The inspector supports a **direct low EE address-space** RAM image;
it does not guess mappings for aliased, mirrored, or compressed RAM
representations. Invalid or absent pointers/slots/descriptors
produce explicit unresolved or rejected results, not fake TEX1
values. Unverified filter selectors likewise never emit predicted
GS words. These are **preflight/replay** values, not a measured GS
command stream.

## Validation

`test_arika_menu_gs_correlation.py` covers:

- Synthetic matching sprite, resource-callback return, descriptor slot
  and exact reconstructed `TEX0/TEX1/CLAMP` values.
- Source resource pointer distinct from opcode-1 returned pointer.
- No ownership without observed callback returns; mismatched
  sampler values and callbacks never assert a match.
- Out-of-capture pointers, invalid descriptor IDs, native writer
  rejection, and unverified filtering indices.
- All four cache byte comparisons, resource pointer changes and
  unknown prior cache.
- JSON CLI round-trip with an asset-free synthetic EE RAM image.
- Optional full-hash-verified **original ELF** opcode checks for the
  binding/cache path and consumer's `+0x38` load.

No game executable, textures, fonts, screenshots or runtime asset
captures are checked into the repository.

## Remaining evidence boundary

The resource's concrete vtable +0x4C implementation, dynamically
allocated slot lifetime, active `TEX0/TEX1/CLAMP/TEXA/TEST/ALPHA/ZBUF`
per primitive and a live GIF capture remain unknown without additional
static callsite proof and/or PCSX2 observation. Static initializer
flags remain **initial flags**, not per-atlas sampling policies.
The Qt native and diagnostic renderers are intentionally unchanged.
