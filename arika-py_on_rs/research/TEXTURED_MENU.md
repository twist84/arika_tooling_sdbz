# Textured menu lab

Open `previews/menu_textured.html` in a browser. It is self-contained, works offline and embeds all thirteen original menu atlases as PNGs. No game installation, server or external CDN is required to view it.

The viewer offers all seven selected-item startup poses, a shared-animation scrubber/play button, independent scenery/character/label and shared-layer toggles, atlas inspection, optional quad outlines, nearest/smooth sampling and PNG export. It starts at settled diagnostic sample 70. The seven item texture labels read ORIGINAL, Z SURVIVOR, VERSUS, DRAGON SUMMONING, TRAINING, CUSTOMIZE and OPTIONS.

Label entry/exit motion is now enabled by default; use the Recovered label motion checkbox to compare the static pose. See `NATIVE_ITEM_LABELS.md`.

## Selected-scene sky correction

The close-up comparison exposed a second issue: the original textured viewer omitted the selected first-group scroll strips. In ORIGINAL, the selected stage sprite has transparent sky pixels that must reveal its own rotated sky strip, not the dimmed small-panel layer. `arika_menu_textured.py` now uses the existing verified strip clipping and rotated-quad ports for items 0, 2, 4 and 6, rendering those textured quads with the item scenery. This restores the bright selected sky and removes panel seams showing through it.

Strip phase advances with the diagnostic sample index; motion offsets are zero and component depth starts at 45, while each successive emitted strip piece increments its depth. The ORIGINAL native first-group draw was independently interpreted with component depth 45 and its strip-call F12 depth captured as 45. This is still an authored preview schedule rather than captured item callback timing. Existing native strip/rotation tests pass, and the actual Canvas renderer now checks opaque sky coverage at (180,2) with only selected scenery enabled. All 76 menu tests pass.

## Reference-layout correction

The supplied native ORIGINAL-menu screenshot exposed incorrect painter ordering in the first preview. The renderer now queues shared and selected-item sprites together and paints by increasing depth, preserving emission order for equal depths. This places the MAIN MENU banner over the small panels, character wings behind the torso/arms, and cloud tiles over lower item geometry. Navigation arrows are restored from native placement callbacks. Bottom help text/panel are intentionally omitted for this comparison.

Depth baselines: background 0; small panels 5; overlay 10; selected scenery 47 (active component 45 plus literal bias 2); character parts 60 plus per-part depth; label 70 (40 on exit); tiles 85; arrows 95; banner 99. Selected-item component depth 45 is the active/entry baseline, not the previous zero-component-depth diagram. The first-group 47 baseline is used for the preview group; per-decoration/effect ordering and full native GPU blending remain outside this fix.

The ORIGINAL layout was rendered and visually checked against the reference, ignoring its bottom help text. Canvas validation includes a pixel-level regression proving that later low-depth geometry cannot overwrite an earlier high-depth sprite. Native arrow tests check 14 layouts (seven items, both conditional-flag variants). The preview chooses flag zero and zero arrow bob displacement. All 76 menu tests pass.

Whole-character entry/exit is now enabled by default; see `NATIVE_ITEM_CHARACTERS.md`. Individual part idle offsets remain zero.

Per-part idle motion is now enabled for items 0, 1 and 4; see `NATIVE_CHARACTER_IDLE.md`. The idle toggle restores zero part offsets for reference-layout comparison.

CUSTOMIZE now adds a coupled two-clock idle callback; four items have verified per-part idle. See `NATIVE_CUSTOMIZE_IDLE.md` for its explicit secondary-clock initialization choice.

VERSUS now adds a verified nine-part idle callback, bringing idle support to five items. See `NATIVE_VERSUS_IDLE.md`; OPTIONS and DRAGON SUMMONING idle remain pending.

OPTIONS circular idle is now enabled, bringing idle support to six items. Its sine/cosine use host math rather than an emulation of native libm; see `NATIVE_OPTIONS_IDLE.md`.

All seven items now have per-part idle motion. DRAGON SUMMONING combines two circles and an eight-case sway pattern; both it and OPTIONS retain host-trig limits. See `NATIVE_DRAGON_IDLE.md`.

Common label/character emphasis is now available through Play shake, with an authored sample-80 trigger. See `NATIVE_ITEM_EMPHASIS.md` for persistent phase-3 behavior and validation scope.

## Source and mapping

Textures come from `dis/main_menu.pix`, entry 235 in the supplied INFO index, sector 22356, size 3,228,404. The asset was read from the original supplied GAME.DAT archive. Its SHA-256 is `b5bef7fb13ccb4cd7f1e0cb005a29c623b166244c2b51ad559e09c1a1ad4e991`.

The FPIX has thirteen XPIX/TIM2 chunks. Chunk 0 is 256 by 256; chunks 1–12 are 512 by 512. The viewer maps FPIX chunk order to researched resource-entry indices; decoded atlas contents and recovered source rectangles were visually checked against all seven assembled items. This mapping produces coherent labels, character assemblies and scenery. It does not claim full runtime resource-manager/GPU emulation. Per-entry source hashes/dimensions are recorded in `research/menu_textures.json` and the embedded payload.

| Entry | Decoded content |
|---:|---|
| 0 | UI controls, arrows and prompts |
| 1 | Shared turquoise background |
| 2 | Item labels, MAIN MENU banner and clouds |
| 3 | Seven shared small location panels |
| 4 | Framed text panel |
| 5–7 | Character part atlases |
| 8 | Options character/scenery and overlay sample |
| 9–12 | Selected-item scenery/effects |

The existing TIM2 decoder handles indexed palettes and expands PS2 alpha 0–128 to 0–255. Textures retain transparent pixels. The canvas renderer uses each recovered quad's UV endpoints and vertices, including reversed axes, and clips rendering to the 512 by 448 viewport. No generated or substitute artwork is used.

## Rebuild

```sh
python arika_menu_textured.py main_menu.pix research/main_menu_map.json examples/menu_shared_children_trace.json previews/menu_textured.html
```

The generator is standard-library Python and uses the existing container/TIM2 decoder. Its adjacent `arika_menu_textured.html` is the reusable template; the generated preview embeds the payload. Input paths and output must differ. The trace must contain banner and small-component motion, with the same ELF hash as the report; the texture-entry count must match the report.

## Composition and limits

Shared rendering follows the recovered call sequence: background, banner, two tiled copies, active small components, then the conditional overlay with its recovered fade alpha. The selected item then draws its static first-group scenery, middle character parts and label. The queued painter order now follows recovered depth baselines; this remains a diagnostic approximation of the game's final GPU compositing system. Selection only changes the selected pose; it does not reproduce transitions, native input gating, character part animation, unrecovered strip callback timing, particles, text descriptions or previous-item overlap. The preview does not draw companion pool sprites; the shared cloud tiles do animate.

The shared trace retains its authored initial activation, seed, sample-120 exit request and 60-samples/s display rate. Scenery startup offsets and individual character-part idle offsets remain zero; whole-character entry/exit is recovered. Label entry/exit visibility is recovered; its activation schedule is authored. Canvas filtering/blending are approximations to native GPU behavior; PS2 per-pixel depth, vertex colors, blend equations and texture sampling are not emulated. The atlas view and layer toggles expose source assets separately when diagnosing those remaining differences.

## Validation

The thirteen atlases decoded successfully and a contact sheet was visually inspected. All seven textured item assemblies were rendered and inspected. `validate_menu_textured.js` executes the delivered HTML's actual JavaScript with a real `@napi-rs/canvas` backend and minimal DOM stubs. It checks all thirteen atlas views, all seven item views, shared timeline endpoints, layer isolation, and pixel-exact flipped U/V affine placement using a four-color fixture. These checks pass. The actual JavaScript renderer produced `previews/menu_textured.png`.

```sh
node validate_menu_textured.js previews/menu_textured.html screenshot.png
```

That optional validator requires `@napi-rs/canvas`; the delivered HTML does not. Browser layout, interactive playback and PNG download behavior could not be tested in a full browser here because its executable was unavailable and downloading it failed. The existing 72 menu tests still pass. The canvas rendering and embedded asset loading were tested directly, rather than claiming a browser test passed.
