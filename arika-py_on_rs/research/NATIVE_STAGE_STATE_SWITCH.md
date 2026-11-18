# EU-beta kind-6 stage state switch / restore audit

**Original game:** *Super Dragon Ball Z*, `SLES_541.61` **EU beta**, not EU retail.  
**Exact ELF SHA-256:** `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`  
**Prerequisite:** [initial kind-6 mask audit](NATIVE_STAGE_CONTROL_INITIAL_STATE.md)  
**Implementation:** `../arika_native_stage_state_switch.py`

## Distinct original native functions

The original game stores **runtime** flags (not STG asset bytes) at object
offset `+0x28`. A kind-6 control stores its primary target pointer at
`+0x6C`, its secondary pointer at `+0x70`, and its phase/status integer
at `+0x54`. The earlier audit recovered initial `0x300` mask assignment.
The new work independently checked **28 additional original EE opcodes**
against the exact beta ELF, on top of the 18 previous checked words.

| Original EE function | Conditions | Proven effect on object `+0x28` |
|---|---|---|
| `0x00240290` — initial setup | primary or secondary object pointer is nonzero | **Primary:** clear `0x300`; **secondary:** set `0x300` |
| `0x00240710` — phase-gated switch | the control's **`+0x54 == 1`** at `0x240720`–`0x240724` | **Primary:** set `0x300` at `0x240750`–`0x240754`; **secondary:** clear `0x300` at `0x240788`–`0x24078C`; increment control phase word at `0x240838`–`0x240840` |
| `0x00240910` — direct restore | invoked with non-null target pointers | **Primary:** clear `0x300` at `0x240940`–`0x240944`; **secondary:** set `0x300` at `0x240970`–`0x240974` |
| `0x002409F0` — event callback | original object's `+0x24` flag `0x08000000` set | enters a separate restoration branch, clearing primary at `0x240A64`–`0x240A70` and setting secondary at `0x240A9C`–`0x240AA0` |
| `0x002409F0` — other branch | bit `0x08000000` clear and bit `0x20` set in object `+0x24` | calls `0x1ABD30` or `0x1ABD70` with mask `0x10`, depending on the callback argument. **Neither helper is treated as a known rendering/collision/destruction mechanism** |

**Important:** Recovering a function, branch predicate, object flag mutation
or callback argument does not establish **whether or when that path ran**
in an actual game session. In particular, `0x240710` is not an
unconditional “stage destruction” switch. It acts only if the native
control's `+0x54` value is 1.

The `0x2409F0` callback is kept **separate** from the direct restore
routine. Its event gate is inspected independently through
`inspect_native_stage_event_callback()`. A caller and target object
must be observed before claiming an event restored a particular
stage; no such event is fabricated here.

## Editor implementation

The previously added **Viewport → Preview native stage state (kind 6)**
toggle now has a **Viewport → Native stage state scenario** submenu:

- **Initial — secondary suppressed:** uses static mask effects from
  `0x240290` (same behaviour as the previous preview).
- **Switched — assume original phase 1:** models the branch at
  `0x240710` *under the explicitly hypothetical assumption* that the
  control's `+0x54` is 1. The editor visually suppresses the primary
  target and exposes the secondary target.
- **Restored — direct helper outcome:** models the direct restore
  routine `0x240910`; its visual output normally matches the initial
  mode, although the callback provenance is distinct.

These three choices visualize **possible stage configurations**, not
timed animations or confirmed gameplay destruction. They do not
advance the game's phase counter, generate collision events, create
objects or execute native EE callbacks. The engine's actual meaning
of object bits `0x100` / `0x200` for GS and collision remains
unresolved. Suppression of a whole subtree is still a **conservative
editor-only visual approximation**.

A separate query, `inspect_native_stage_scenario(scene,
'switched', assumed_phase_word=...)`, **refuses to apply** the
switched outcome when the phase word is absent or is not exactly 1.
The Qt menu deliberately supplies a hypothetical phase word of 1
and always labels the result as such. This avoids incorrectly
presenting the branch as unconditional.

The same source-offset / kind / name mapping from the prior
implementation applies to every state: ambiguous, duplicated or
deleted nodes are **not** arbitrarily hidden. State conflicts are
detected before suppression. Authored Show/Hide remains a separate
visibility layer. Collision clone geometry, STG data, project
serialization and exported glTF are untouched. Disabling the preview
restores the authored viewport state.

## Reproduction and acceptance

Pure tests and optional Qt integration:

```sh
cd arika-py_on_rs
python -m unittest test_arika_native_stage_controls test_arika_native_stage_state_switch -v
```

An exact **original EU-beta ELF** oracle can be opted into locally
without distributing the executable:

```sh
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 python -m unittest test_arika_native_stage_state_switch -v
```

Acceptance criteria:

1. Previous 18 original opcode signatures plus **28 new** signatures
   match the exact EU-beta ELF, guarded by SHA-256.
2. Suppression for “switched” is refused unless the caller supplies
   `+0x54 == 1`; unspecified or other status values produce **no
   inferred switched visual outcome**.
3. Switched state reverses primary/secondary mask operations;
   direct restoration reverses them back.
4. Contradictory active/hidden targets and ambiguous glTF mappings
   never produce arbitrary object suppression.
5. Qt scenario choices alter only the effective *viewport* hidden
   set; project, STG and glTF content are unchanged.
6. Windows and Ubuntu CI runs all existing scene-editor and lifecycle
   suites alongside the new tests.

## Next evidence to collect

Trace the **callers and return conditions** of `0x240710`,
`0x240910` and `0x2409F0` during real gameplay. Capture
control `+0x54`, object `+0x24` and `+0x28`, original target
pointers, and GS/collision visibility **before and after** an actual
event. Only that can establish whether a particular state switch is
a destruction trigger, when it occurs, how it animates, and whether
the native renderer filters a parent or every descendant.

The preview is intentionally opt-in until the observed PS2
rendering and collision behaviour is known.
