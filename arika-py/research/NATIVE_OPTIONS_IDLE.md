# OPTIONS circular idle

Report version 23 adds item 6 to `character_idle`. `step_circular_idle` implements its clock, angle curve and circular offset for both character parts. The textured viewer now offers idle motion for six items; DRAGON SUMMONING remains pending.

## Native evidence

The callback is `0x0037FC00`, with its two X/Y offset pairs at component +320 through +332. It increments float age by one and subtracts 240 once when age is at least 240. Two angle values at `0x004FA868` are (0, float32(2*pi)); times at `0x004FA870` are (0,240). The sample-count byte at GP-19192 is two. The radius at `0x004FA860` is 5.

The interpolated angle is passed to `0x001859D8` (cosine) and `0x00185C78` (sine). Their small-angle kernels confirm the identities: cosine kernel `0x00183DE0` returns 1 near zero; sine kernel `0x00184798` returns its input near zero. Both part pairs receive X = 5 - 5*cos(angle), Y = 5*sin(angle). These offsets add to the existing base/placement coordinates; the part geometry and depth ordering are otherwise unchanged.

## Trigonometry scope

The callback's clocks, curve sampling, trig-call arguments and coordinate arithmetic are reconstructed from the native instructions. The preview evaluates sine/cosine using host math rounded to float32. It does **not** claim native libm bit equivalence, PS2 FPU accuracy or emulation of the game's complete argument-reduction kernels. This distinction is recorded in the report component's `trig_model` field and trace limits.

The API accepts injected cosine/sine functions so the surrounding native arithmetic can be tested independently. This is important because comparing two uses of host math would not validate the native library implementation.

## Integration and validation

`examples/menu_character_idle_trace.json` includes OPTIONS motion, and the viewer's idle toggle compares it with zero per-part offsets. The existing authored activation and exit schedule remains unchanged: idle starts after entry at sample 22; its last offsets are retained during exit. The 240-update period is an update count, not a measured wall-clock duration.

All 84 menu tests pass. New cases execute 400 actual native callbacks and the native interpolation helper with controlled trig returns, checking the updated clock, both trig arguments and all four part-offset float bits. This validates the callback around the math calls, not the native sine/cosine internals. Separate host-trig checks verify the four quadrants, identical offsets for both parts and full-cycle wrap. Prior linear/coupled idle and geometry tests continue passing.

The actual HTML JavaScript Canvas validator also checks that the OPTIONS idle toggle changes the rendered parts. Full-browser playback remains untested. Next: DRAGON SUMMONING's combined trigonometric idle, native trig fidelity if required, emphasis and actual selection scheduling.
