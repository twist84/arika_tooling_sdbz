# Native main-menu pad input and repeat decoder (EU beta)

ELF: `SLES_541.61` SHA256 `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`. The Phase 2 behavioral reconstruction is implemented in `arika_menu_input.py`; targeted synthetic byte-mask cases are in `test_arika_menu_input.py`. This note extends [NATIVE_MAIN_MENU_LIFECYCLE.md](NATIVE_MAIN_MENU_LIFECYCLE.md).

## Two different input mechanisms

`0x00336420`, `0x00336430`, `0x00336440` are tails into `0x00336490` with constant masks 0x80, 0x40, 0x20. `0x00336490` dispatches controller selector 2 across both controllers and calls `0x00336580`. That helper reads the **native pad halfword at +0x22** and returns whether the requested mask is set. In `0x0037A040` the 0x80 probe on controller IDs 0 and 1 sets menu `+0xD8` to the first qualifying controller; if neither qualifies, `0x00379C80` invokes the cancel handler at `0x00379D58`. **The physical meaning of pad+0x22 bit 0x80 (presence/status vs gameplay input) still needs producer-level validation; it is not labeled a Cancel button in code.**

`0x00336450` (mask 1), `0x00336460` (mask 2), `0x00336470` (mask 4) and `0x00336480` (mask 8) set `a2=a1` and jump to `0x00336510`. The menu caller at `0x00379CD0/0x00379D9C/0x00379DB4/0x00379DCC` sets `a1=1`. For a single controller this calls `0x00336600`, which reads input-aggregate **halfword +0x06**. With `a1=0` it would call `0x003365C0`, reading **halfword +0x04**. Selector 2 accesses aggregated halfwords at `0x005E7ABE` (edge, a1=1) or `0x005E7ABC` (edge OR repeat, a1=0). **The native main menu uses edges, not auto-repeat.**

## Native producer and exact repeat, `0x00336240`

The parent input preprocessor runs for both controllers; each controller owns a 12-byte record at `0x005E7AA0+index*12`.

| Offset | Evidence | Recovered role |
| --- | --- | --- |
| +0 | `0x003363C8..0x003363E4` | Count of continuous nonzero held-direction masks |
| +4 | `0x003362E4`, `0x003363EC`, `0x003365E0` | Press edges OR repeat pulses |
| +6 | `0x003362DC`, `0x00336620` | Press edges only |
| +8 | `0x003362A4`, `0x003362C0` | Previous/current analog-derived four-bit direction state |

Each update reads `pad+0x1E & 0xF` as **held** and `pad+0x22 & 0xF` as **pressed** (`0x00336290..0x003362A0`). `0x00336640` converts the native stick data into an analog direction mask, which is combined with held for the repeat counter and with *rising* analog directions (`new & ~previous`) for pressed edges. The separately emulated analog-mask input deliberately does not claim a recovered byte-to-axis calibration.

The repeat helper `0x003363C0` uses a counter per controller plus another aggregate counter:

| Condition | Branch | Counter change | Output +4 |
| --- | --- | --- | --- |
| no held directions | `0x003363C0 -> 0x003363F8` | set 0 | no repeat |
| held and `++counter < 20` | `0x003363D0 -> 0x00336400` | increment | edge only |
| held and `++counter >= 20` | `0x003363DC..0x003363F0` | subtract 4 | edge OR held-direction repeat |

Thus a continuously held direction produces extra repeat pulses on **logical updates 20,24,28,...** of a hold, but the main-menu's `a1=1` selector reads +6 and suppresses those pulses. No wall-clock timing or FPS inference is involved.

After the two controllers' masks are combined, `0x00336314..0x00336374` resolve simultaneous opposite directions separately for held and pressed: mask 1 wins over mask 2, and mask 4 wins over mask 8. Individual-controller edge queries read their own +6 record rather than this aggregate; selector 2 reads the aggregate.

## Menu dispatch priority and failure cases

The concrete `0x00379C80` call order is:

1. `0x0037A040` / `0x00336420` gate: if no qualifying controller, call `+0x74` cancel.
2. `0x00336430` with mask 0x40: if true, call `+0x78` confirm; this wins over directions.
3. `0x00336450` with mask 1: logical direction **2** (up).
4. `0x00336460` with mask 2: logical direction **3** (down).
5. `0x00336480` with mask 8: logical direction **0** (right).
6. `0x00336470` with mask 4: logical direction **1** (left).
7. Resolve neighbour via `0x00375270`; `-1` is a no-op, not a selection-change trigger. Valid neighbour invokes `0x00379F00`, preserving history and pending previous item.

Because the first successful direction wins, simultaneous orthogonal directions are **not** combined into a diagonal move. The native producer removes contradictory direction pairs in selector-2 aggregate mode first; for single-controller direct queries, the main-menu's up/down/right/left order still selects exactly one direction.

The `+0xD0` float counter is a *selection-audio delay* (GP-relative threshold `60.0f`, compare at `0x0037A160`) and is **not the pad repeat counter**. The menu's other flags `+0xD4` control sound latching/gating, not the native button-edge selection.

## Scope and remaining source questions

Synthetic tests exercise all masks and priorities, each 20/4 repeat boundary, analog rising edges, two-pad aggregation, opposite masks, and confirm/cancel gates without pretending to supply a gamepad stream. To establish actual controller semantics and end-to-end native parity, trace the upstream producer of pad `+0x1E/+0x22`, the sampling cadence of `0x00336240`, and stick conversion `0x00336640`; then compare interpreted ELF states after each update. The **Qt editor remains in diagnostic mode** pending full lifecycle validation. Do not infer an input delay from the 140-sample preview.
