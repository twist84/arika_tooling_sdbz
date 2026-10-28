# Main-menu item overlays and shared layers

This pass extends the supported-build ELF report to version 4. `arika_menu_layout.py` still produces diagnostic diagrams, now including the third component group's seven item overlays in addition to the middle group's 38 sprite parts. See `MENU_LAYOUT.md` for commands and the earlier geometry research.

`arika_menu_layers.py` recovers literal resource and rectangle arguments from native setup instructions. It follows direct local jumps, processes call delay slots, and invalidates caller-saved registers after calls. It does not emulate called functions. Conditional branches, unknown arguments, unsupported instructions and loops are rejected. This is a bounded setup extractor for the supported build, not a general R5900 interpreter.

Seventeen menu tests pass. Added cases check call delay slots, caller-saved register invalidation, direct jumps, loop rejection, and preservation of an unresolved runtime position. No native runtime/rendering comparison is claimed.

## Item overlay sprites

All seven use resource entry 2, centered anchor mode 0, zero rotation, and a depth bias of 25. Each draw routine adds its component's animation X/Y offset to the base below. The diagrams use zero animation offsets. These sprites' exact visible labels still require matching against the native textures.

| Item | Setup | Draw | UV X,Y,W,H | Base X,Y |
|---:|---|---|---|---|
| 0 | `0x0037E960` | `0x0037E8C0` | 0, 0, 256, 64 | 156, 204 |
| 1 | `0x0037EC80` | `0x0037EBE0` | 0, 64, 280, 64 | 248, 256 |
| 2 | `0x0037EFA0` | `0x0037EF00` | 280, 64, 200, 63 | 390, 64 |
| 3 | `0x0037EAF0` | `0x0037EA50` | 296, 128, 216, 72 | 388, 240 |
| 4 | `0x0037EE10` | `0x0037ED70` | 0, 128, 280, 64 | 156, 140 |
| 5 | `0x0037E640` | `0x0037E5A0` | 0, 192, 288, 63 | 336, 90 |
| 6 | `0x0037E7D0` | `0x0037E730` | 256, 0, 240, 64 | 372, 240 |

The report keeps the literal-argument callsite address for every rectangle and resource lookup. `composite_layout.layers.item_overlays` contains the source metadata; each diagram composite's `item_overlay.zero_offset_pose` contains its diagnostic quad.

## Shared setup and draw structure

Shared initialization `0x00377A10` calls the base setup, shared banner setup, tiled-element setup, and seven-small-component constructor. The latter is another function incorrectly decompiled as an infinite allocation loop; the report records the seven items used by the caller but does not emulate their lifecycle.

| Role | Setup | Resource entry | UV X,Y,W,H |
|---|---|---:|---|
| Base background | `0x00377A70` | 1 | 0, 0, 512, 448 |
| Conditional overlay | `0x00377A70` | 8 | 60, 120, 1, 1 |
| Shared banner | `0x003783C0` | 2 | 0, 256, 264, 48 |
| Tiled element | `0x00375FE0` | 2 | 0, 384, 512, 128 |

The conditional overlay scales its one-pixel source to 512 by 448. Its draw is gated by shared-object byte +224 being zero. Its initial alpha and subsequent fade are controlled elsewhere; the tool does not turn it into an always-visible opaque rectangle.

The shared draw routine `0x00378170` calls the background sprite, banner, tiled element (two draws), seven small components (each state-gated), then the conditional overlay. The outer menu draw `0x00379E60` calls shared drawing, the previous item if its index is valid, the current item if valid, and the embedded menu component at +64. **These are call sequences, not a recovered final depth/compositing order.**

The shared sprites are constructed as the plain sprite type, whose draw path differs from the 38-part and seven-overlay component sprite type. This update records their UV setups and draw structure without exporting guessed shared-screen quads.

## Seven small shared components

Each uses resource entry 3. Six base positions are file-backed constants. Component 2 reads `0x004FDC50`, outside file bytes but inside verified startup zero-fill. It now exports initial position (0, 0) with `base_source: startup_zero_fill`. See `MENU_STARTUP.md`; subsequent runtime writes are not captured.

The small components have state and animation offsets, so their setup rectangles alone do not establish which are visible in any one frame. Together with the four shared setup rectangles and seven item overlays, this pass records 18 new rectangle calls. Only the seven item-overlay quads are added to the geometry diagrams.

## Remaining work

First-group setup data is now extracted in `MENU_FIRST_COMPONENTS.md`: literal sprites, scaled decorations, scrolling strips and particle templates. Its geometry/effect playback remains incomplete. Native animation curves, runtime position initialization, visibility gates, texture sampling and final compositing order also remain. The diagrams therefore show 45 diagnostic quads, not a complete menu reconstruction.
