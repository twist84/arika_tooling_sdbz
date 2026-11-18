# EU-beta stage kind-6 control — original state masks and diagnostic preview

**Target executable:** Super Dragon Ball Z **EU beta** `SLES_541.61`, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`
(**not** European retail).

## Why this milestone

Stage sky/clear colours have already been solved by per-class original
ELF constants; they are not a PIX texture-border heuristic.
The next unresolved stage-editor behaviour is the game-owned **kind-6
runtime state control**, which holds primary and secondary named
descendant targets, a parameter index and a handler index. The stage
parser already recovers those names and resolves the original
first-depth-first match. Previously the scene editor showed both
geometries without a way to inspect their native initial state.

## Directly verified original EE behaviour

Original EU-beta instructions at **`0x00240290`** set up a
state control's primary/secondary object pointers (`+0x6C`, `+0x70`)
then change the **runtime object's `+0x28` flag word**:

| EE address | Original operation | Meaning |
|---|---|---|
| `0x002402B4` | `addiu v1,zero,-0x301` | Construct mask `~0x300` |
| `0x002402C0`, `0x002402C4` | `and`, `sw +0x28` | **Clear both bits `0x300` on the primary object** |
| `0x002402F4`, `0x002402F8` | `ori 0x300`, `sw +0x28` | **Set both bits `0x300` on the secondary object** |
| `0x00240864`–`0x0024087C` | load object `+0x28`, `andi 0x300`, conditional branch | An original native callback **skips further work** if both mask bits are already set |
| `0x00240750`, `0x00240788` | set primary, clear secondary | Separate native event path reverses the mask assignment |
| `0x00240A64`–`0x00240AA0` | clear primary, set secondary | Original reset/event path restores the initial mask pattern |

The instruction checker in `arika_native_stage_controls.py`
verifies **18 exact original machine words**, their original
addresses and the EU-beta executable SHA-256. This research does
not depend on an emulator trace. There are no original game files
committed.

These bits are real **runtime state flags**, not fields in
the authored STG header or per-node `flags` byte. Their full
consumption by PS2 rendering, collision, animation and destruction
systems has **not yet been proven**.

## New stage editor feature

**Viewport → Preview native stage initial state (kind 6)** is
an explicit opt-in *editor diagnostic*.

- Uses the existing parser's original first-depth-first named
  targets and only traverses live `EFFECT` and `STAGE` roots,
  excluding template-only controls.
- Reports primary `clear 0x300` and secondary
  `set 0x300` actions with exact source instruction locations.
- **For visual inspection only**, suppresses the secondary
  target and its descendants in the WebGPU viewport. This
  is an approximation of the native initial-state appearance,
  not a demonstrated PS2 visibility or destruction simulation.
- On ambiguous mappings (deleted/duplicated native glTF source
  objects, missing targets, or secondary roots overlapping a
  primary target) the affected subtree is **not hidden**.
- Maps source STG node indices into glTF by **original source
  byte offset, kind and name**. No match by unqualified
  texture or mesh name. Collision-wireframe clones are
  deliberately untouched because the native collision consumer
  needs separate verification.
- The effect is not stored in `.arika-scene.json`, exported glTF,
  or STG bytes. It does not change authored **Show/Hide** checkboxes
  or lock flags; turning it off restores the normal authored
  visibility filter. Undo/redo and project loading recompute it
  from the currently parsed original stage and edited glTF nodes.

## Reproduction

Run without an original executable or original stage assets:

```bash
cd arika-py_on_rs
python -m unittest test_arika_native_stage_controls -v
```

Run the exact-ELF oracle if the locally owned, exact
EU-beta ELF is available:

```bash
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 python -m unittest test_arika_native_stage_controls -v
```

Windows (PowerShell):

```powershell
$env:SDBZ_EU_BETA_ELF = "C:\\Games\\SDBZ_EU_BETA\\SLES_541.61"
python -m unittest test_arika_native_stage_controls -v
```

All ordinary tests, including the Qt opt-in toggle, run on both
Windows and Ubuntu CI using a tiny **synthetic kind-6 STG fixture**;
the original game ELF is intentionally optional.

## Evidence boundary / follow-up

This is **not** a complete native screen/state implementation.
Next investigate the consumers of runtime bits `0x100` and `0x200`
in GS submission, collision and the
`0x001BE040` object traversal, including when a node's own
flag word rather than its descendants gates work. Determine
whether mask propagation to child nodes agrees with the
editor's subtree-hidden visual approximation. Compare actual
PCSX2 stage screenshots in both initial and alternate states
before enabling automatic visibility by default.
