# EU-beta native main-menu lifecycle: outer scheduler and exit controller

**Scope:** `SLES_541.61` (EU beta), SHA-256 `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`. All addresses below are EE virtual addresses. **No game binary or extracted artwork is committed.**

This is the first instruction-anchored checkpoint for [NATIVE_MENU_LIFECYCLE_PLAN.md](NATIVE_MENU_LIFECYCLE_PLAN.md). Crucially, **`0x00379B50` is not the enclosing per-frame update**: it is the `+0x4c` exit-completion callback of vtable `0x004F1C50`. The generic parent update is `0x00333920`; the menu's `+0x40` child update is `0x00379A40`. Reading `0x00379B50` as the entire menu scheduler loses the input, selection and entry/exit ordering.

## Binary mapping and constant provenance

ELF PT_LOAD: file offset `0x80`, load VA `0x00100000`, filesz `0x003FC900`; file location of an ELF-loaded address is `VA - 0x00100000 + 0x80`. ELF `.reginfo` gp value at file `0x003FC9EC` is **`0x004FF370`**. Consequently:

| MIPS load | ELF address | IEEE754 f32 | Meaning |
| --- | --- | --- | --- |
| `lwc1 $f0,-0x4CC4($gp)` at `0x00379C00` | `0x004FA6AC` | `10.0` | Exit substate 2 waiting threshold |
| `lwc1 $f0,-0x4CC0($gp)` at `0x0037A15C` | `0x004FA6B0` | `60.0` | Selection-audio cooldown threshold |

The previously authored example samples 23, 80 and 120 **do not** establish native entry, emphasis or exit triggers.

## Main-menu vtable evidence

The class constructor `0x0037A200` writes `0x004F1C50` as the main-menu vtable (at `0x0037A22C`). The table's populated function-pointer slots establish this direct dispatch graph:

| Slot | Target | Role / evidence |
| --- | --- | --- |
| +0x18 | `0x00333920` | Generic parent update; state at `this+0x14` |
| +0x1C | `0x00333AE0` | Generic render dispatcher |
| +0x30 | `0x00379960` | Entry setup, reset `+0xC8`, call `0x003782A0` |
| +0x34 | `0x00379970` | Entry-ready initialization: select index zero, start inner component |
| +0x38 | `0x003799B0` | Exit request (confirm/cancel dependent) |
| +0x40 | `0x00379A40` | Always-first per-frame child/selection update |
| +0x44 | `0x00379AF0` | Entry-readiness check via `0x00377FA0` |
| +0x48 | `0x00379C80` | Input processing (only in parent state 2) |
| +0x4C | `0x00379B50` | **Exit completion substate machine** (only in parent state 3) |
| +0x50 | `0x00379EF0` | Interactive draw callback (no-op) |
| +0x54 | `0x00379E60` | Menu draw: shared, selected/pending, inner |
| +0x5C | `0x00333DA0` | Controller selector |
| +0x70 | `0x00379F00` | Selection change and pending old item |
| +0x74 | `0x00379FF0` | Cancel: sound, begin base exit |
| +0x78 | `0x0037A0A0` | Confirm: set `+0xD5=1`, begin base exit, sound |
| +0x7C | `0x0037A120` | Entry notification/sound |
| +0x80 | `0x0037A140` | Selection sound, cooldown/flag gating |
| +0x84 | `0x0037A1C0` | Sound callback |

## Object fields (actual MIPS accesses)

Offsets are relative to main-menu `this`, **not** the nested shared component at `+0x20`.

| Offset | Storage | Evidence | Status |
| --- | --- | --- | --- |
| `+0x14` | s32 | `lw` at `0x00333930`, `sw` at `0x0033399C`, `0x003339BC`, `0x00333B8C`, `0x00333A14` | **Verified:** generic parent lifecycle 0..4 |
| `+0x20` | ptr | `lw` at `0x00379A54`, `0x00379B14` | **Verified:** shared scheduler/controller pointer |
| `+0x24..+0x3C` | seven ptrs | `lw +0x24($this+index*4)` at `0x00379DE8`, `0x00379F3C` | **Verified:** selectable item pointers |
| `+0x40` | inline object | vtable dispatch at `0x00379A8C`, `0x00379990` | **Verified:** nested component; subrole pending |
| `+0xC0` | s32 | `0x00379F14`, `0x00379F30`, `0x00379DE0` | **Verified:** current selection |
| `+0xC4` | s32 | `0x00379F24`, `0x00379A58`, `0x00379ADC` | **Verified:** pending **previous** selection, -1 when none |
| `+0xC8` | s32 | `0x00379B60`, `0x00379BC8`, `0x00379C4C` | **Verified:** exit substate 0,1,2,3,30 |
| `+0xCC` | f32 | `0x00379BE4`, `0x00379C04`, `0x00379C10` | **Verified:** exit substate-2 age; zeroed on entry to substate 2 |
| `+0xD0` | f32 | `0x00379D10`, `0x00379D38`, `0x00379F9C` | **Verified:** incremented by 1 with upper clamp 9999; resets on selection change; used by sound |
| `+0xD4` | u8 flags | `0x00379B30`, `0x00379D04`, `0x00379F8C`, `0x0037A148` | **Verified:** bit 0 sound latch; bit 1 sound played gating; **not** proven input lockout |
| `+0xD5` | u8 | `0x0037A0B8`, `0x003799BC` | **Verified:** confirm=1; zero/default selects cancel path (explicit zeroing on cancel still to be traced) |
| `+0xD8` | s32 | `0x0037A070` | **Verified:** selected controller 0 or 1 from `0x00336420` |

**Important:** `+0xD0` is **not** the duration of input repeat; the code visible here only uses it for the sound/cooldown path. Do not invent a repeat delay.

## Parent lifecycle: exact update order

`0x00333920` checks `+0x14==4` at `0x00333934` and returns immediately when finished. Otherwise **every update starts** by invoking vtable `+0x40` at `0x00333944..0x00333950`:

1. Call `0x00379A40`: shared update `0x00377DE0` **first** (`0x00379A50`); when `+0xC4>=0`, update pending previous-item arrow `0x00374FB0`, poll its completion `0x00375250`, and clear pending after `0x003782E0` (`0x00379ACC..0x00379AE0`). Then, if `+0xC0>=0`, update current arrow and nested `+0x40` component. Pending and current arrows may both tick on the same game update.
2. Inspect parent phase at `0x00333954`:
   - **0**: invoke `+0x30` setup (`0x00333988`); write phase **1** (`0x00333998`); **fall through** to readiness test in the same update.
   - **1**: invoke `+0x44` readiness (`0x003339A0`); if false remain 1. If true write **2** (`0x003339B8`), invoke `+0x34` (`0x003339C0`), **fall through** to input in the same update.
   - **2**: invoke `+0x48` input (`0x003339D0`). If its return is nonzero, call `0x00333B70` to begin exit at `0x003339E8`, then **fall through** to exit callback. In the current concrete `0x00379C80` all normal paths return 0, but it can begin exit *indirectly* via confirm/cancel handlers; do not synthesize an extra input-return transition.
   - **3**: invoke `+0x4C` (`0x00379B50`, at `0x003339F0`); if nonzero mark phase **4** (`0x00333A14`) and perform parent completion/route propagation. Otherwise remain in 3.
   - **4**: updates are suppressed.
3. Rendering is **not** done in this update: generic draw `0x00333AE0` invokes `+0x54` in all phases except 4 (`0x00333AFC..0x00333B08`); when phase 2 it also invokes `+0x50` (`0x00333B24..0x00333B30`). The actual `+0x54` draw is `0x00379E60`.

The base begin-exit helper `0x00333B70` writes parent state 3 at `0x00333B8C`, then calls menu `+0x38` `0x003799B0` (`0x00333B90..0x00333B9C`), unless already finished.

## Exit completion callback `0x00379B50` — branch-annotated transition table

The return value is **1 only once native exit is complete**; otherwise 0. One callback invocation occurs per parent update in phase 3, after the shared and arrow updates.

| Substate at `+0xC8` | Event/condition | Exact instruction/branch | Side effects, in order | Next substate | Return |
| --- | --- | --- | --- | --- | --- |
| 0 | first poll | `0x00379B8C -> 0x00379B9C` | `0x002C0C90`; `0x002C08A0(1,5,+1.0,-1.0)`; `C8++` at `0x00379BC4` | 1 | 0 |
| 1 | `0x002C0C20()!=0` | `0x00379BD0`, `0x00379BD8` | none after readiness query | 1 | 0 |
| 1 | `0x002C0C20()==0` | `0x00379BE0..0x00379BF0` | `CC=0.0f`, `C8++` | 2 | 0 |
| 2 | `float32(CC+1)<10.0` | `0x00379BF4..0x00379C10`, branch `0x00379C0C` | `CC=float32(CC+1)` in **FPU branch delay slot** | 2 | 0 |
| 2 | `float32(CC+1)>=10.0` | `0x00379C14..0x00379C20` | same `CC` increment/store; `C8++` | 3 | 0 |
| 3 | first poll | `0x00379C24..0x00379C4C` | `0x002C0C90`; `0x002C08A0(2,15,-1.0,-1.0)`; write `C8=30` | 30 | 0 |
| 30 | `0x002C0C20()!=0` | `0x00379C50..0x00379C5C` | none after readiness query | 30 | 0 |
| 30 | `0x002C0C20()==0` | `0x00379C60..0x00379C68` | none | 30 | **1** |
| other | unexpected value | `0x00379B94` | none | unchanged | 0 |

These are **logical update counts**; they do not establish seconds, frame rate or image-sample anchors. The `10.0` threshold was read from the ELF's own gp-derived constant, not selected to match a screenshot.

The start callback `0x003799B0` determines entry substate: it clears `+0xC8` first at `0x003799C8`; if `+0xD5==1`, it writes `+0xC8=30` at `0x00379A04`, requests selected-item exit `0x00375210` and shared exit `0x003782C0` before resetting `+0xCC`. On cancel (`D5==0`), it calls `0x00375230`, leaves `+0xC8=0`, resets `+0xCC`, and invokes the nested component callback. Both paths invoke the nested callback at `0x003799E4..0x003799F0`.

## Selection, input and call sites

- `0x00379F00`: at `0x00379F24` stores previous `+C0` to pending `+C4` **in the delay slot of the old-selection test**. If old selection was nonnegative, requests its exit via `0x00375210`. At `0x00379F30` writes the new `+C0`; for nonnegative new item, invokes `0x003751F0(new_item, old_index)` and vtable `+0x60`, preserving native history. Eventually clears `+D0` and sound flag bit1 per `0x00379F98..0x00379FA8`.
- `0x00379C80`: first probes controllers via `0x0037A040` which calls `0x00336420`; no qualifying controller leads to `+0x74` cancel (`0x00379CA0 -> 0x00379D58`). Otherwise the `0x00336430` mask-0x40 helper takes priority and invokes `+0x78` confirm (`0x00379CC4 -> 0x00379D70`); then directional helper priority is `0x00336450` mask1 (logical direction 2), `0x00336460` mask2 (direction 3), `0x00336480` mask8 (direction 0), `0x00336470` mask4 (direction 1). A valid neighbour returned by `0x00375270` is passed to `+0x70`. Invalid neighbour -1 does not change selection. Bit-level interpretation of these helpers (edge/repeat/hold) requires further tracing.
- Cancel callback `0x00379FF0` calls `0x00333B70` at `0x0037A00C`; confirm callback `0x0037A0A0` stores `D5=1` in the delay slot of its `0x00333B70` call at `0x0037A0B8`. Both cause parent phase 3 **without** relying on input's return value. App routing is downstream in `0x003FE020`, not part of the per-frame button decoder.
- Controller selector `+0xD8`: `0x0037A040` tries IDs 0 then 1 using `0x00336420` and stores the first qualifying ID at `0x0037A070`.
- Input helpers `0x00336420..0x00336600` and low-level pad state remain a **Phase 2** verification target; native repeat delay must not be inferred from Qt arrow key repeat.

## Known unknowns / next steps (explicit)

- **Unresolved:** exact physical pad button mapping, held-vs-pressed semantics and repeat/debounce in `0x00336420..0x00336600`; effect of simultaneous directions past verified priority; pad disconnect origin.
- **Unresolved:** full caller-chain beyond base/outer callbacks through app scheduler; app-global exit side effects; possible external mutations of `+0xD5` and nested components before start.
- **Unresolved:** independent native clock activation relative to entry and selected-item callbacks; per-item ages must **not** use the global diagnostic `m_time`.
- **Unresolved:** full downstream scene effects and GS screenshot agreement. Existing Qt editor, timeline, Match Pose, help panel and 4:3 layout must remain unchanged until a separately validated native runtime is introduced.

## Reproduce

Use `llvm-objdump -d --start-address=0x333920 --stop-address=0x333ba8 SLES_541.61` and `llvm-objdump -d --start-address=0x379960 --stop-address=0x37a1d8 SLES_541.61` against the **exact SHA** above, then inspect the `.reginfo` `ri_gp_value` (`0x004FF370`) and the two corresponding float32s. Compare direct function entries in vtable `0x004F1C50`; do not use US/Japan addresses interchangeably.

This checkpoint reconstructs the outer/exit dispatch and documents direct call sites. It does **not** claim that a complete native input oracle or a standalone end-to-end app simulation has already been validated.
