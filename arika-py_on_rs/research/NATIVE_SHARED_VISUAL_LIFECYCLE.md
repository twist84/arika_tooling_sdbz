# EU-beta native shared visual lifecycle and 2D draw ordering

ELF: `SLES_541.61` (EU beta, 2006-05-02), SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
All addresses are EE virtual addresses. Only derived code/metadata is
committed, not the executable, image archives, TIM2 or proprietary textures.

## Ownership and update order (native code)

`0x377A10` constructs the shared visual object: its banner subobject
at shared +`0x100` is initialized by `0x3783C0`, its tile/companion
owner at shared +`0x180` by `0x375F90`, and the seven small objects
by `0x377BA0`. Shared phase is +`0xD0`, subphase +`0xD4`,
age +`0xD8`, started count +`0xDC`, overlay hidden byte +`0xE0`,
overlay alpha +`0xAC`, and small-object pointers +`0xE4`
through +`0xFC`.

```text
0x379A40 outer update
  -> 0x377DE0 shared update, only while shared phase != 0
     -> 0x378480 banner update (shared +0x100)
     -> 0x376080 tile/companion owner update (shared +0x180)
     -> 0x376AC0 small update (small pointers 0..6)
     -> 0x377F40 shared overlay-alpha update
     -> shared phase callback
          phase 1, subphase 0:
             -> 0x3786F0 banner start
             -> 0x376390 tile/companion owner start
          phase 1, subphase 1:
             -> 0x376C70 small start per seven native age thresholds
          phase 3, subphase 0:
             -> 0x378700 banner exit
  -> pending item and selected item updates
  -> inner update
```

The start/exit callbacks occur **after** the current update's banner,
owner and small passes. This timing is observable in the first step
and must not be simulated by advancing a child again after its start.
The shared state machine is already instruction-oracle-tested in
`test_arika_menu_shared.py`; the banner's update, interpolation,
start and exit are instruction-oracle-tested in
`test_arika_menu_banner.py`; and all seven small-component kernels
are covered by `test_arika_menu_small.py`.
`test_arika_menu_shared_visual_runtime.py` verifies their integration
and continued independence from the authored diagnostic frames.

## Native fields and curves reused in the editor

| Object | State fields | Native values |
| --- | --- | --- |
| Banner | subobject +0x70 phase, +0x74 age, +0x78/+0x7C XY | initial (-512,0), base (0,16), texture entry 2, UV XYWH (0,256,264,48), depth 99 |
| Banner entry | curve arrays at GP-0x4CF0 / GP-0x4CE8 | age 0→10, X -256→0 |
| Banner exit | curve arrays at GP-0x4CD8 / GP-0x4CD0 | age 0→5, X 0→-256 |
| Small (each) | +0x04 phase, +0x08 age, +0x70/+0x74 offset, +0x78/+0x79 direction | seven independently recovered bases, UVs, directions; texture entry 3, depth 5 |
| Small entry | shared approach curve and 13-key bounce curve | approach age 0→5, displacement 256→0; bounce age 0→12 using [0,3,6,3,0,2,4,2,0,1,2,1,0] |
| Tile owner | +0x70 phase, +0x74 owner age, +0x78 tile phase, +0x7C/+0x80 offset, +0x84 event timer | base (0,320), two 512×128 quads, texture entry 2, depth 85, scroll period 2048 |
| Shared overlay | shared +0xE0 hidden flag, +0xAC alpha | native target alpha 0.5, rate 0.1 per update while enabled |

The seven independent small start thresholds are [10,30,40,20,25,35,15]
in slot index order. Therefore the native start order is
0, 6, 3, 4, 1, 5, 2. These are instruction-recovered scheduler
constants; they are **not** the authored reference timeline.

## Native draw path: `0x379E60 -> 0x378170`

```text
0x378170 shared draw
  -> first fixed background sprite (shared +0x10)
  -> 0x3786A0 banner draw (shared +0x100)
  -> 0x376290 tile draw (shared +0x180)
     -> first tile draw, then second tile draw at +512 X
     -> 0x3763B0 global companion handle
     -> 0x376600 ten-slot companion draw (0x376950 per slot)
  -> 0x376C20 for each of seven small pointers
     -> vtable +0x30 only when small phase != 0
  -> if shared +0xE0 == 0:
       second fixed overlay sprite (shared +0x70)
```

The companion draw was integrated in the previous checkpoint. This
milestone connects the remaining shared visual children to the
scheduler: `step_shared` now sends banner start/update/exit and seven
small start/update callbacks into their recovered state machines;
tile rendering reads the **same owner +0x78 tile phase** used by the
companion event system. `shared_banner_geometry`,
`shared_tile_geometry`, `shared_small_geometry`, and
`companion_geometry` are read-only. Qt native mode draws their quads
from state, and draws the overlay from shared +0xE0/+0xAC rather than
the 140-sample diagnostic frame. The normal diagnostic timeline and
pose matcher remain independent.

The editor still uses the existing recovered background/tint geometries
and retains a depth-sort approximation for backend compositor ordering.
The frame-independent native state does not imply exact GS blending,
pixel sampling, video mode, or a captured live context RNG seed.
Unseeded runtime replay can still recover banner/small logical clocks
but cannot invent an unknown companion-owner RNG/tile-phase state.

## Validation and remaining work

- Existing tests for banner, shared scheduler, tiles and seven small
  sprites compare native EE instruction outputs.
- `test_arika_menu_shared_visual_runtime.py` exercises joined parent
  entry/exit/idle, native child callback order, banner/small state
  evolution, tile scroll wraps, draw geometry and pure snapshots.
- Offscreen Qt tests with synthetic images validate visible native
  banner/tile/small/overlay movement, and prove replacing authored
  frame contents cannot alter native draw geometry.
- No game textures or ELF binaries are checked into the repository.

Further recovery: independently verify the full `0x378170` draw
compositor, especially native GS blend/depth/write flags and texture
sampling. The ten-slot event RNG consumes one shared diagnostic stream
with DRAGON SUMMONING; the real-game stream seed and other consumers
remain unobserved. Do not mark native mode pixel-perfect until verified
against a real in-game capture and hardware/PCSX2 state.
