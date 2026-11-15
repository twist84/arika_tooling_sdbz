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


## Display geometry (ELF verification)

See [NATIVE_VIDEO_DISPLAY.md](NATIVE_VIDEO_DISPLAY.md) for the inspected
EU beta, EU release, Japan and US graphics initializers. A common boot path
passes 640×448 to the GS configuration helper, while the menu's native
sprite/tile coordinates span 512×448. The physical television aspect
correction is not yet proven: the square 512×512 editor display is a
comparison presentation, not a recovered native aspect-ratio rule.

## Arrow and help-box rendering (screenshot comparison)

The reference screenshots show each item with a bottom help frame containing
four lines and direction arrows that are part of the menu image, not external
Qt controls. The editor draws the four original ELF-extracted strings in its
512×448 canvas through the existing native FFON decoder, using the archive's
`font/5-24-2.fon` automatically on archive load. Text rasterisation shares
`arika_ffon.render_text` with the Fonts panel; the temporary QPainter
frame and system-font substitutions have been removed. The native textbox is identified as **FPIX atlas entry 4** in
`research/TEXTURED_MENU.md` and now renders behind the font. Its **source crop
and final quad placement remain provisional**, not extracted native UVs.
The FFON text renderer now preserves word spacing (previously lost for
non-wrapped lines) and scales without distorting aspect ratio. Atlas 4 is
cropped to its nontransparent alpha bounds before being fitted to the
help-panel destination; stretching the entire 512x512 atlas compressed the
visible frame to a narrow strip. The game viewport and all sprite/text clips
are intersected so clouds and borders cannot leak into the Qt editor margins.
The recovered menu sprite coordinates and cloud helper use a **512×448
logical canvas**; the original screenshots are square 512×512 presentations.
The Qt renderer now scales X by the square-view fit and Y by an additional
512/448, rather than rewriting the underlying game coordinates. The original
tile at y=320–448 reaches the display bottom without a speculative +64 Y
offset. The help texture is currently at logical (30,272) sized 450×175,
with FFON text beginning at y=324 and advancing 25 pixels per line.
The 2026-11-14 4:3 reference/editor comparison measured the orange top
border slightly low and FFON letters slightly high. Their offsets have been
adjusted **independently** (frame -3, text +4 logical Y pixels), without
changing native geometry, glyph spacing, line lengths, or the 4:3 transform.
All four FFON lines share one scale derived from the longest line. The
reference and preview were captured at different animation moments, so a
single still image does not justify changing the recovered character poses.
These panel coordinates are screenshot-aligned, not yet recovered from the
native draw helper. Native exact frame draw geometry remains an open
reverse-engineering task. The existing Qt help
label remains an inspection aid.

Arrow UVs, base coordinates, and the history-dependent variants are taken from
`arrow_baselines` in `main_menu_map.json`. The arrow displacement function at **ELF 0x003753A0 is now recovered**:
it reads the component clock at +0xB0, computes fmod(age, 40.0), and calls
the game's linear interpolation helper 0x002C2C10 with keyframe times
(0, 10, 30, 40) and displacement values (0, +3, -3, 0). Its direction
cases add/subtract that displacement from X or Y, using the UV table
indexed by direction ID 0=right, 1=left, 2=up, 3=down. The keyframe table
and UV rectangles start at EU beta VA 0x004A9E60; the times are at
0x004A9E80 and values at 0x004A9E90. This corrects the original
preview-only 32-tick sine-wave approximation.

The same unique 64-byte UV+curve layout was found in all four inspected
ELFs: EU beta 0x004A9E60, EU final 0x004AD310, Japan 0x004AABF0,
USA 0x004AC380. The reproducible `elf_tooling/elf_menu_arrows.py` probe
identifies these data addresses without embedding an ELF or game assets.
Unit tests validate both keyframe interpolation and directional translation.

The arrow object's clock initialization and update are also traced:
`0x00374F38` clears `+0xB0` to float zero; `0x00374FC8–0x00374FF0`
increments it by float `1.0` during the active update and wraps ages
above `99999.0` by subtracting `99999.0` at
`0x003750DC–0x003750E4`. The displacement helper uses that stored age.

**Remaining limitation:** the editor currently feeds its preview sample
clock into the recovered displacement function, rather than reproducing
the full component activation lifecycle. The native clock's increment,
reset and wrap are verified, but the item's activation time relative
to a particular reference screenshot remains to be established.
Consequently the animation **shape, direction and period are native**,
while its initial displayed phase may still differ. The **Arrow bob (preview)** and **Help panel** checkboxes
allow individual visual comparison. No captured artwork or screenshots are
embedded in the repo; arrow sprites still load from the user's FPIX atlas.

## Visual reference-frame matching (4:3)

The editor now offers **Match pose...** and **Next match**. Select a
**cropped game-only 4:3** reference screenshot (no emulator/window chrome).
The diagnostic renderer compares samples 23–119 of the authored 140-frame
timeline at 512×384 TV presentation, then ranks the five closest samples
using color and edge differences within the central Cell/character region.
It downscales comparison images to 256×192, masks out most of the scrolling
cloud, banner and textbox, and uses the user-loaded game textures.

The tool restores the previous display mode, event emphasis age and timeline
after scoring, then seeks to the best candidate for manual inspection.
**Next match** cycles through the other top samples. Results are comparisons
of *preview* frame geometry, **not recovered in-game timestamps or proof of
native playback scheduling**. Screenshots taken at different stages of idle,
or with different filtering/blending, may produce ambiguous matches; a ranked
score cannot resolve those limitations.

No screenshots or copyrighted pixels are bundled into the repository.
The unit test generates synthetic images, and the Qt regression renders an
in-memory synthetic preview as the reference.

## Validation and next research

```sh
cd arika-py_on_rs
python -m unittest test_arika_menu_navigation test_arika_menu_selection_effect test_arika_menu_arrow_preview test_arika_ffon_spacing test_arika_menu_editor_navigation -v
```

The CI matrix also runs these checks headlessly on Windows and Ubuntu. Native
gamepad repeat/debounce, native selection scheduling and interruption windows,
confirm/cancel effects, and application lifecycle are intentionally not
invented. The next ELF work should examine the input helper calls at
`0x00336430` through `0x00336480` and menu state fields `+0xC8` through
`+0xD5` in `0x00379B50` and `0x00379C80` before implementing real
timed transitions.
