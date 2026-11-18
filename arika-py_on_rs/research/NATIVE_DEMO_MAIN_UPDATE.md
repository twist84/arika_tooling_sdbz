# Original EU-beta CAppDemoMain update (factory ID 6)

## Exact executable and boundary

Source: **Super Dragon Ball Z EU beta** `SLES_541.61`,
SHA-256 `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.

Entry `0x003E0830` is the update function of the app constructed
by **factory 0x003F2C00 (ID 6)**. This is **not** the implementation
of the other class called `CAppDemoMain` registered as **ID 8**.

This result follows [NATIVE_APP_HANDOFF.md](NATIVE_APP_HANDOFF.md),
which establishes the title-to-ID-6 transition.
`arika_demo_main_update.py` is a deterministic projection of this
specific EE update function, with an exact binary/instruction oracle.
The original ELF and game assets are not committed.

## Verified application identities

| ID | Factory | Constructor | Vtable-name getter | Class string |
| ---: | --- | --- | --- | --- |
| 3 | `0x3F2D20` | `0x3F7150` | `0x3F86C0` → `0x4D7F90` | `CAppTitleMain` (alternate) |
| 6 | `0x3F2C00` | `0x3E03E0` | `0x3E0D10` → `0x4D52F0` | `CAppDemoMain` |
| 7 | `0x3F2BA0` | `0x3E1BD0` | `0x3E2080` → `0x4D5338` | `CAppDemoMovie` |
| 8 | `0x3F2B40` | `0x3E2160` | `0x3E26B0` → `0x4D5348` | `CAppDemoMain` |
| 9 | `0x3F2AE0` | `0x3E0DF0` | `0x3E1AE0` → `0x4D5310` | `CAppDemoPlay` |

ID 8's base/phase vtables are `0x4F5F30/0x4F5F58`,
while ID 9's are `0x4F5E70/0x4F5E98`.
The ID-6 vtables are `0x4F5E00/0x4F5E28`.

The duplicate `CAppDemoMain` class names are **in the original
ELF**, not an accidental registry alias. They identify separate
factory/constructor implementations and must not be conflated.
Likewise ID 3 is an alternate registered `CAppTitleMain` with
a distinct phase vtable (`0x4F6698`) from the ID-2 title
application. The ID-7 completion path thus returns to registered
ID **3**, not an unidentified application.

## Exact update state

The ID-6 constructor zeroes `this+0x28`, `+0x29`,
`+0x30` and other fields. Initialization at `0x3E0440`
sets `this+0x2A = 3`. Begin callback `0x3E07F0`
stores a game-helper pointer at `this+0x2C` and resets
`this+0x30=0`. The meaning of that pointer is not
inferred beyond the actually executed virtual callback.

| Offset | Meaning in the update |
| --- | --- |
| `this+0x28` | Current/previous child-choice index (0..3) |
| `this+0x29` | Next child-choice index (wraps modulo 4) |
| `this+0x2A` | Signed parent return application ID; initially 3 |
| `this+0x2C` | Pointer checked before the virtual `+0x18` callback |
| `this+0x30` | Update phase: 0 dispatch; 1 wait |
| `gp−0xFD4` | Game-global exit flag, read and cleared in the update |

The native flow at `0x3E0830..0x3E09F8` is:

1. If `this+0x2C` is non-null, call its vtable
   `+0x18` function (`0x3E084C..0x3E0858`).
   If phase is 0, dispatch the next child; if phase
   is 1, continue waiting.
2. Phase 0 without that pointer calls `0x3EB860(0)`.
   Both phase-0 entry paths copy `this+0x29` to
   `this+0x28`. This index selects a four-way child
   request through `0x3DFBD0(this,child_id)`.
   The next index increments mod 4, and the phase
   increments from 0 to 1.
3. **In the same update**, after the request, the code
   calls `0x3DFC60(this)`. A nonzero result means the
   child is still pending; phase 1 remains active.
   Subsequent phase-1 updates poll the same helper.
4. If `0x3DFC60` returns zero, the completed
   current-choice index controls the next action.
   Cases 0 and 2 just reset phase to 0. Case 1
   resets phase and sets the global exit flag.
   Case 3 resets phase, sets return app ID **6**,
   and sets the global exit flag.
5. On a nonzero global exit flag (including one set
   externally), the update runs `0x3EF140`,
   `0x3EF4D0`, conditionally clears the low bit
   of a child's flags if the `+0x2C` pointer exists,
   calls **`0x3DFB00(this, this+0x2A)`** and
   returns completion `1`. It clears the global
   exit flag on this path.

### Choice and completion table

| `this+0x28` | Request site | Child ID | Next `this+0x29` | On helper completion |
| ---: | --- | ---: | ---: | --- |
| 0 | `0x3E08B4` | 4 — LogoMain | 1 | Phase 0, continue |
| 1 | `0x3E08CC` | 7 — DemoMovie | 2 | Request parent **ID 3** |
| 2 | `0x3E08E4` | 8 — alternate DemoMain | 3 | Phase 0, continue |
| 3 | `0x3E08F4` | 9 — DemoPlay | 0 | Request parent **ID 6** |

The code sets the child-completion state on the **same**
update where a request is issued if `0x3DFC60`
already returns zero. No invented extra frame is added.

**Important:** the four choices are encoded in a native
state variable. The actual initial choice is 0; for
ordinary simulated completion of ID 7, the parent
requests ID 3 before reaching choices 2/3.
The **Set captured next choice** control deliberately
injects an observed `this+0x29` value at phase 0 to
inspect later cases, not a claimed normal in-game route.

The `0x3DFC60` routine derives its bool from
application fields (`this+0x12`, `this+0x08`).
The editor accepts that bool as **external observation**,
because it does not execute the app manager or child.
It also accepts the global exit flag separately.

## In-editor workflow

After pulling `master`, run `launch_editor.bat`,
open EU-beta `INFO.DAT`/`GAME.DAT`, then open
**Menu → Demo Main**. The original title-screen completion
still enables **Inspect destination (ID 6)**.

The Demo Main tab now has its existing resource-loader
and static child-inspection controls, plus a stateful
**CAppDemoMain update** section:

- **Step native update**, **Play/Pause** and **Reset update**
  for the `0x3E0830` state. Playback uses an **arbitrary
  100 ms Qt UI scheduler**, not a measured PS2 update rate.
- **Native child pointer exists**, **child still pending**
  and **Global exit signal** as explicitly supplied values.
  The global exit signal checkbox is consumed once per step.
- **Set captured next choice** to inspect a later-state
  observation only when the native phase is 0.
- Live phase/current/next counters, child identity/factory,
  number of requests, last recorded native calls and
  parent transition destination. **No calls are executed.**

Changing archives and leaving the tab stops autoplay;
archive replacement also resets any prior inspector state.
Neither movie decoding, graphics, audio nor real
application switching is claimed.

## Verification

```sh
cd arika-py_on_rs
python -m unittest test_arika_app_registry test_arika_demo_main_update test_arika_demo_main_preview -v
```

For exact user-owned original ELF checks, set
`SDBZ_EU_BETA_ELF` to the matching executable and
run the same tests. A hash-gated original-code oracle
checks the per-branch instruction words; the remaining
tests use synthetic state with explicit external observations.
Windows and Ubuntu CI run all non-proprietary tests.

**Remaining scope:** fully recover loader states beyond
the current bootstrap, identify the other ID-8
`CAppDemoMain` update behaviour and original graphics/
movie resources before adding actual frame rendering.
