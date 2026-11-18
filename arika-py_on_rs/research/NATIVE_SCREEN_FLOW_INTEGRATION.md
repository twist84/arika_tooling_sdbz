# Integrated EU-beta game-screen tour

This work composes the **existing** Arika Editor → Menu widgets. The
screens continue to use the original in-memory archive resources that the
editor already loaded once; no game texture is recreated or extracted.

## Goal

Provide one continuous *editor preview workflow* across the recovered
Warning / Video Mode, Startup / Splash, Title Screen, Press Start and Main
Menu previews, while retaining the distinct Demo Main inspector. This
does not conflate UI order with the original EE application's boot path.

The **Start screen tour** bar above the current tab hosts:
- Start/restart tour, Previous/Next preview, Step active and Play active;
- Main menu cancel back to the Press Start preview;
- status explaining which moves are manually chosen and which reflect
  independently verified native app requests.

All six tabs remain independently usable, including their original
per-screen input controls, visual viewers, native lifecycle state and
research diagnostics. No duplicate state-machine instance, secondary
asset archive, app-factory invocation or movie/GS emulator is created.

## Source of truth and route handling

Native factory IDs, top-level class names and instruction sites come from
`native_app_registry_eu_beta.json`, exposed via `arika_app_registry.py`,
and the existing per-app runtime modules. The complete exact-ELF map is in
`NATIVE_APP_REGISTRY_GRAPH.md`; screen roles are not class-name aliases.
The visible route mapping remains an editor-specific mapping onto tabs.

| Source | Original request | Integrated behaviour |
|---|---|---|
| Title (ID 2, `CAppCRISofdec`) | `0x3DFB00(6)` | Record Demo Main handoff; advance to owner-observed Press Start visible preview, preserving separate Demo Main inspector |
| Demo Main (ID 6) | Conditional native `0x3DFB00(this+0x2A)` at `0x3E09E0` | Default exit target is ID **3** (`CAppTitleMain`) after choice-1 child completion; choice 3 can instead set target **6**. The existing Press Start preview is available without claiming a factory ran |
| Press Start (ID 3) | Attract timeout `0x3DFB00(6)` | Open Demo Main inspector |
| Main Menu | Original cancel route ID **3** | Open Press Start preview when the diagnostic route is explicitly requested |
| Warning (ID 5, `CAppMonitorSelect`) | `0x3DFB00(1)` | Show Startup/Splash preview, recording native ID 1 (`CAppWarning`) request without executing its constructor |
| Press Start (ID 3) | Start `0x3DFB00(42)` | Show existing Main Menu preview; ID 42 is `CAppMenuMain`, not adjacent Shenron ID 43 |
| Logo (ID 4) | Update finished | Owner-observed handoff to Title preview; exact original next-factory callback remains unestablished |

`arika_screen_flow.py` is an asset-free route description with explicit
unsupported request results, and `arika_screen_flow_preview.py` owns a
single Qt tour controller around existing tabs.

**The owner's annotated 2026-11-18 screenshot establishes the intended
guided preview order** (the red numbers refer to visible screen order,
**not** native factory IDs):

1. Warning / Video Mode
2. Startup / Splash
3. Title Screen
4. Press Start
5. Main menu

Demo Main was annotated "idk": it remains a **separate inspector tab**
after those five, not a supposed sixth sequential game screen. The
existing six widgets are reordered **in place** using the Qt tab bar;
their runtimes, signal hookups, caches and archive references survive.

This is the **user-specified preview order, not a proven game's boot
order**. Start screen tour opens Warning; Previous/Next traverse only
the five numbered previews. They say "Manual preview jump" and do
**not** claim that the target game app was requested by the ELF.
Demo Main is reachable directly via its tab or via an independently
verified original native request, not by merely pressing Next after
one of the five screens.

When the original controller has an independently proven completed
transition, the common flow may change tabs automatically. A request is
not treated as proof the actual factory ran. In particular, title → demo
requires `title_handoff_request(result)` and the DemoMain inspector's
`accept_title_result(result)`; a synthetic or unfinished title result
cannot trigger that transition.

## Playback and user input

One flow timer advances only the *existing* logo, warning, title or Press
Start runtime with measured `QElapsedTimer` monotonic elapsed seconds;
it never creates a second state machine or substitutes a constant native
frame step. **Step active** uses a clearly diagnostic 1/60-second manual
delta. Existing per-screen input and busy flags are respected.

Pause boundaries:
- Warning option selection (the existing warning buttons remain active);
- Demo Main (its movie/child runtime is a diagnostic inspector, without
  a justified common 60 Hz update);
- Main Menu (its own recovered input/state controller remains separate);
- Completion with an unresolved next-app request;
- Direct tab switch, archive change, leaving the Menu workspace, and
  editor closure.

Explicit `Main menu cancel` uses the existing menu's verified cancel
graph; when its experimental native lifecycle is active, it only queues
the native cancel input and **does not** immediately assume a completed
app request.

## Shared archive lifecycle

`arika_editor.py` loads all six screen resource subsets from the same
`VirtualArchive`. The new tour bar is inserted above the existing tabs,
never reparents their canvases. Archive changes stop all clocks before
clearing old resources. The existing per-tab `load_archive_assets`
methods remain responsible for cache invalidation; selecting another
screen in a tour does not reload or duplicate the archive.

## Validation

`test_arika_screen_flow.py` covers all routes, manual-only boundaries,
title handoff integrity, verified Warning ID 1 and Press Start ID 42 requests,
attract return to DemoMain, main menu cancel, archive reset and timer
interruption. CI also compile-checks both flow modules and the exact-ELF verification tool; it runs deterministic assertions for all 47 IDs and 110 extracted helper callsites on Windows and Ubuntu.

This integration milestone intentionally does **not** block on perfect
copyright font, GS sampler/blend, prompt opacity or pixel-parity matching.
Those remain distinct, testable rendering improvements in the underlying
Press Start PR.

## Follow-up integration targets

The 47 factory identities and their original class-name getters are recovered,
including IDs 1 and 42. The **generic native scheduler** and DemoMain's conditional
ID 3/ID 6 exit field are now ELF-verified, as documented in
`NATIVE_APP_REGISTRY_GRAPH.md`. The existing Screen Flow annotates the ID 6 → 3
path as an **ELF-confirmed conditional request**, not a proven parent-stack
return or successful factory execution. The pure
`arika_native_app_lifecycle.py` inspector can evaluate the branch from
explicitly supplied prior-choice and active-child observations.
Remaining work includes real runtime branch acceptance, stack restoration,
per-class resource readiness/cleanup, and other dynamic call sites.
DemoMain's child/movie presentation remains an independent inspector.
Audio, GS rendering and an executable boot remain outside this UI
integration. Do not silently replace unresolved app IDs with a
hand-chosen next tab.
