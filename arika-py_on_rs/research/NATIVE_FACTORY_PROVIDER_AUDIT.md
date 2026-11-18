# EU-beta native factory-provider argument audit

**Target:** Super Dragon Ball Z **EU beta**, `SLES_541.61` (2006-05-02; not EU retail)  
**ELF SHA-256:** `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`  
**Base:** merged `master` after PRs #25 and #26  
**Evidence:** [native_factory_provider_calls_eu_beta.json](native_factory_provider_calls_eu_beta.json)  
**Verifier:** `../arika_native_factory_provider_extract.py`

## Scope and interpretation

The previous 47-ID native registry recovered **110** direct calls to three
helper APIs: 41 transition requests, 32 child requests and **37**
calls to `0x003F1C40`, historically named `factory_lookup`. This last
helper is an **instance provider**: it accesses the registered factory
table and can invoke a factory through `jalr` at `0x003F1C78`.
It does **not** store the global root-application pointer
(`0x0063BE38`); the separate root installer `0x003F1BA0` does.

This audit recovers the **`a0` provider argument source at every one
of the 37 static JAL sites**, without reclassifying any call as a new
screen transition, assuming a factory ran in a user capture or
equating a factory invocation with a fresh object allocation.

| Classification | Sites | Interpretation |
|---|---:|---|
| Explicit literal registered ID | **26** | `addiu a0,zero,ID`; includes branch and JAL delay slots |
| Child-ID byte `this+0x12` | **9** | The runtime child ID may vary; the field is **not** a literal app |
| Pending-ID byte `this+0x10` | **1** | The runtime pending target may vary |
| Forwarded requested child ID | **1** | `move a0,s1` in the generic child helper, where `s1` holds caller `a1` |
| **Total** | **37** | No remaining unclassified provider JAL argument sources |

The 26 literal lookups address only registered IDs **2, 5, 6, 8,
9, 14, 15, 22**. For example, `0x003FABF8` and
`0x003FAC30` request provider **ID 2** from the Warning wrapper
at separate lifecycle phases; `0x00326B84` targets ID **5**;
`0x003E0AB8`/ `0x003E0AD0` target IDs **8** and **9** in the
Demo family. ID **15** appears in twelve literal provider calls,
including less obvious delay-slot branches at `0x001CA1F8`
and `0x001CBFA0`.

### Every original provider JAL and argument-forming instruction

| Provider JAL | Proved ID, if literal | Argument kind | Argument word site | Instruction position |
|---|---|---|---|---|
| `0x001CA1F8` | `15` CAppFightMainTrain | `literal` | `0x001CA11C` | branch delay slot |
| `0x001CA36C` | `15` CAppFightMainTrain | `literal` | `0x001CA368` | branch delay slot |
| `0x001CBFA0` | `15` CAppFightMainTrain | `literal` | `0x001CBED4` | branch delay slot |
| `0x001CF14C` | `15` CAppFightMainTrain | `literal` | `0x001CF148` | branch delay slot |
| `0x001D02F8` | `15` CAppFightMainTrain | `literal` | `0x001D02E0` | branch delay slot |
| `0x001D0324` | `15` CAppFightMainTrain | `literal` | `0x001D0328` | jal delay slot |
| `0x001DD270` | `15` CAppFightMainTrain | `literal` | `0x001DD274` | jal delay slot |
| `0x001F4878` | `15` CAppFightMainTrain | `literal` | `0x001F4874` | branch delay slot |
| `0x00326B84` | `5` CAppMonitorSelect | `literal` | `0x00326B88` | jal delay slot |
| `0x0033E968` | `15` CAppFightMainTrain | `literal` | `0x0033E96C` | jal delay slot |
| `0x0033EC18` | `15` CAppFightMainTrain | `literal` | `0x0033EC1C` | jal delay slot |
| `0x003DFB7C` | *runtime state* | `child_id_byte` | `0x003DFB80` | jal delay slot |
| `0x003DFBFC` | *runtime state* | `child_id_byte` | `0x003DFC00` | jal delay slot |
| `0x003DFC2C` | *runtime state* | `requested_child_id` | `0x003DFC08` | branch delay slot |
| `0x003DFDFC` | *runtime state* | `pending_id_byte` | `0x003DFE00` | jal delay slot |
| `0x003DFF88` | *runtime state* | `child_id_byte` | `0x003DFF8C` | jal delay slot |
| `0x003DFFC0` | *runtime state* | `child_id_byte` | `0x003DFFC4` | jal delay slot |
| `0x003DFFFC` | *runtime state* | `child_id_byte` | `0x003E0000` | jal delay slot |
| `0x003E0058` | *runtime state* | `child_id_byte` | `0x003E0054` | before jal |
| `0x003E01F0` | *runtime state* | `child_id_byte` | `0x003E01E8` | before jal |
| `0x003E027C` | *runtime state* | `child_id_byte` | `0x003E0274` | before jal |
| `0x003E02F4` | *runtime state* | `child_id_byte` | `0x003E02EC` | before jal |
| `0x003E0AB8` | `8` CAppDemoMain | `literal` | `0x003E0ABC` | jal delay slot |
| `0x003E0AD0` | `9` CAppDemoPlay | `literal` | `0x003E0AD4` | jal delay slot |
| `0x003E0B20` | `6` CAppDemoMain | `literal` | `0x003E0B24` | jal delay slot |
| `0x003E0F94` | `6` CAppDemoMain | `literal` | `0x003E0F90` | before jal |
| `0x003E236C` | `9` CAppDemoPlay | `literal` | `0x003E2370` | jal delay slot |
| `0x003E23E8` | `9` CAppDemoPlay | `literal` | `0x003E23DC` | branch delay slot |
| `0x003E9340` | `22` CAppFightDemoFinish | `literal` | `0x003E933C` | branch delay slot |
| `0x003FABF8` | `2` CAppCRISofdec | `literal` | `0x003FABFC` | jal delay slot |
| `0x003FAC30` | `2` CAppCRISofdec | `literal` | `0x003FAC34` | jal delay slot |
| `0x0040C56C` | `14` CAppFightMain | `literal` | `0x0040C570` | jal delay slot |
| `0x0040C580` | `15` CAppFightMainTrain | `literal` | `0x0040C584` | jal delay slot |
| `0x0040CCE8` | `14` CAppFightMain | `literal` | `0x0040CCEC` | jal delay slot |
| `0x0040CCFC` | `15` CAppFightMainTrain | `literal` | `0x0040CD00` | jal delay slot |
| `0x00412770` | `14` CAppFightMain | `literal` | `0x00412774` | jal delay slot |
| `0x00415DCC` | `14` CAppFightMain | `literal` | `0x00415DD0` | jal delay slot |

**Instruction timing matters:** For MIPS branch/JAL delay slots, the
argument instruction may execute **after the branch or JAL opcode**
despite appearing later in disassembly, or well before the target
provider call. The verifier checks original instruction words at both
the JAL and the argument-setting site. Two distant branch-derived
literal cases are intentionally not classified as unknown simply
because an instruction-window heuristic would miss them.

### Generic dynamic sources are not missing factories

The provider argument is `lb a0,+0x12(base)` at nine sites,
`lb a0,+0x10(base)` at `0x003DFDFC`, and
`move a0,s1` at `0x003DFC2C`. The latter is the
`0x003DFBD0` child-request helper's original caller-supplied ID.
In all eleven cases, the **instruction source** is proven but the
**runtime value and any resulting factory invocation are not**.
Do not add eleven guessed destinations to the graph.

### Validation and acceptance criteria

The canonical `arika_app_registry.py` exposes
`registered_factory_providers(target_id=None, argument_kind=None)`
and `APP_NATIVE_PROVIDER_CALLS` from the checked-in JSON.
This is a separate evidence layer and deliberately leaves
`registered_native_requests()`, the **73 transition/child callsite
count**, and the **67 literal registered requests** unchanged.

Run the deterministic tests without an ELF:

```bash
cd arika-py_on_rs
python -m unittest test_arika_native_factory_provider -v
```

For an exact-ELF oracle, set `SDBZ_EU_BETA_ELF` and run:

```bash
python arika_native_factory_provider_extract.py /path/to/SLES_541.61
SDBZ_EU_BETA_ELF=/path/to/SLES_541.61 python -m unittest test_arika_native_factory_provider -v
```

The oracle SHA-256 guards the original beta ELF, verifies
**37 JAL words + 37 exact argument words**, compares the exact
set of sites against the prior canonical registry, checks all
26 literal targets and the 11 state-derived register sources,
and rejects false runtime-execution claims. The original executable
is not committed, copied into CI or needed to run deterministic tests.

Windows/Ubuntu CI runs the new tests alongside all existing editor,
native lifecycle and rendering tests. In addition to the original
readiness gates, a pass requires **37 unique classified sites,
26/9/1/1 counts, literal IDs in the eight-member set, and no
change to the 67 registered transition/child requests**.

## Boundaries for the next milestone

The source application for **35 of the 37** provider calls remains
**unassigned** until interprocedural caller/callback ownership is proven.
Two existing verified ID 1 `CAppWarning` vtable callbacks own the
provider calls at `0x003FABF8` (phase 3) and `0x003FAC30`
(phase 4), each addressing ID 2 `CAppCRISofdec`. These were
cross-checked against the canonical registry's existing
`cross_app_interactions` and app ID 1 base-vtable callbacks;
no other source ID is assigned by proximity. Some
callers are generic lifecycle functions and deliberately have no
unique application ID. Runtime traces remain necessary to distinguish
a reached `jalr`, a returned singleton/cached object, successful
initialization and actual displayed screen transitions.

The next useful task is instrumentation at `0x003F1C78`,
`0x003F1BE0`, root-pointer stores and lifecycle callbacks with
runtime-observed ID, parent/child fields, return pointer and frame
counter; it is **not** to invent more application IDs from proximity.
