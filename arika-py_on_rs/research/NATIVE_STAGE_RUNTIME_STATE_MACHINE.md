# M4 — EU-beta native kind-6 state machine (evidence-bounded implementation)

**Target:** Super Dragon Ball Z **EU beta** `SLES_541.61`, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
This is not EU retail, and no game executable or assets are included.

## Implemented now

- `native_stage_kind6_transitions.json` records ten transitions and the
  evidence boundary for each, including opcode locations, field offsets,
  predicates, side effects, and unresolved requirements.
- `c_native_stage_state_runtime` models the proven constructor phase-zero
  result and initial target `0x300` mask writes; phase-1 gated switch
  (`0x240710`), phase increment, direct mask restoration (`0x240910`)
  and separately gated `0x2409F0` reset-mask callback.
- Controller state is independent. Target object flags, correctly, are
  **shared by target node** (not cloned per controller). Conflicting
  ownership and aliased primary/secondary targets cannot cause arbitrary
  visual suppression. The original unmodified bits outside `0x300` are
  preserved on every mask operation.
- The runtime is **RAM-only**, and the editor's WebGPU scene and Object
  View share the same diagnostic overlay. It uses the established exact
  STG source offset, kind, and name mapping and ignores collision clones.
- The existing Initial / Switched / Restored **manual scenarios remain**
  available; selecting them leaves runtime mode.
- Runtime menu: *Viewport → Native stage runtime (diagnostic)*. It
  exposes reset, a safe unresolved timer step, an explicit phase-ready
  injection, the phase-gated switch, direct restoration, explicit event
  reset-mask injection, and controller inspection.

## What each control proves

| Editor command | Modelled original instruction effect | Critical caveat |
|---|---|---|
| Reset controller state | `0x240C78` phase 0 + `0x240290` initial target masks | Editor reset, **not** an observed native reset event |
| Advance one frame | Nothing; an explicit unresolved result is returned | `0x2403D0` timer timebase and decrement conditions unproven |
| Inject phase-ready branch | `0x2404B0` writes phase 1 | Forcing the branch **outcome** does not recover its predicate |
| Invoke gated switch | `0x240724` gate `+0x54 == 1`; `0x240750`/`0x240788` mask writes; `0x240840` phase increment | Original vtable dispatcher and gameplay event unknown |
| Invoke direct restore | `0x240940`/`0x240970` mask writes | Original caller unknown; no inferred phase reset |
| Invoke event reset-mask | `0x240A04`/`0x240A08` event flag gate, `0x240A6C`/`0x240A9C` writes | Supplied synthetic event flags, not a known damage callback |
| Inspect | In-memory controller `+0x54`, `+0x5C`, `+0x60`, and target flag words | Diagnostic state, not a live EE object snapshot |

The separate `0x240860` timer/countdown reset assignments at `0x2408DC`
and `0x2408E0` are available in the Python runtime as
`reset_countdown_callback(..., diagnostic=True)`. The editor deliberately
does not auto-invoke that path.

## Evidence provenance and limitations

Existing exact ELF signature tables
(`arika_native_stage_controls.py` and
`arika_native_stage_state_switch.py`) check **56 instruction words and
one vtable pointer**. The JSON graph references these recorded words and
explicitly says no fresh executable reinspection or runtime trace took
place here. The full ELF was not available in this development session,
so **Batch 1's complete caller CFG and countdown predicate are not yet
claimed complete**.

There is no proven mapping of runtime `+0x28` bits `0x100` or `0x200`
to GS draw submission, collision activation, animation, or destruction.
The model's suppressed subtrees are **only a visual diagnostic
hypothesis**, just as in M2/M3. No collision mesh, authored Show/Hide,
STG bytes, exported glTF, serialization or project undo state is changed.

## Validation

Pure Python:

```sh
cd arika-py_on_rs
python -m unittest test_arika_native_stage_controls test_arika_native_stage_state_switch test_arika_native_stage_state_runtime -v
```

Optional exact EU-beta ELF recheck:

```sh
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 python -m unittest test_arika_native_stage_state_switch -v
```

The Windows and Ubuntu hybrid-editor CI workflow runs the new test suite
alongside existing scene, menu, animation, renderer, and lifecycle tests.
Optional Qt tests exercise nonpersistent overlay transitions.

## Next investigation

1. Obtain the exact hashed EU-beta ELF in a local analysis environment and
   disassemble `0x2403D0`–`0x2404B0` completely: recover the countdown
   source, decrement, timebase, conditional branches and scheduler caller.
2. Trace direct and virtual callers of `0x240710`, `0x240910`,
   `0x2409F0`, and `0x240860`; distinguish event types with actual
   argument provenance rather than naming them from proximity.
3. Trace *separate* readers of `0x100` and `0x200` around
   `0x1BE040`, GS submission and collision. Prove whether parent flags
   propagate, and whether collision follows the same rule as rendering.
4. Replace the explicitly unresolved clock/event hooks only after
   instruction-level evidence and tests exist. Native visibility and
   collision should remain opt-in until validated by runtime comparison.

**Status:** M4 evidence-bounded partial implementation; full native
destruction and timer reconstruction remains open.
