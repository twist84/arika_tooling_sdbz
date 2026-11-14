# Interactive main-menu logic in the Qt editor

This milestone connects the 2D preview to the seven-item navigation and
destination routing recovered from the supplied SLES_541.61 ELF. It is a
behavioural reconstruction of the *verified graph*, not a live game emulator.

## ELF sources and verified behaviour

- `CMenuMainMenu::input` at `0x00379C80` queries logical direction
  helpers, passes the selected logical direction to the current item's
  vtable dispatch at `0x00375270`, and processes the returned neighbour.
  The four tested direction masks are **8, 4, 1, 2** for IDs 0, 1, 2, 3.
- Item neighbour getters live in each item's vtable slots
  `+0x34 / +0x38 / +0x3c / +0x40`; `-1` rejects a movement.
- `0x00379F00` saves the previous/current index and invokes the new
  selection's entry callback. Entry callbacks set two *history-dependent*
  item-local flags (the distinct objects' `+0x710` and `+0x830` fields).
- When entering index 0 from previous index 2, direction 3 goes to item 2
  rather than item 1.
- At index 2 after arriving from index 0, 1 or 5, direction 0 goes to item 5
  rather than 6 and direction 1 goes to item 1 rather than 4.
- `0x003FE020` routes confirmed selections after the menu exits;
  cancel routes to app 3 without updating the mode-selector field.

See `research/main_menu_map.json` for the instruction-derived table values.
All seven items and all four directions are verified against this extraction
in `test_arika_menu_navigation.py`; the existing C++03 comparison independently
checks `arika_menu_logic.h`.

## Editor behaviour

The **Native graph** row in `arika_menu_editor.py` provides left/up/down/right
buttons, a selected-item history/route indicator, and **Confirm route** /
**Cancel route**. The canvas accepts arrow keys and Enter/Escape when focused
(click the canvas first). The Item dropdown remains available for direct
selection and correctly updates the selection-history state.

The directional key mapping **(Right -> 0, Left -> 1, Up -> 2, Down -> 3)**
follows the directional-bit mask convention, but a real controller trace has
not proved the physical assignment. Accordingly, the buttons display logical
ELF direction IDs in their tooltips. The original help text corresponding to
the selected index is shown below the canvas; item names are practical labels
inferred from the help text/art, not independently extracted text strings.

Confirm/cancel **inspect the route only**. They do not switch apps, write the
save game, or pretend to animate a native exit transition. The pre-generated frame slider and existing animation playback remain
independent of the **preview-only** selection emphasis event clock. Selecting
an item now triggers the recovered character/label emphasis displacement
samples (baked for relative ages 0–14 from ticks 80–94). The effect adds
sampled displacement to the live pose without replacing the global animation
frame. It works with playback paused, ends automatically, and is controlled
by the **Selection pulse (preview)** layer checkbox. The selection event as a
trigger and its clock rate are authored editor conventions, **not** a verified
native interruption or transition schedule. Unavailable neighbour moves preserve selection history.

The preview now requests repaint on its actual `c_menu_canvas` child whenever
a frame, item or layer changes. Previously it called `update()` only on the
editor container, which could leave the textured canvas visually stale.


## Arrow and help-box rendering (screenshot comparison)

The reference screenshots show each item with a bottom help frame containing
four lines and direction arrows that are part of the menu image, not external
Qt controls. The editor now draws the four original ELF-extracted strings in
its 512×448 canvas. The decorative frame, cloud accents, and font selection are
**temporary QPainter approximations**; native UVs/font rendering remain to be
recovered. The existing Qt help label is retained as an inspection aid.

Arrow UVs, base coordinates, and the history-dependent variants are taken from
`arrow_baselines` in `main_menu_map.json`. The visual bob is an authored
32-sample sine displacement (3 canvas pixels), not yet the original arrow
animation routine. The **Arrow bob (preview)** and **Help panel** checkboxes
allow individual visual comparison. No captured artwork or screenshots are
embedded in the repo; arrow sprites still load from the user's FPIX atlas.

## Validation and next research

```sh
cd arika-py_on_rs
python -m unittest test_arika_menu_navigation test_arika_menu_selection_effect test_arika_menu_arrow_preview test_arika_menu_editor_navigation -v
```

The CI matrix also runs these checks headlessly on Windows and Ubuntu. Native
gamepad repeat/debounce, native selection scheduling and interruption windows,
confirm/cancel effects, and application lifecycle are intentionally not
invented. The next ELF work should examine the input helper calls at
`0x00336430` through `0x00336480` and menu state fields `+0xC8` through
`+0xD5` in `0x00379B50` and `0x00379C80` before implementing real
timed transitions.
