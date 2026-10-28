# Scene editor performance patch

This patch focuses on CPU work and GPU resource churn during interactive editing.

## Changes

- `c_webgpu_renderer.set_project(..., geometry=False)` now reuses mesh buffers, instance records, and existing material bindings. It updates world matrices instead of recreating every instance and its GPU resources during transform edits.
- Removed the separate per-instance uniform buffer. Rendering uses lazily allocated per-material uniforms, so the extra buffer was never bound and only consumed GPU memory.
- Material bindings no longer duplicate just because the selected state changes. When a material's texture assignment changes, the previous binding uniform is retired instead of accumulating stale bindings.
- Explicitly destroy obsolete geometry buffers, textures, and instance uniform buffers when rebuilding or replacing a project.
- Cache world transforms and parent links in each viewport until `set_project` invalidates them. Gizmo-state calculation and selection-root discovery can reuse the same result.
- Cache hidden-node and selected-subtree sets in the renderer, avoiding repeated hierarchy walks on each redraw.
- Generate gizmo line geometry only when its state key changes, rather than rebuilding the Python geometry on every redraw.

## Validation

- `py_compile` passed for the edited modules and included tests.
- All 14 available gizmo/settings tests passed.
- Full scene-project tests could not run in this environment because the patch ZIP does not include `arika_stage_editor.py`. The current environment also lacks PySide6 and wgpu, so the Qt/WebGPU viewport could not be launched or benchmarked here.

No FPS improvement is claimed without a runtime benchmark on the target machine.
