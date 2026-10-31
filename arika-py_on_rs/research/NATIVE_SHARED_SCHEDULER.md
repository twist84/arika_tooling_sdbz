# Shared-menu scheduler

Banner callbacks can now use the recovered implementation in `NATIVE_MENU_BANNER.md`. The `--banner` example mode enables that motion; the original no-op-child example remains available for comparison.

Report version 14 adds `shared_scheduler`; `arika_menu_shared.py` implements the shared controller's update, entry wait, staggered starts, overlay fade and exit wait. Banner and small-component animations are caller callbacks. The inner tile/companion owner can run through those callbacks using `arika_menu_owner.py`.

## Recovered order

Native update `0x00377DE0` returns immediately when shared phase +208 is zero. Otherwise it performs these actions in order:

1. Update banner (+256), then tile/companion owner (+384).
2. Update the seven small components in index order.
3. Run overlay fade `0x00377F40`.
4. Increment shared age +216, subtracting 99999 once only if the result is strictly greater than 99999.
5. Dispatch the shared phase callback from table `0x004F1C10`: entry `0x00377FB0`, active `0x003780E0`, exit `0x003780F0`.

All three phase fields are distinct: phase +208, subphase +212 and float age +216. The started count at +220 is initialized to zero, but is not cleared by phase transitions or the exit request. Overlay-hidden byte +224 starts at 1; setup `0x00377A70` writes overlay alpha +172 to zero. The scheduler initialization helper models these fields and zero small phases, without allocating or configuring GPU sprites.

## Entry sequence

Entry subphase 0 starts the banner then inner owner and advances to subphase 1. The children have already received their update for that pass, so the newly started owner performs its entry callback on the following shared update. Its first timer/spawn callback follows one pass later. Under the example's explicit shared start at sample zero, the first event RNG input occurs at sample 2.

Subphase 1 checks each small component after its update. A component starts only when its phase is zero and shared age meets its threshold. Starting sets its phase to 1, invokes the caller's start callback, and increments the shared count. Thresholds from `0x004A9F80` are:

| Component | Shared age threshold | Example sample |
|---:|---:|---:|
| 0 | 10 | 9 |
| 1 | 30 | 29 |
| 2 | 40 | 39 |
| 3 | 20 | 19 |
| 4 | 25 | 24 |
| 5 | 35 | 34 |
| 6 | 15 | 14 |

The count is a count of starts, not an independent set of seven completion flags. If a caller makes an already-started component inactive again, the native scheduler can start/count it again. The implementation preserves that rule instead of inventing a deduplication guard.

After count reaches seven, entry subphase becomes 2 and age resets to zero. After a further 15 updates (GP-19712), the overlay-hidden byte clears, alpha resets to zero, and shared phase becomes 2 with subphase/age zero. The active callback returns zero, so it does not automatically trigger exit.

## Fade and exit

Fade runs before phase dispatch. When the overlay is enabled and alpha is below the target 0.5 (GP-19708), it adds float32(0.1 * 0.5), clamping an overshoot to 0.5. Entry therefore enables the overlay at alpha zero; its first fade increment occurs on the next pass. Alpha already at or above the target is left unchanged, as is alpha while the overlay is hidden.

Exit request `0x003782C0` writes phase 3, subphase 0 and age zero. The first exit callback starts banner exit and advances subphase. Once age reaches 10, shared phase/subphase/age become zero. Child updates and fade still run on that final pass. The request neither resets the count nor calls inner-owner exit; when shared updates stop, the inner owner's phase can remain 2 while its updates are frozen. No separate inner exit trigger is inferred.

This update gate does not determine whether an independent draw call occurs. Existing shared draw order and overlay draw gating are documented in `MENU_LAYERS.md`; final visibility/depth compositing remains unresolved.

## API and reproducible example

`step_shared(state, kernel, child)` invokes `child(role, index)` for updates/starts and returns the ordered call list. Child update callbacks can mutate `state['small_phases']` before entry readiness checks. The caller owns banner/small animation data and the actual outer activation moment. `request_exit(state)` models the verified exit request. Initialization leaves phase zero; choosing phase 1 is an explicit diagnostic activation, not a newly recovered outer-menu call.

```sh
python examples/menu_shared_schedule.py examples/menu_shared_schedule_trace.json
```

This example starts shared phase 1 before sample zero, uses native RNG seed 1, runs the recovered inner owner, and requests shared exit at sample 120. Banner/small animation callbacks are explicitly no-ops; scheduler writes to their phase flags remain. These choices are recorded in the JSON's limits. The trace runs 140 samples. The shared controller stops at sample 129; later samples confirm that the inner owner remains active but frozen. `previews/menu_shared_schedule.svg` visualizes phase transitions, small starts and overlay alpha. Its horizontal axis is diagnostic update samples, not native elapsed time.

## Validation and scope

All 65 menu tests pass. New checks compare 600 controlled shared updates against the extracted native instructions, including callback order, child readiness changes, phases/subphases, counter changes, age wrap and fade boundaries. The native shared update, fade and phase callbacks execute directly in the scalar interpreter. Banner/owner/small operations and small readiness queries are controlled stubs in these comparisons; this does not validate unresolved child animation curves.

A 70-update entry/fade sequence verifies every staggered start and the additional wait. Other cases cover busy children, readiness changing during child updates, exit-request writes, the ten-update exit and the inactive freeze. The example separately integrates the previously verified inner owner. The interpreter gained byte stores and direct calls into loaded function words; the entire existing menu suite still passes.

The timeline was rendered for visual inspection. Outer menu activation timing, banner/small animation curves, textures, viewport clipping, full compositing and captured global RNG ordering remain pending. Arithmetic uses host float32 and does not establish PS2 hardware bit accuracy.
