# EU-beta texture filtering: engine opcode-1 binding and GS TEX1

Project: `twist84/arika_tooling_sdbz`, PR #14. Binary:
`SLES_541.61` with SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
All addresses below are MIPS EE virtual addresses; these findings were
checked against the original ELF words. No executable, screenshots or
texture assets have been committed.

## Confirmed path from the intermediate command buffer

The engine command dispatcher at `0x19B5C0` reads a packed opcode
from each command. Opcode **1** jumps to `0x19B688`. Its 12-byte
command layout includes:

| Command offset | Instruction | Meaning established by the trace |
| --- | --- | --- |
| +0 | `lhu` at `0x19B614` | opcode = 1 |
| +2 | — | separate selector, **not** used for filtering here |
| +4 | `lhu a1,4(s4)` at `0x19B688` | index into filtering flag table |
| +6 | `lbu v1,6(s4)` at `0x19B68C` | index into clamping flag table |
| +7 | — | another option, meaning unverified |
| +8 | `lw v0,8(s4)` at `0x19B6B4` | resource pointer; `lw a0,0x38(v0)` is passed to texture binder |

The two table bases are created using `gp - 0x7FA8` at
`0x19B690` and `gp - 0x7FA0` at `0x19B694`.
Their **file-backed** words are:

| Address | Table | Selector 0 | Selector 1 |
| --- | --- | ---: | ---: |
| `0x4F73C8` | Texture filtering | 0 | 1 |
| `0x4F73D0` | Texture clamping | 1 | 0 |

**There are only two verified entries per table.** An index
outside 0..1 is not interpreted in the Python recovery.
The two index fields may have different values; do not
treat the two tables as the same index or infer one from
the other.

At `0x19B6AC`, the interpreter calls `0x104820` with
the table results as a0/a1. That setter writes
`0x4FF470 = a0` and `0x4FF474 = a1`
via `sw` at `0x104824` and `0x10482C`. The locations are
runtime BSS, **not** recoverable final values from the ELF.
The interpreter calls `0x10DA20` immediately afterward at
`0x19B6B8`, using the resource handle extracted from +8.

`0x10DA20` (at `0x10DA80–0x10DA88`) supplies the current
`0x4FF470` and `0x4FF474` globals to `0x10C3E0`.
The latter tests the filter flag at `0x10C47C`, and emits
`GS TEX1_1 = 0x60` if nonzero, otherwise `0x00`
(at `0x10C484–0x10C48C`). The existing
`arika_menu_gs_texture.decode_tex1` therefore yields:

| Filter flag | TEX1, if submitted | MMAG | MMIN |
| ---: | ---: | ---: | ---: |
| 0 | `0x0` | 0 (nearest) | 0 (nearest) |
| 1 | `0x60` | 1 (linear) | 1 (linear) |

This reconstructed TEX1 is **conditional** on the
separate texture record being accepted by `0x10C3E0`.
The resource might be invalid or the state might be
overridden by a later command. These table lookups
identify exactly how the **engine chooses filtering
at a texture-binding command**, not the final active
hardware state in a saved screenshot.

## Implementation and reproducibility

- `arika_menu_gs_sampling.py` resolves the verified
  tables for captured native opcode-1 commands.
- `annotate_packet_sampling` propagates a known texture
  binding only up to an indirect opcode-0 callback.
  This conservative boundary matters because the callback
  at `0x19B658` dispatches a vtable function and may
  itself change GS state. Subsequent callbacks are
  unknown until a new binding appears.
- Opcode-8 resets the interpreter's *local* ten-byte
  context via `0x199500`; it does **not** itself call
  `0x104820`, so the last verified binding flags
  remain until an unexamined indirect callback.
- `test_arika_menu_gs_sampling.py` includes all four
  independent selector combinations, out-of-bounds
  cases, sequential binding/reset/callback tests,
  and an optional exact-ELF table/instruction oracle.
- The existing native packet inspector adds the
  `--resolve-sampling` flag:

```sh
cd arika-py_on_rs
python arika_menu_gs_packet.py captured-engine-commands.bin --resolve-sampling
```

The input is the **engine's intermediate command
buffer**, not `GAME.DAT`, `main_menu.pix`, or a
raw GIF/DMA packet. Unsupported or unobserved
selector values are emitted as **null**, not assigned
Qt filtering modes by default.

## Status and next capture dependency

What is now proven: selector field offsets, two
2-word lookup tables, the global flag setter, the
texture-binding call and the conditional `TEX1`
bit pattern.

**Not yet proven:** the actual binding commands
issued for each main-menu sprite, the 12-byte
resource selection's relationship to `dis/main_menu.pix`
atlas IDs, successfully bound runtime texture
descriptors, other GS state writes between draws,
and the active PCSX2 `TEX1` state. In particular, do
not assign every PIX atlas a nearest/linear mode
based on its atlas number or name.

The current Qt **Bilinear (PS2)** screenshot-comparison
preset remains a global *approximation*, not per-draw
GS state emulation. Apply a native per-sprite
filter only when a native command-buffer capture
and verified sprite/resource association support
that change. Screenshot edge differences do not
supply that association.

**Periodic review checklist:** confirm ELF
byte identity, inspect exact selector table bytes,
run both packet decoder and editor suites, inspect
new CI failures and review the PR diff before
treating each milestone as complete.
