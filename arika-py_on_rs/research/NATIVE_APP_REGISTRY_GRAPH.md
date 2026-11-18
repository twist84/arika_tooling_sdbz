# EU-beta native application registry and interaction graph

**Target:** Super Dragon Ball Z **EU beta**, original executable `SLES_541.61` (not EU retail)  
**SHA-256:** `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`  
**Registry:** [native_app_registry_eu_beta.json](native_app_registry_eu_beta.json)  
**Graph:** [native_app_interactions_eu_beta.dot](native_app_interactions_eu_beta.dot)  
**Oracle:** `../arika_native_app_extract.py`

## Findings and evidence boundary

The exact game executable registers **47 separate native application IDs 1–47** at `0x003F1580` using registration helper `0x003DFA60`. Factories are stored by ID in the BSS table `0x006217E0 + 4*ID` (not by registration position). The instance-provider helper conventionally labelled **factory lookup** is `0x003F1C40`: it calls a BSS factory with `jalr` and returns the resulting pointer, rather than merely reading a function pointer. The extracted factory addresses, constructor JAL sites, class strings reached through each constructor's base vtable, and both top-level vtable pairs are individually represented in the JSON. The table below uses **ID order**; its Order column preserves the **original nonnumeric registration order**.

Across the exact ELF there are **110 direct helper calls**: **41** transition requests to `0x003DFB00`, **32** child requests to `0x003DFBD0`, and **37** factory lookups to `0x003F1C40`. **67** of the 73 transition/child calls have statically resolved *registered* destination IDs. These are **callsites, not unique executable transitions**. The 37 factory-provider calls are distinct from the 73 application requests: a provider **can call** a factory, but whether the factory allocates an object, returns a cached instance, or runs in an observed session remains separate evidence.

**Critical identity correction:** ID **2** is `CAppCRISofdec`; ID **3** is `CAppTitleMain`. ID **5** is `CAppMonitorSelect`; ID **1** is `CAppWarning`. Previous screen-widget labels are roles, not interchangeable class names. ID **42** is `CAppMenuMain`; ID **43** is `CAppShenronMain`. The native strings for IDs 6/8 (both `CAppDemoMain`) and IDs 12/13 (both `CAppSelectWorld`) are duplicates, but their factories, constructors and vtable pairs are distinct. `CCardDemo` is a helper class and is not a registered app ID.

## Native application families

- **Boot, logo, title and monitor:** application IDs 1–5
- **Demo and attract:** application IDs 6–9
- **Character / world selection:** application IDs 10–13
- **Fight and gameplay lifecycle:** application IDs 14–27
- **Results and score progression:** application IDs 28–38
- **Endings and game-over:** application IDs 39–41
- **Menus, Shenron and Dragon Mission:** application IDs 42–45
- **Options / rankings:** application IDs 46–47

Family grouping is for research/navigation and does not imply a parent ownership hierarchy.

## Complete application table (47 unique native IDs)

| ID | Order | Factory | Constructor | Base vtable | Phase vtable | Class getter | ELF string address | Original class string |
|---:|---:|---|---|---|---|---|---|---|
| 1 | 1 | `0x003F2DE0` | `0x003FA9A0` | `0x004F6860` | `0x004F6888` | `0x003FAED0` | `0x004D8518` | `CAppWarning` |
| 2 | 2 | `0x003F2D80` | `0x003F86E0` | `0x004F66D0` | `0x004F66F8` | `0x003F8AB0` | `0x004D7FA0` | `CAppCRISofdec` |
| 3 | 3 | `0x003F2D20` | `0x003F7150` | `0x004F6670` | `0x004F6698` | `0x003F86C0` | `0x004D7F90` | `CAppTitleMain` |
| 4 | 4 | `0x003F2CC0` | `0x0041E620` | `0x004F7250` | `0x004F7278` | `0x0041EC80` | `0x004D91F8` | `CAppLogoMain` |
| 5 | 5 | `0x003F2C60` | `0x0041ECA0` | `0x004F72B0` | `0x004F72D8` | `0x0041F580` | `0x004D9210` | `CAppMonitorSelect` |
| 6 | 6 | `0x003F2C00` | `0x003E03E0` | `0x004F5E00` | `0x004F5E28` | `0x003E0D10` | `0x004D52F0` | `CAppDemoMain` |
| 7 | 7 | `0x003F2BA0` | `0x003E1BD0` | `0x004F5ED0` | `0x004F5EF8` | `0x003E2080` | `0x004D5338` | `CAppDemoMovie` |
| 8 | 8 | `0x003F2B40` | `0x003E2160` | `0x004F5F30` | `0x004F5F58` | `0x003E26B0` | `0x004D5348` | `CAppDemoMain` |
| 9 | 9 | `0x003F2AE0` | `0x003E0DF0` | `0x004F5E70` | `0x004F5E98` | `0x003E1AE0` | `0x004D5310` | `CAppDemoPlay` |
| 10 | 10 | `0x003F2A80` | `0x003F5620` | `0x004F6550` | `0x004F6578` | `0x003F5EA0` | `0x004D7F30` | `CAppSelectMain` |
| 11 | 11 | `0x003F2A20` | `0x003FAEF0` | `0x004F68C0` | `0x004F68E8` | `0x003FDD40` | `0x004D85A0` | `CAppSelectCharcter` |
| 12 | 12 | `0x003F29C0` | `0x003F5EC0` | `0x004F6610` | `0x004F6638` | `0x003F7120` | `0x004D7F70` | `CAppSelectWorld` |
| 13 | 13 | `0x003F2960` | `0x003F66C0` | `0x004F65B0` | `0x004F65D8` | `0x003F7110` | `0x004D7F70` | `CAppSelectWorld` |
| 14 | 14 | `0x003F2900` | `0x003E6300` | `0x004F6240` | `0x004F6268` | `0x003E8890` | `0x004D7568` | `CAppFightMain` |
| 15 | 15 | `0x003F28A0` | `0x00406D20` | `0x004F6A60` | `0x004F6A88` | `0x00407F30` | `0x004D8880` | `CAppFightMainTrain` |
| 16 | 19 | `0x003F2720` | `0x003E38C0` | `0x004F6060` | `0x004F6088` | `0x003E40B0` | `0x004D73F0` | `CAppFightDemoBoss` |
| 17 | 20 | `0x003F26C0` | `0x003F9500` | `0x004F6790` | `0x004F67B8` | `0x003F9C10` | `0x004D8030` | `CAppFightDemoEnding` |
| 18 | 21 | `0x003F2660` | `0x003E4190` | `0x004F60C0` | `0x004F60E8` | `0x003E4A90` | `0x004D7450` | `CAppFightDemoStart` |
| 19 | 22 | `0x003F2600` | `0x003F8AD0` | `0x004F6730` | `0x004F6758` | `0x003F94E0` | `0x004D7FF0` | `CAppFightStageView` |
| 20 | 23 | `0x003F25A0` | `0x003E8A20` | `0x004F6300` | `0x004F6328` | `0x003EA530` | `0x004D75D0` | `CAppFightPlaySingle` |
| 21 | 24 | `0x003F2540` | `0x003EA310` | `0x004F62A0` | `0x004F62C8` | `0x003EA440` | `0x004D75B0` | `CAppFightPlayDoubles` |
| 22 | 16 | `0x003F2840` | `0x0040C320` | `0x004F6C50` | `0x004F6C78` | `0x0040CEF0` | `0x004D8A70` | `CAppFightDemoFinish` |
| 23 | 17 | `0x003F27E0` | `0x00412450` | `0x004F6EF0` | `0x004F6F18` | `0x004127C0` | `0x004D8DA0` | `CAppFightQuickLoad` |
| 24 | 18 | `0x003F2780` | `0x00415B20` | `0x004F7010` | `0x004F7038` | `0x00416000` | `0x004D8E60` | `CAppFightSurvivalNext` |
| 25 | 25 | `0x003F24E0` | `0x003E4B70` | `0x004F6120` | `0x004F6148` | `0x003E4CC0` | `0x004D7470` | `CAppFightDemoEnd` |
| 26 | 26 | `0x003F2480` | `0x003E4DA0` | `0x004F6180` | `0x004F61A8` | `0x003E59C0` | `0x004D74C0` | `CAppFightDemoEndCard` |
| 27 | 27 | `0x003F2420` | `0x003E5AA0` | `0x004F61E0` | `0x004F6208` | `0x003E61B0` | `0x004D74E0` | `CAppFightGameOver` |
| 28 | 28 | `0x003F23C0` | `0x0040BAC0` | `0x004F6BF0` | `0x004F6C18` | `0x0040C300` | `0x004D89E0` | `CAppFightResultMain` |
| 29 | 29 | `0x003F2360` | `0x0040A160` | `0x004F6B30` | `0x004F6B58` | `0x0040AA80` | `0x004D8950` | `CAppFightResultCsAcSingle` |
| 30 | 30 | `0x003F2300` | `0x0040AAA0` | `0x004F6B90` | `0x004F6BB8` | `0x0040BAA0` | `0x004D89C0` | `CAppFightResultCsAcDoubles` |
| 31 | 31 | `0x003F22A0` | `0x003EA680` | `0x004F6360` | `0x004F6388` | `0x003EA8B0` | `0x004D75E8` | `CAppFgtResDgnM` |
| 32 | 32 | `0x003F2240` | `0x003EAA70` | `0x004F6420` | `0x004F6448` | `0x003EABB0` | `0x004D7608` | `CAppFgtResDgnO` |
| 33 | 33 | `0x003F21E0` | `0x003EA560` | `0x004F63C0` | `0x004F63E8` | `0x003EA980` | `0x004D75F8` | `CAppFgtResDgnC` |
| 34 | 34 | `0x003F2180` | `0x0040E7A0` | `0x004F6CD0` | `0x004F6CF8` | `0x0040ED20` | `0x004D8AE0` | `CAppFightResultSurvival` |
| 35 | 35 | `0x003F2120` | `0x0040ED40` | `0x004F6D30` | `0x004F6D58` | `0x0040F180` | `0x004D8BC0` | `CAppFightResultSurvBoss` |
| 36 | 36 | `0x003F20C0` | `0x0040F1A0` | `0x004F6D90` | `0x004F6DB8` | `0x0040FB50` | `0x004D8C10` | `CAppFightResultSurvNorm` |
| 37 | 37 | `0x003F2060` | `0x0040FB70` | `0x004F6DF0` | `0x004F6E18` | `0x0040FF30` | `0x004D8C30` | `CAppFightResultSurvRoul` |
| 38 | 38 | `0x003F2000` | `0x0040FF50` | `0x004F6E50` | `0x004F6E78` | `0x00410E20` | `0x004D8C90` | `CAppFightResultVersus` |
| 39 | 39 | `0x003F1FA0` | `0x003E27B0` | `0x004F5F90` | `0x004F5FB8` | `0x003E2940` | `0x004D5358` | `CAppEnding` |
| 40 | 44 | `0x003F1DC0` | `0x003E33F0` | `0x004F6000` | `0x004F6028` | `0x003E37D0` | `0x004D73B8` | `CAppEndingDemo` |
| 41 | 45 | `0x003F1D60` | `0x003F9C30` | `0x004F67F0` | `0x004F6818` | `0x003FA050` | `0x004D8048` | `CAppGameOver` |
| 42 | 40 | `0x003F1F40` | `0x003FDD60` | `0x004F6920` | `0x004F6948` | `0x003FE330` | `0x004D85F0` | `CAppMenuMain` |
| 43 | 41 | `0x003F1EE0` | `0x00402550` | `0x004F69B0` | `0x004F69D8` | `0x004030D0` | `0x004D8640` | `CAppShenronMain` |
| 44 | 42 | `0x003F1E80` | `0x0041D230` | `0x004F71C0` | `0x004F71E8` | `0x0041DE30` | `0x004D9180` | `CAppShenronSel` |
| 45 | 43 | `0x003F1E20` | `0x00409930` | `0x004F6AD0` | `0x004F6AF8` | `0x0040A140` | `0x004D8908` | `CAppDMModeMain` |
| 46 | 46 | `0x003F1D00` | `0x00418F60` | `0x004F7080` | `0x004F70A8` | `0x004196F0` | `0x004D8F30` | `CAppOptionModeMain` |
| 47 | 47 | `0x003F1CA0` | `0x0041BF70` | `0x004F7140` | `0x004F7168` | `0x0041C270` | `0x004D90A0` | `CAppOptionRanking` |

Every row additionally has `factory_site`, `registration_callsite`, `registration_id_site`, `factory_table_store_site`, `constructor_callsite`, plus **20 base-vtable words and ten secondary phase-vtable callback pointers** in JSON. Callback pointer recovery does **not** by itself prove execution order, state semantics or destructor/cleanup behaviour.

## Directed graph and instruction evidence

Graphviz `.dot` deliberately uses distinct graphical representations:

- **Solid edges:** native transition requests (`0x003DFB00`). No assertion of completed factory execution.
- **Dashed edges:** native child requests (`0x003DFBD0`), not unconditional parent-child construction.
- **Solid dark-blue conditional edges:** ID 6 → ID 3 or ID 6 → ID 6 via the ELF-verified field-derived request at `0x003E09E0`; these are *requests*, not successful constructions.
- **Dotted dark-green edge:** the instance provider `0x003F1C40` invokes a BSS factory by `jalr` at `0x003F1C78`, but does not install the active root pointer and is not itself a transition request.
- **Dotted cyan edges:** exact ELF-confirmed cross-app lookup/method calls (not native transition requests or parent/child creation).
- **Dotted dark-orange edges to a diamond:** original requests for sentinel `0x30` (48), **not** app IDs. Generic forwarded caller-ID requests are represented separately from static application edges.
- **Dotted edges between screen nodes:** the owner's observed *visible* progression, not native app IDs.
- **Instance-provider callsites:** 37 dedicated records retaining the compatible `factory_lookup` API label in JSON; the helper can execute a factory through `jalr`, but each callsite is not a native transition edge.

The source-ID annotations on some callsites are **nearby phase-callback candidates**, not a proven interprocedural ownership graph. In particular, shared ID 14/15 fighter callbacks must not be assigned a unique source without owner-state analysis.

Selected exact literal request sites:

| Source candidate ID | Destination ID | JAL site | API | Evidence |
|---:|---:|---|---|---|
| 5 | 1 | `0x0041F070` | transition | Literal instruction + direct call |
| 1 | 6 | `0x003FADA4` | transition | Literal instruction + direct call |
| 2 | 6 | `0x003F89C8` | transition | Literal instruction + direct call |
| 3 | 42 | `0x003F786C` | transition | Literal instruction + direct call |
| 3 | 6 | `0x003F7898` | transition | Literal instruction + direct call |
| 42 | 3 | `0x003FE21C` | transition | Literal instruction + direct call |
| 42 | 1 | `0x003FE1CC` | transition | Literal instruction + direct call |
| 6 | 4 | `0x003E08B0` | child_request | Literal instruction + direct call |
| 6 | 7 | `0x003E08C8` | child_request | Literal instruction + direct call |
| 6 | 8 | `0x003E08E0` | child_request | Literal instruction + direct call |
| 6 | 9 | `0x003E08F8` | child_request | Literal instruction + direct call |
| 44 | 43 | `0x0041D790` | transition | Literal instruction + direct call |

Unregistered/sentinel/dynamic request callsites: `0x003DFB8C` sentinel 0x30, `0x003DFC1C` dynamically forwards the child helper's caller-provided ID, `0x003E09E0` field-derived ID 3/ID 6 conditional target, `0x003E4C54` ID 25 timer-gated sentinel 0x30, `0x003E920C` ID 20 state-9 completion-gated sentinel 0x30, `0x0040BD0C` selector-derived ID 29/30/34/38 or sentinel. The destination value `0x30` (48) is an internal sentinel, **not application ID 48**.

For original request evidence, inspect `callsites[]` and validate the `callsite`, `api_address`, and `argument_site` instruction words using the included extractor. Request processing depends on scheduler state and may not create the target immediately. The destination class is resolved using the factory registry only when `is_registered_destination` is true.

## Boot-to-main-menu: native internal nodes versus visible screens

The owner-observed visible progression remains:

`Warning / Video Mode → Startup / Splash → Title Screen → Press Start → Main Menu`.

This is a **confirmed visible screen order**. It is not equivalent to five consecutive native application IDs:

1. **Warning widget / monitor selection** is native ID **5**, `CAppMonitorSelect`; selecting *To Game* requests **ID 1** (`CAppWarning`) at `0x41F070`. The editor displays the existing Startup/Splash preview as the next visible surface, without asserting that ID 1 actually executed.
2. **ID 1**, `CAppWarning`, participates in an internal application handshake. `0x3FABF8` is a **factory lookup for ID 2** and `0x3FABFC` sets the ID 2 argument to that lookup. That is **not itself a child transition**. ID 1 also has the direct native transition request to ID **6** at `0x3FADA4`. The lifecycle and visible display ownership across this sequence need fuller tracing.
3. **Startup / Splash** uses native logo resources and the ID **4** `CAppLogoMain` inspector. Its preview completion leading to Title Screen is *user-observed*; the corresponding native dispatcher/parent-return evidence is still open.
4. **Title Screen preview** is associated with the ID **2** `CAppCRISofdec` internal title/middleware path; **ID 3** separately names `CAppTitleMain` and owns the Press Start flow. The ID 2 request to **ID 6** at `0x3F89C8` is native evidence. The editor records that request but advances to Press Start as the owner-observed visible screen, while preserving Demo Main as its own inspector; no missing Demo Main update is fabricated.
5. **Press Start**, ID **3**, requests **ID 42** at `0x3F786C` after Start, or **ID 6** at `0x3F7898` for attract mode. **Main Menu** is native ID **42** `CAppMenuMain`, not neighboring **43**. Its native controller also contains an ID 3 request, recorded at `0x3FE21C`.

The distinction between observed preview handoff and verified native runtime handoff is preserved in `arika_screen_flow.py`. No new texture loading or pixel-perfect rendering dependency is introduced.

## Ownership, callback slots and lifecycle semantics

Each application records **two top-level vtables**. The base table has its independently verified getter in offset `+0x08`, while the secondary phase table has **ten callback pointers** at offsets `+0x08` through `+0x2C`. The earlier `+0x30/+0x34` reads were adjacent data, not additional phase callbacks. The base vtable has **20 recorded words** at `+0x08` through `+0x54`; its `+0x30..+0x54` tail aliases the ten secondary callbacks. Some phase slots are common base helpers (`0x003DFA80`, `0x003DFA90`, `0x003DFAB0`, `0x003DFAC0`, `0x003DFAD0`); others are app-specific. These common addresses should be treated as shared callback targets rather than 47 independent overrides.

Recovered app transition requests `0x003DFB00`, child requests `0x003DFBD0`, and `0x003F1C40` factory lookups must be analysed separately. The generic scheduler phase gates, child-successor processing and callback invocation sites are ELF-backed. DemoMain's conditional ID 3/ID 6 exit targets are also recovered; runtime branch outcomes, other dynamic requests, parent return policy, readiness state and cleanup effects require further tracing. Vtable slot addresses are listed without prematurely assigning all to init/load/begin/update/draw/release/cleanup.

## Native request scheduler evidence (ELF-derived)

The original transition function at `0x003DFB00` reads the native object's
flags byte at `this+0x08` and phase byte at `this+0x09`; it branches through
the case pointer table at `0x004D5280`. At `0x003DFB4C`/`0x003DFB58`,
selected cases write the pending requested app ID to `this+0x10`.
When an existing child ID at `this+0x12` differs from the `0x30` sentinel,
the `0x003DFB7C` lookup may recurse through `0x003DFB8C`; this is **not**
an unconditional immediate application construction.

The child helper at `0x003DFBD0` tests the flag byte at `this+0x08`,
looks up the existing child at `this+0x12` (`0x003DFBFC`), and can **forward the incoming caller-provided ID** to the existing child's `0x003DFB00` transition method at `0x003DFC1C`. On its creation path, `0x003DFC2C`
looks up the requested child, `0x003DFC34` propagates a parent field into
child `+0x13`, and `0x003DFC40`–`0x003DFC44` propagates and increments
a nesting/depth field into child `+0x14`. These stores establish
parent metadata, not full parent **restoration** behaviour.

The base initializer `0x003DFC90` clears flags and state at
`this+0x08`, sets phase `this+0x09 = 1`, initializes bytes
`+0x10`, `+0x12` and `+0x13` to the `0x30` sentinel, and calls a
virtual callback at vtable offset `+0x34` (`0x003DFCC0`).
These fields, their supporting instruction addresses and confidence
boundaries are stored in `dispatcher` in the JSON registry.

The generic per-app lifecycle dispatcher now determines the role of
base-vtable slots `+0x34` (initialization callback), `+0x38` (phase-2
readiness callback), `+0x3C` (phase-3 callback), `+0x40` (phase-4
callback) and `+0x44` (phase-5 completion callback). These are
native *invocation roles*, not proof of detailed per-class resource
ownership, draw order or callback internals. For example, ID 1's
phase-2 callback points at `0x003FAAB0`, and ID 42's phase-4 callback
points at `0x003FE020`.

## Per-application lifecycle callback map — all 47

The following targets are taken from the exact class-specific **base**
vtable entries. The ELF scheduler invokes these offsets, but the table
does not assert that an application has run, nor that a method's
internal rendering/resource semantics are completely understood.

| ID | Native class | Init +0x34 | Phase 2 +0x38 | Phase 3 +0x3C | Phase 4 +0x40 | Phase 5 +0x44 | Shutdown +0x4C |
|---:|---|---|---|---|---|---|---|
| 1 | CAppWarning | `0x003FAA00` | `0x003FAAB0` | `0x003FABF0` | `0x003FAC20` | `0x003DFAB0` | `0x003FADD0` |
| 2 | CAppCRISofdec | `0x003F8740` | `0x003F8790` | `0x003F88D0` | `0x003F8900` | `0x003F89F0` | `0x003F8A50` |
| 3 | CAppTitleMain | `0x003F71E0` | `0x003F7320` | `0x003F7680` | `0x003F76A0` | `0x003F79A0` | `0x003F7A90` |
| 4 | CAppLogoMain | `0x0041E680` | `0x0041E750` | `0x0041E850` | `0x0041E890` | `0x003DFAB0` | `0x0041EB00` |
| 5 | CAppMonitorSelect | `0x0041ED10` | `0x0041EDB0` | `0x0041EEF0` | `0x0041EF00` | `0x003DFAB0` | `0x0041F2A0` |
| 6 | CAppDemoMain | `0x003E0440` | `0x003E04A0` | `0x003E07F0` | `0x003E0830` | `0x003E0A00` | `0x003E0AB0` |
| 7 | CAppDemoMovie | `0x003E1C20` | `0x003E1C80` | `0x003E1DD0` | `0x003E1DF0` | `0x003E1FF0` | `0x003E2020` |
| 8 | CAppDemoMain | `0x003E2280` | `0x003E22F0` | `0x003DFA90` | `0x003E23C0` | `0x003E24D0` | `0x003E2570` |
| 9 | CAppDemoPlay | `0x003E0E50` | `0x003E0EE0` | `0x003E11B0` | `0x003E1260` | `0x003DFAB0` | `0x003E14C0` |
| 10 | CAppSelectMain | `0x003F5670` | `0x003F5810` | `0x003DFA90` | `0x003F5A40` | `0x003F5BC0` | `0x003F5CD0` |
| 11 | CAppSelectCharcter | `0x003FAF50` | `0x003FB450` | `0x003DFA90` | `0x003FB460` | `0x003DFAB0` | `0x003FBE50` |
| 12 | CAppSelectWorld | `0x003F5F30` | `0x003DFA80` | `0x003DFA90` | `0x003F6110` | `0x003DFAB0` | `0x003F65C0` |
| 13 | CAppSelectWorld | `0x003F6750` | `0x003DFA80` | `0x003DFA90` | `0x003F6990` | `0x003DFAB0` | `0x003F6F10` |
| 14 | CAppFightMain | `0x003E6800` | `0x003E68B0` | `0x003E6EB0` | `0x003E6EF0` | `0x003E7BA0` | `0x003E7F30` |
| 15 | CAppFightMainTrain | `0x00406F20` | `0x003E68B0` | `0x003E6EB0` | `0x004070E0` | `0x003E7BA0` | `0x004071F0` |
| 16 | CAppFightDemoBoss | `0x003E3910` | `0x003E39E0` | `0x003E3AE0` | `0x003E3B90` | `0x003E3CE0` | `0x003E3CF0` |
| 17 | CAppFightDemoEnding | `0x003F9560` | `0x003F9630` | `0x003F9760` | `0x003F97D0` | `0x003DFAB0` | `0x003F9AE0` |
| 18 | CAppFightDemoStart | `0x003E41F0` | `0x003E4250` | `0x003DFA90` | `0x003E42D0` | `0x003E4950` | `0x003E4A30` |
| 19 | CAppFightStageView | `0x003F8B20` | `0x003F8C20` | `0x003F8C00` | `0x003F8D00` | `0x003F8F80` | `0x003F90A0` |
| 20 | CAppFightPlaySingle | `0x003E8A80` | `0x003DFA80` | `0x003DFA90` | `0x003E8BC0` | `0x003E9650` | `0x003E9660` |
| 21 | CAppFightPlayDoubles | `0x003E8A80` | `0x003DFA80` | `0x003DFA90` | `0x003EA430` | `0x003E9650` | `0x003E9660` |
| 22 | CAppFightDemoFinish | `0x0040C370` | `0x0040C4F0` | `0x0040C800` | `0x0040C9E0` | `0x0040CA10` | `0x0040CDA0` |
| 23 | CAppFightQuickLoad | `0x004124A0` | `0x003DFA80` | `0x003DFA90` | `0x00412550` | `0x003DFAB0` | `0x003DFAD0` |
| 24 | CAppFightSurvivalNext | `0x00415B70` | `0x003DFA80` | `0x003DFA90` | `0x00415C70` | `0x003DFAB0` | `0x003DFAD0` |
| 25 | CAppFightDemoEnd | `0x003E4BC0` | `0x003DFA80` | `0x003DFA90` | `0x003E4C00` | `0x003DFAB0` | `0x003E4C80` |
| 26 | CAppFightDemoEndCard | `0x003E4E00` | `0x003E4F90` | `0x003E5160` | `0x003E5270` | `0x003E5430` | `0x003E54C0` |
| 27 | CAppFightGameOver | `0x003E5B30` | `0x003E5B80` | `0x003DFA90` | `0x003E5BC0` | `0x003E5EE0` | `0x003E5F30` |
| 28 | CAppFightResultMain | `0x0040BB00` | `0x0040BB60` | `0x0040BBB0` | `0x0040BBD0` | `0x0040BC20` | `0x0040BC80` |
| 29 | CAppFightResultCsAcSingle | `0x0040A2A0` | `0x0040A560` | `0x0040A5C0` | `0x0040A5D0` | `0x0040AA20` | `0x0040AA70` |
| 30 | CAppFightResultCsAcDoubles | `0x0040AC10` | `0x0040AE90` | `0x0040AF60` | `0x0040AF70` | `0x0040B680` | `0x0040B6A0` |
| 31 | CAppFgtResDgnM | `0x003EA6C0` | `0x003DFA80` | `0x003DFA90` | `0x003EA7D0` | `0x003DFAB0` | `0x003EA8A0` |
| 32 | CAppFgtResDgnO | `0x003EAAC0` | `0x003EAB00` | `0x003DFA90` | `0x003EAB10` | `0x003EAB30` | `0x003EAB40` |
| 33 | CAppFgtResDgnC | `0x003EA5B0` | `0x003EA5C0` | `0x003DFA90` | `0x003EA5D0` | `0x003EA5F0` | `0x003EA670` |
| 34 | CAppFightResultSurvival | `0x0040E820` | `0x0040E920` | `0x0040E940` | `0x0040EA00` | `0x0040EC40` | `0x0040EC90` |
| 35 | CAppFightResultSurvBoss | `0x0040EDF0` | `0x0040EE30` | `0x0040EEE0` | `0x0040EF30` | `0x0040F020` | `0x0040F030` |
| 36 | CAppFightResultSurvNorm | `0x0040F2E0` | `0x0040F570` | `0x0040F5F0` | `0x0040F600` | `0x0040FAE0` | `0x0040FAF0` |
| 37 | CAppFightResultSurvRoul | `0x0040FC30` | `0x0040FCC0` | `0x0040FD30` | `0x0040FD40` | `0x0040FF10` | `0x0040FF20` |
| 38 | CAppFightResultVersus | `0x00410140` | `0x004103F0` | `0x004104D0` | `0x004104E0` | `0x00410C20` | `0x00410C40` |
| 39 | CAppEnding | `0x003E2800` | `0x003E2850` | `0x003DFA90` | `0x003E2860` | `0x003E28F0` | `0x003E2900` |
| 40 | CAppEndingDemo | `0x003E3450` | `0x003E3490` | `0x003DFA90` | `0x003E3600` | `0x003DFAB0` | `0x003E3730` |
| 41 | CAppGameOver | `0x003F9C80` | `0x003F9D40` | `0x003DFA90` | `0x003F9D90` | `0x003DFAB0` | `0x003F9F90` |
| 42 | CAppMenuMain | `0x003FDE00` | `0x003FDEB0` | `0x003FDFE0` | `0x003FE020` | `0x003FE240` | `0x003FE2F0` |
| 43 | CAppShenronMain | `0x004025B0` | `0x00402630` | `0x00402AD0` | `0x00402BF0` | `0x00402D60` | `0x00402FA0` |
| 44 | CAppShenronSel | `0x0041D290` | `0x0041D2C0` | `0x0041D370` | `0x0041D560` | `0x0041DC80` | `0x0041DD10` |
| 45 | CAppDMModeMain | `0x00409980` | `0x00409A90` | `0x00409C20` | `0x00409C90` | `0x00409FC0` | `0x0040A080` |
| 46 | CAppOptionModeMain | `0x00418FC0` | `0x00419040` | `0x00419290` | `0x004192C0` | `0x004194E0` | `0x004195E0` |
| 47 | CAppOptionRanking | `0x0041BFC0` | `0x0041BFF0` | `0x003DFA90` | `0x0041C080` | `0x0041C120` | `0x0041C170` |

The JSON additionally records callbacks at `+0x48`, `+0x50`
and `+0x54` and the six common base helpers at
`+0x10..+0x24`. Repeated addresses represent shared native
implementations, not copy/pasted per-app logic.

## Boot path: direct Warning → CRI interactions

The exact ELF shows **two application-owned callback paths** in
ID 1 (`CAppWarning`) that address ID 2 (`CAppCRISofdec`) directly:

| Source (ID 1) | Instruction | Target/action | Evidence |
|---|---|---|---|
| Phase-3 callback `0x003FABF0` | `0x003FABF8` | `0x003F1C40(2)` factory lookup | `0x003FABFC` supplies literal ID 2 |
| Same callback | `0x003FAC00` | Direct `0x003F8780` method call on ID 2 instance | `0x003FAC04` passes lookup result as `a0` |
| Phase-4 callback `0x003FAC20` | `0x003FAC30` | Second `0x003F1C40(2)` lookup | `0x003FAC34` supplies ID 2 |
| Same callback | `0x003FAC40` | Virtual callback `+0x38` on ID 2 | `0x003FAC3C` loads the slot; ID 2's vtable points to `0x003F8790` |

This is direct **cross-application method invocation**, verified through
the base vtables and original instructions. None of these calls uses
`0x003DFBD0` to request a child. Consequently they do **not** establish
that ID 2 was created as a child, that it owned the visible title screen,
or that it finished loading. They do establish that the ID 1 wrapper
actively drives an ID 2 middleware/lifecycle component.

These four interactions are stored in `cross_app_interactions` in the
canonical JSON and separately drawn in cyan on the Graphviz file.
The exact-ELF oracle checks their call words, argument setup,
source callback ownership and ID 2 virtual target. ID 1 and ID 2
each independently contain a native request for ID 6 on their later
phase-4 paths (`0x003FADA4` and `0x003F89C8`).
Which request actually executes depends on runtime scheduler state.

## Exact scheduler lifecycle and child successor — follow-up

The original EU-beta ELF provides the **generic** lifecycle mechanism
independently of any particular app's runtime state.

| Phase | Base vtable offset | Indirect-call instruction | Advancement condition |
|---|---|---|---|
| 1 | No phase-specific virtual callback | `0x003DFD28` | flag bit 1 clear and resource-status bit 31 clear |
| 2 | `+0x38` | `0x003DFE64` | callback nonzero; flag bit 1 clear; resource-status bit 31 clear |
| 3 | `+0x3C` | `0x003DFEA8` | callback nonzero; same two guards |
| 4 | `+0x40` | `0x003DFEEC` | callback nonzero; same two guards |
| 5 | `+0x44` | `0x003DFDC0` | child absence/suppression and callback/resource/parent guards; may enter phase 6 |
| 6 | No phase-specific callback | `0x003DFF98` in parent-child helper | completed child can advertise pending successor |

All callbacks above are retrieved through the **base vtable at
`this+0x00`**; the secondary vtable at `this+0x04` overlaps
the same app-specific callback-pointer sequence. The initial
`0x003DFC90` routine calls vtable offset `+0x34` at
`0x003DFCC0`. Generic teardown `0x003E0110` calls `+0x4C`
at `0x003E012C`. Other shared recursive paths invoke `+0x48`,
`+0x50` and `+0x54`; their exact user-visible significance remains
subject to caller analysis.

### Exact parent-child succession

`0x003DFF60` guards processing with the parent's flags `+0x08`
bit `0x04` (`0x003DFF74`). If not suspended, it looks up
the parent's active child ID `+0x12` at `0x003DFF88`.
A child reporting lifecycle phase **6** (`0x003DFF98`) has
its pending successor read from child `+0x10` at
`0x003DFFA8` and stored into the parent's `+0x12`
at `0x003DFFAC`. The original then invokes completed-child
teardown at virtual `+0x14` (`0x003DFFB4`).

A second lookup at `0x003DFFC0` may resolve the successor.
If that successor is in phase 0, an initialization virtual call
`+0x10` occurs at `0x003DFFE4`, parent metadata is installed
at successor `+0x13` (`0x003DFFF8`), and the successor
per-frame callback `+0x18` is invoked at `0x003E0010`.
A missing factory/sentinel `0x30` yields no concrete child.

**This verifies the general child-completion/successor mechanism.** The
specific Demo Main ID 6 → Press Start ID 3 route is now independently
recovered as a **conditional native transition request** from ID 6's
application update. It is not automatically a parent-stack return.
Neither mechanism alone proves that the target factory ran.

### Transition-request phase switching

`0x003DFB00` indexes the exact seven-entry jump table
`0x004D5280`: phases 0, 5 and 6 write their requested ID
into `+0x10`, while phases 1–4 also enter phase 5 and set
the transition-in-progress bit `0x02`. If an existing child is
present, those latter cases can recursively send it the `0x30`
sentinel as a cancellation request, subject to a successful factory
lookup. The `0x01` flag early-exit and `0x04` flag clearing
are preserved in the diagnostic model.

The new asset-free `arika_native_app_lifecycle.py` exposes
`describe_native_phase`, `inspect_native_phase_gate`,
`inspect_native_transition_request`, and
`inspect_native_child_successor`. They **only inspect supplied state**:
no native app creation, memory mutation, callback invocation or
automatic screen progression is claimed. The exact ELF oracle checks
56 instruction words, seven phase table entries and callback indirect
calls. Deterministic Windows/Ubuntu tests exercise phase gates,
all 47 classes, invalid IDs, paused children, successor phase 6 and
sentinel cancellation.

## Demo Main conditional exit requests — exact ELF evidence

The prior tentative ID 6 → ID 3 *parent return* annotation is **superseded**.
The original ID 6 `CAppDemoMain` itself selects an exit-target ID and
passes that target to the original transition-request helper.

| ELF address | Native behaviour |
|---|---|
| `0x003E0440` | ID 6 initialization callback |
| `0x003E0470`, `0x003E0478` | Set instance exit-target byte `this+0x2A = 3` (the ID 3 `CAppTitleMain` factory) |
| `0x003E0830` | ID 6 update callback, also manages the distinct children 4/7/8/9 |
| `0x003E090C`, `0x003E091C` | Probe whether a child is active, then switch on previous choice byte `this+0x28` |
| `0x003E0960` | Previous choice 1 signals the global exit flag **without** changing the exit-target byte; **0x003E095C is the preceding branch, not the flag store** |
| `0x003E0970`, `0x003E0978` | Previous choice 3 overrides exit-target to **6** and signals the global exit flag |
| `0x003E0980` | Test the global exit condition |
| `0x003E09DC`, `0x003E09E0` | Load exit target from `this+0x2A`, request it through `0x003DFB00` |

Consequently, the default exit-target **ID 3** provides an
instruction-backed candidate for the internal
`ID 2 → ID 6 → ID 3` startup handoff after the appropriate Demo Main
child finishes. The choice-3 exit alternatively requests **ID 6**
(and the field's previous value can persist if the object was not
reinitialized). Neither path is an unconditional handoff.

The canonical JSON's `demo_main_exit` section identifies the two
target-setting sites and the original branch/argument instructions;
`callsites[]` retains the single dynamic JAL at `0x003E09E0` with
`target_id = null` and `target_candidates = [3, 6]` so it is **not**
miscounted among the 67 static literal requests. Two separately
conditional native edges in `relationships[]` and Graphviz represent
the possible destinations. The extractor verifies the 13 instruction
words and source vtable callback; deterministic tests model both
choices and ensure the child-activity and exit gates are explicit.

This proves request formation and conditional target identity, **not**
that a game instance took the branch, the factory executed, or the
destination successfully loaded. It does not prove that the entire
user-visible startup tour follows those exact requests.

## Fight Result Main — resolved conditional child dispatch

The ID **28** `CAppFightResultMain` base vtable's phase-3 callback
`0x0040BBB0` calls helper `0x0040BC90` at `0x0040BBB8`.
This helper requests a child through `0x003DFBD0` at
`0x0040BD0C`; it selects its `a1` ID using a native selector
returned by `0x0032A5E0`, not a fixed literal.

| Native selector | Additional condition | Child ID | Registered class |
|---|---|---:|---|
| 1 | `0x003EBCE0` returns zero | 29 | `CAppFightResultCsAcSingle` |
| 1 | `0x003EBCE0` returns nonzero | 30 | `CAppFightResultCsAcDoubles` |
| 2 | None | 34 | `CAppFightResultSurvival` |
| 3 | None | 38 | `CAppFightResultVersus` |
| Other | None | 48 | **0x30 sentinel — not a registered app** |

The relevant ELF branch/target evidence is `0x0040BCB8`,
`0x0040BCC0`, `0x0040BCCC`, `0x0040BCE4` and
the chosen ID loads at `0x0040BCE8` (29),
`0x0040BCF0` (30), `0x0040BD00` (34) and
`0x0040BD04` (38). The default `li s0,0x30`
occurs in the delay slot at `0x0040BCA8`;
the child request's delay-slot argument move is
`0x0040BD10`.

The JSON adds `fight_result_dispatch`, four distinct
`conditional_native_child_request` relationships and the exact
16-bit/32-bit opcode evidence. The `callsites` entry remains
**one** dynamic JAL at `0x0040BD0C`, excluded from the 67
literal registered requests. The Graphviz graph uses **dashed dark-blue
conditional child-request edges** rather than pretending four
children are always instantiated. A pure
`inspect_fight_result_child` function lets the editor examine the
selector and optional subpredicate without running a factory.
The original selector inputs and real runtime branch outcome are
still to be observed.

## Remaining transition and child-request paths — exact-ELF classification

The original 110 direct helper callsites remain unchanged. Across the
**73 transition and child-request JAL sites**, the 67 static requests to
registered application IDs stay exactly as catalogued. The other **six**
are now separately documented with their source semantics:

| Address | Native owner / route | ID semantics | Proof boundary |
|---|---|---|---|
| `0x003DFB8C` | Generic transition helper `0x003DFB00` | Literal `0x30` sent recursively to an existing child | Child ID `+0x12`, phase 1–4 and successful lookup guard |
| `0x003DFC1C` | Generic child helper `0x003DFBD0` | **Forward the incoming `a1`**, not a missing literal app ID | Parent flag bit `0x02` clear, existing child lookup succeeds, clear bit `0x04` on parent |
| `0x003E09E0` | ID 6 `CAppDemoMain` update | Dynamic field `this+0x2A` selects ID **3 or 6** | Exit flag and child-completion conditions, already recovered |
| `0x003E4C54` | ID 25 `CAppFightDemoEnd` update | Literal `0x30` exit/cancel sentinel | Float32 duration threshold and branch |
| `0x003E920C` | ID 20 `CAppFightPlaySingle` update | Literal `0x30` exit/cancel sentinel | Phase-4 callback's jump-table state 9 and completion predicate |
| `0x0040BD0C` | ID 28 `CAppFightResultMain` | Dynamic selector chooses ID **29, 30, 34, 38**, or sentinel | Selector and optional subpredicate, already recovered |

### Child request forwarding is not a new factory edge

The `0x003DFBD0` helper preserves the caller's `a1` as `s1`,
checks parent transition-busy bit `0x02` at `0x003DFBE4`–`0x003DFBEC`,
then looks up the current child ID at parent `+0x12` via
`0x003DFBFC`. When a child exists, instructions
`0x003DFC10`–`0x003DFC20` forward `s1` to `0x003DFB00`
and clear parent bit `0x04`. A successful *lookup* is not the same
as successful acceptance of that request by the child's own phase
scheduler. If no child resolves, `0x003DFC30` instead stores the
new ID into parent `+0x12`; the lookup at `0x003DFC2C` attempts
to retrieve that instance for parent/depth propagation.

Similarly, `0x003DFB8C` is a generic **recursive sentinel** request
with `a1 = 0x30` provided in its delay slot at `0x003DFB90`.
It occurs when the original transition helper enters its
phases 1–4 cancellation path and resolves an existing child.
Neither site supports inventing a concrete destination or another
registered factory.

### ID 25: a native float32 timeout, not a frame-count guess

The ID 25 base-vtable phase-4 callback is `0x003E4C00`.
It compares the object's post-update timer at `this+0x2C`
against the exact 32-bit IEEE-754 constant `0x3CA3D70A`
(**0.019999999552965164 seconds**). The instruction
`c.ole.s` at `0x003E4C28` is followed by
`bc1f` at `0x003E4C2C`; when timer ≤ threshold is false,
it calls `0x003DFB00` at `0x003E4C54` with sentinel `0x30`
loaded in the branch's delay slot (`0x003E4C30`).
A NaN comparison is unordered and therefore also takes the
false branch under native FP comparison semantics.

The timer can be accumulated earlier in the callback depending on a
global flag and a delta from its data object. The research **does not**
fabricate that delta or a PS2 frame duration. The new
`inspect_fight_demo_end_timeout` receives an *already observed*
post-update timer and returns only the requested-ID possibility.

### ID 20: the phase-4 state-9 exit condition

The ID 20 `CAppFightPlaySingle` base-vtable phase-4 callback at
`0x003E8BC0` contains a **ten-entry state jump table** at
`0x004D7580`. State `9` selects entry `0x003E91D4`,
which calls `0x002C0C20`. A **nonzero** result branches over
the exit. When the result is zero, the callback performs two
`0x001CBD10` operations and then calls the generic native
transition method at `0x003E920C` with
sentinel `0x30` loaded at `0x003E9210`.

The independently registered ID 21 `CAppFightPlayDoubles`
does **not** use `0x003E8BC0` as its phase-4 callback
(its slot points elsewhere); sharing nearby fighter routines does
not justify assigning this exit request to both IDs.
The pure `inspect_fight_play_single_finish` helper requires
an explicitly observed signed state byte and an observed boolean
predicate result; missing observations remain unresolved.

The exact-ELF oracle now checks **54 additional raw instruction words**
across these paths, the **ten original jump-table targets**, callback
ownership for IDs 20 and 25, and the non-executing request taxonomy.
The deterministic tests cover stage gating, busy parents, forward vs
new-child paths, 32-bit float comparisons and the `0x30` sentinel.
No original ELF data is committed or required for ordinary CI.

## Root application handoff: actual factory invocation site

The native EE scheduler contains a more consequential path than the
request-only helpers: **`0x003DFD34` → `0x003F1BA0`**. This is the
instruction path capable of *calling* the destination's factory.

**When does the scheduler reach it?** In `0x003DFCF0`, an application
in lifecycle phase **5** waits until the child ID `this+0x12`
is `0x30` (no active child) or the parent suppression bit
`this+0x08 & 0x04` is set. It then calls the application's base
vtable callback `+0x44` at `0x003DFDC0`. If the callback returns
nonzero and the status word `this+0x0C` has bit 31 clear, the
parent ID field `this+0x13` determines the path:

- **Parent ID `0x30`:** call the root handoff `0x003F1BA0`
  at `0x003DFF34`, passing the pending ID byte
  `this+0x10` in the MIPS JAL delay slot `0x003DFF38`.
- **Parent ID 1–47:** store lifecycle phase **6** at
  `0x003DFDF8`, look up the pending target at
  `0x003DFDFC`, and propagate depth when that lookup succeeds.
  This is a nested parent/child completion route, not the root
  factory handoff.

**What does `0x003F1BA0` actually do?**

| Address | Action |
|---|---|
| `0x003F1BAC` | Calls one-time/guarded app registry initializer `0x003F1580` |
| `0x003F1BB4`–`0x003F1BC4` | Masks requested ID to eight bits and checks **1 ≤ ID ≤ 47** |
| `0x003F1BCC`–`0x003F1BDC` | Loads `*(uint32_t *)(0x006217E0 + 4 × ID)` |
| `0x003F1BE0` | **`jalr` to the selected factory pointer** |
| `0x003F1BEC`–`0x003F1BFC` | Chooses factory return pointer, or fallback `0x004FCAD4` when null |
| `0x003F1C04` | Stores that root pointer to global BSS slot **`0x0063BE38`** |
| `0x003F1C10`–`0x003F1C30` | For invalid IDs (including `0x30`), stores static fallback **`0x005E1AC0`** |

This is substantially different from the
`0x003F1C40` instance-provider helper: **both invoke factories**, but
but `0x003F1BA0` also **installs the result as the active root
pointer**. The immediate factory return is not equivalent to
loading, initializing or rendering the app.

A separate instruction audit of the provider at
`0x003F1C40` confirms it also initializes the factory registry
(`0x003F1C4C`), masks its ID to eight bits, loads the
BSS factory pointer at `0x003F1C74`, and calls that pointer
at `0x003F1C78`. Unlike the root installer, it **returns the
factory's pointer without storing `0x0063BE38`**.
The provider's range check is `0 ≤ ID < 48`; ID 0
passes the machine-level bound check but is not one of the
**47 registered IDs**, so no assertion is made about the
unregistered table slot. The root installer explicitly requires
`1 ≤ ID ≤ 47`. Nine additional opcode signatures
prove this separate provider path.

The canonical JSON's `native_root_factory_dispatch` section records
**40 independent instruction word signatures**, bounds, caller
guards, pointer locations and fallback paths. All 40 words
matched the exact EU-beta ELF during local analysis. The extractor
checks those opcodes, the concrete root pointer slot and
the registry initializer/indirect factory invocation; the pure
`describe_native_root_factory` and
`inspect_native_phase_five_root_handoff` functions expose
the relevant possible control-flow outcomes using user-supplied
observations. Tests cover all **47** table indices, invalid IDs,
null-factory fallback descriptions, active-child suppression,
callback failure, status-busy state, and nested versus root
completion. They do **not** invoke the PS2 binary.

**Evidence boundary:** this proves the original EE *contains*
real root-factory execution paths and identifies their guards.
It does not show that a particular boot run entered the branch,
that the pointer was actually written in that run, or that
resource initialization and a visible transition succeeded.
The five-screen guided editor preview remains distinct from
an authentic native boot trace.

## Reproduction and tests

Run locally with the *exact* original beta ELF (the ELF is not distributed with the repository):

```bash
cd arika-py_on_rs
python arika_native_app_extract.py /path/to/SLES_541.61
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 python -m unittest test_arika_app_registry test_arika_native_app_registry test_arika_native_app_lifecycle -v
```

For Windows PowerShell, set `$env:SDBZ_EU_BETA_ELF` before the test invocation. Without the original file in CI, deterministic metadata checks remain active; exact-ELF assertions skip. The Windows/Ubuntu workflow runs both deterministic suites.

## Unresolved work (do not claim complete behaviour)

- Prove call ownership and conditional predicates through native interprocedural control/data flow. Current source candidates can be ambiguous or shared callbacks.
- The **phase-5 native root factory invocation**, generic child completion/successor mechanism and ID 6 conditional exit requests are ELF-verified. Recover actual runtime branch acceptance, remaining parent restoration details and phase/fade/resource predicates. The existence of a real `jalr` does not prove execution in a captured run.
- The six nonliteral/unregistered transition-or-child request sites are now *classified* as a field-derived choice, selector-derived choice, generic caller-ID forward, or sentinel requests. Remaining unknowns are runtime values/branches, dynamic **factory-lookup** inputs, and interprocedural parent restoration.
- Generic lifecycle phases and virtual invocation sites are verified; trace per-class callback internals, resource ownership, draw ordering and teardown effects for all 47 classes.
- Complete the startup logo and ID 1/ID 2 middleware ownership trace and establish when the now-recovered DemoMain conditional ID 3 request actually executes. The editor retains the observed five-screen order as a separately labelled preview.
- Runtime trace/PCSX2 differential verification of the complete registry graph and multi-screen update/draw ordering.

**PR #26 stays draft. PR #25 visual parity remains a separate acceptance gate.**
