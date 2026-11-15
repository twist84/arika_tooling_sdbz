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

## Source sprite initializers to opcode-1 binding (next static milestone)

The first direct sprite-to-binding link is **now proven**, with two
separate generic sprite paths. The sprite setter `0x2FD8F0` writes a
resource pointer at `sprite+0x44`, and four independent bytes at
`sprite+0x48/+0x49/+0x4A/+0x4B` (the last store is in its
`JR $ra` delay slot at `0x2FD904`). The draw-command producers
`0x2FD084–0x2FD094` and `0x2FDB68–0x2FDB78` load those four
bytes into `a2/a3/a4/a5` and call `0x2FE920` when the attached
resource is non-null. At `0x2FE974–0x2FE990`, that producer emits
a 12-byte opcode-1 intermediate command with the same four fields:

| Sprite byte | Engine opcode-1 offset | Interpretation in `0x19B688` |
| --- | --- | --- |
| +0x48 | +2 | separate native selector (not filter) |
| +0x49 | +4 | halfword filter selector: 0 nearest / 1 linear |
| +0x4A | +6 | byte clamp selector: 0 enables / 1 disables |
| +0x4B | +7 | additional option, unverified |

`0x2FE920` also caches the most recent resource/flags and can
elide a redundant binding. This means the constructor's four
literal arguments establish the sprite's **initial fields**, not
that every frame executes the opcode-1 packet or leaves GS state
unchanged.

### Four named constructor sites, each verified instruction-by-instruction

Each of the four direct JAL sites below sets
`a2=0, a3=1, a4=0` in the preceding three instructions and
`a5=0` in the JAL delay slot, i.e. **(0, 1, 0, 0)**.
The resource selectors are independently passed to `0x3725E0`
earlier in their constructors:

| JAL `0x2FD8F0` | Owner | Resource selector | Initial filter/clamp |
| --- | --- | ---: | --- |
| `0x376034` | shared tile owner sprite | 2 | linear / clamp enabled |
| `0x378434` | shared MAIN MENU banner sprite | 2 | linear / clamp enabled |
| `0x37A754` | DRAGON SUMMONING embedded sprite | 11 | linear / clamp enabled |
| `0x37BF0C` | main-menu help-panel sprite | 4 | linear / clamp enabled |

This is actual **constructor-site provenance**, not an assignment
from a texture's filename, alpha bounds or screenshot colours. It
does not prove the resource selector's runtime pointer is non-null,
that other draws reuse this object, or that a later setter/callback
has not changed the GS state.

### Broader code-region scan, strict unknowns

A SHA-256-gated offline scan of **direct** `JAL 0x2FD8F0`
within the EU-beta menu-code range `[0x370000,0x3B0000)`
found **77** matching call instructions. Only an *exact*
consecutive constant-argument signature (three instructions
before JAL and its delay slot) was classified:

| Class | Verified direct sites |
| --- | ---: |
| Literal (0,1,0,0): initial linear filtering | 59 |
| Literal (0,0,0,0): initial nearest filtering | 7 |
| Noncanonical/conditional argument setup: **unknown** | 11 |

The seven nearest-initialization JAL sites are
`0x370A6C`, `0x370B7C`, `0x370BE4`,
`0x370C08`, `0x37C56C`, `0x37C67C`,
and `0x37D8D0`. Some use dynamic resource pointers;
their PIX indices and draw-time GS state have **not**
been claimed or filled in.

The parser `arika_menu_gs_attachment.py` accepts a captured
sprite memory image through offset `+0x4B`. It reports the
native sampler fields and whether a non-null resource makes
opcode-1 submission **possible**, without fabricating a TEX1
write from an explicitly null pointer. The separate
`arika_menu_gs_attachment_elf.py` inventories the verified
literal direct-call sites using the user's **own** exact ELF:

```sh
cd arika-py_on_rs
python arika_menu_gs_attachment.py --static-menu
python arika_menu_gs_attachment.py captured_sprite.bin
python arika_menu_gs_attachment_elf.py path/to/SLES_541.61 --only-nearest
```

The first command lists only four named source-to-attachment
constructors, and the last scans the bounded code region. Neither
accepts archive filenames as a substitute for captured resource
pointers.

**Validation boundary:** The test modules include synthetic
snapshots, null-resource handling, standalone JSON CLI paths and
optional exact-ELF opcode/constructor checks. Native editor
filtering is **unchanged**: the data above is not a complete
per-draw/screenshot GS capture, and substituting inferred
per-atlas switches would erase that distinction. The next
step is to correlate a captured menu sprite instance and
opcode-1 resource pointer with its runtime texture descriptor
and active GS registers.
