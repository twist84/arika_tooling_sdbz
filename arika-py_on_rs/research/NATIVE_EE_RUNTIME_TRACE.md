# EU-beta native application runtime trace — M3 evidence capture

**Game:** Super Dragon Ball Z **EU beta**, original `SLES_541.61` (not EU retail)  
**Required ELF SHA-256:** `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`  
**Merged prerequisite:** #27, factory-provider arguments  
**Capture reader:** `../arika_native_ee_trace.py`  
**Empty capture template:** [native_ee_trace_template_eu_beta.json](native_ee_trace_template_eu_beta.json)

## Evidence this can establish

The original EE code contains two **real indirect factory call** instructions:

- `0x003F1C78`: **instance provider** `0x003F1C40`. It loads a
  factory from `0x006217E0 + 4 × ID` and calls it but does
  **not** install the active-root pointer.
- `0x003F1BE0`: **root installer** `0x003F1BA0`. It also calls a
  registered factory and subsequently writes its return pointer
  (or a fallback) to `0x0063BE38`.

An EE breakpoint *at a `jalr` before it executes* shows only that
the dispatcher **reached that instruction**. It does not prove that
the destination ran. A matched stop on the actual registered
factory's first instruction with the expected return address is
separate evidence of **entry**. Similarly, a pre-`sw` breakpoint
does **not** prove that global memory changed. The import reader
accepts a root-store event only when memory has been observed
**after** the write.

Even a confirmed factory entry does **not** prove a new allocation:
a constructor/factory may return a singleton, reuse an existing
instance or fail. Even a confirmed active-root write does **not**
prove that a visible screen was presented. The existing Qt preview
still **does not** run the original ELF.

## Debugger setup and capture sites

PCSX2's built-in debugger supports R5900 disassembly, registers,
memory and breakpoint inspection. In supported PCSX2 versions,
enable **Tools → Show Advanced Settings**, open
**Debug → Open Debugger**, and select the **R5900** layout.
See [official PCSX2 debugger documentation](https://pcsx2.net/docs/advanced/debugger/).

Generate **navigation symbols** from the 47 verified EU-beta
factory addresses and nine critical debugger locations:

```bash
cd arika-py_on_rs
python arika_native_ee_trace.py --write-pcsx2-symbols research/eu_beta_factory_trace.sym
```

Use PCSX2's **Analysis Options → Import Symbols** functionality for
that `.sym` file if your build exposes it. A symbol import adds
labels, **not breakpoints, logging, or an automatic runtime hook**.
Choose the **EE/R5900**, not the IOP debugger.

| Breakpoint or memory watchpoint | Register / memory to observe | Meaning |
|---|---|---|
| Entry `0x003F1BA0` | `a0` (low byte); `ra` | Root handoff entry; `ra=0x003DFF3C` indicates the recovered phase-5 scheduler caller |
| **Before** `jalr` `0x003F1BE0` | `s0` (low byte), `v0` | Root installer reached indirect factory call; **not yet entered** |
| **Before** `jalr` `0x003F1C78` | `s0` (low byte), `v0` | Instance provider reached factory call; **not yet entered** |
| Actual factory entry `0x003F2D20` for ID 3, or any of the 47 `.sym` factory labels | current `PC`, `ra` | Confirms entry only when matched to in-flight dispatcher; `ra=0x003F1BE8` for root, or `0x003F1C80` for provider |
| After return `0x003F1BE8` or `0x003F1C80` | `v0` | Factory-returned pointer; may be zero or cached |
| **Write observation** at global `0x0063BE38` (store `0x003F1C04` or branch-delay store `0x003F1C30`) | resulting 32-bit memory value, stored `a0` | Confirms installed active-root pointer **only after the write committed** |

For `0x003F1C04` and `0x003F1C30`, do **not** mark an
ordinary instruction breakpoint as `post_write`. If the debugger
stops *before* the store, step far enough for the instruction
(including any MIPS delay-slot semantics) to commit, then read
`[0x0063BE38]` and the stored `a0`. Only then record a
`root_write`. A memory-write watchpoint is useful only when you
have verified whether your specific debugger reports the state
before or after the write.

### Event schema

The importer reads a **single JSON object**:
`format`, exact `elf_sha256`, `source`, and `events`.
The `source` may be `pcsx2-ee-debugger` (manual debugger),
`pcsx2-ee-gdb` (GDB-based capture), or
`synthetic-test-fixture` (unit tests, **never** runtime proof).
Each event requires a strictly increasing integer `sequence`.
All register and pointer values may be unsigned 32-bit integers
or `0x`-prefixed hexadecimal strings. When reading the 128-bit
R5900 general registers, record only their relevant **low 32 bits**.

These are the five event kinds:

1. `root_handoff`: `pc=0x003F1BA0`,
   `registers.a0`, `registers.ra`.
2. `factory_dispatch`: `pc=0x003F1BE0` (root)
   or `0x003F1C78` (provider); `registers.s0` is the
   incoming ID saved by the native routine and `registers.v0`
   is the actual indirect factory target. For IDs 1–47 the
   captured target must match the original registry.
3. `factory_entry`: `pc` is the **actual first instruction**
   of the target factory, and `registers.ra` is the
   matching post-`jalr` return PC. The importer matches the
   most recent outstanding dispatcher (including nested calls).
4. `factory_return`: `pc=0x003F1BE8` or `0x003F1C80`,
   with `registers.v0` recording the object pointer returned
   by the factory (zero allowed). A return without its dispatch
   is explicitly labelled **unpaired**.
5. `root_write`: `store_pc=0x003F1C04` or
   `0x003F1C30`, `address=0x0063BE38`,
   `value` is the **post-write** memory value,
   `registers.a0` is the stored value, and
   `post_write=true`. Both values must agree.

Do **not** include an event merely because disassembly reveals
the corresponding instruction. The events are observations from
a live original-game debugger session.

### Worked example — synthetic ONLY

The following numbers demonstrate JSON serialization and state
correlation; **they are not an observed game trace**:

```json
{
  "format": "sdbz-eu-beta-ee-factory-trace-v1",
  "elf_sha256": "80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0",
  "source": "synthetic-test-fixture",
  "events": [
    {"sequence": 1, "kind": "root_handoff", "pc": "0x3f1ba0",
     "registers": {"a0": "0x3", "ra": "0x3dff3c"}},
    {"sequence": 2, "kind": "factory_dispatch", "pc": "0x3f1be0",
     "registers": {"s0": "0x3", "v0": "0x3f2d20"}},
    {"sequence": 3, "kind": "factory_entry", "pc": "0x3f2d20",
     "registers": {"ra": "0x3f1be8"}},
    {"sequence": 4, "kind": "factory_return", "pc": "0x3f1be8",
     "registers": {"v0": "0x123450"}},
    {"sequence": 5, "kind": "root_write", "store_pc": "0x3f1c04",
     "address": "0x63be38", "value": "0x123450",
     "registers": {"a0": "0x123450"}, "post_write": true}
  ]
}
```

Copy [the **empty template**](native_ee_trace_template_eu_beta.json),
not the synthetic demonstration, for a real capture. Change its
`source` only when recording genuine debugger observations.
The `0x123450` object pointer above is made up solely for the
synthetic example; **do not** interpret it as a recovered game pointer.

## Import and analysis

Run the validator on the debugger JSON file:

```bash
cd arika-py_on_rs
python arika_native_ee_trace.py path/to/your_ee_trace.json
python -m unittest test_arika_native_ee_trace -v
```

The validator rejects wrong-version hashes, impossible factory
targets, wrong return PCs, out-of-order events and attempts to
claim uncommitted writes. It tolerates sparse manual traces but
labels unmatched returns and incomplete dispatches. Both
provider and root dispatches are tracked through nested
factory calls in last-in/first-out order.

Inside **Arika Editor → Menu → Screen Flow**, the new
**Import EE trace** action reads that JSON file and shows
the reported matched factory-entry and active-root-write counts.
It is **read-only**: it never drives the original ELF,
invents an application transition, changes tabs, or
resets the six existing preview widgets.

Import results are explicitly user-reported: the tool can
check internal consistency and compare against the exact
static registry, but it cannot authenticate the debugger
source or prove a trace was produced by PCSX2.

## Acceptance and remaining work

- All 47 original factory addresses and nine useful debugger
  sites are exportable as PCSX2 `.sym` navigation labels.
- A pre-`jalr` stop alone yields **zero** verified factory
  entries; an exact matched target-PC and `ra` pair yields
  an entry observation.
- Only an observed memory value **after** the original
  `sw` instruction counts as an active-root write.
- Root invalid-ID fallback `0x005E1AC0` and
  null-return fallback `0x004FCAD4` remain distinct.
- The trace importer does not assert new object
  allocation, visible pixels, splash completion or
  parent/child restoration beyond observed events.
- Tests run on both Windows and Ubuntu with **synthetic
  fixtures**, requiring no proprietary ELF or emulator.

**Still needed:** a real EE debugger recording from the original
EU-beta game, coverage of actual startup sequence/factory execution
and a before/after GS frame comparison. The infrastructure here
makes that evidence comparable and actionable without falsifying
a runtime trace.
