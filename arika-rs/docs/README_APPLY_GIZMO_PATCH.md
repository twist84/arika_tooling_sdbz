# Arika scene editor — gizmo, settings and recent files update

Extract this archive over the existing `arika_dat_tools` directory. The archive contains only the editor files changed for this feature; it is not a replacement for the full research package.

## Settings and recent files

The editor now stores settings in `~/.arika/editor_settings.json` (Windows: `%USERPROFILE%\.arika\editor_settings.json`). It remembers recent stage and project files, the last open directory for each kind, and window/dock layout. Use **File → Open Recent → Stages** or **Projects** to reopen a recent file. Missing entries are disabled; **Clear Recent Files** clears the history.

The archive adds `arika_editor_settings.py` and its unit tests. Extract the ZIP over the existing `arika_dat_tools` directory, including the new module.

## Gizmo tools

- **T — Transform:** combined Move, Rotate and Scale handles.
- **G — Move:** X/Y/Z arrows, XY/XZ/YZ plane handles and view-plane movement.
- **R — Rotate:** X/Y/Z rings, view ring and trackball.
- **S — Scale:** axis handles, plane scaling and uniform scaling.
- Hover a handle to highlight it; drag to transform the selection.

## Transform controls

- **Orientation:** Global, Local, Normal (object-local fallback for object-level selection), Gimbal, View, Cursor and Custom.
- **Pivot:** Median Point, Active Element, Individual Origins and 3D Cursor.
- View menu can place the 3D Cursor at the active object, align its orientation to the active object, create/clear a custom orientation, or reset the cursor. Shift+right-click places the cursor on the Y-up ground plane. The top-right axis compass clicks to align ±X/±Y/±Z and drags to orbit.
- **X/Y/Z** constrains an active drag. Press the same axis again to switch the constraint to the global axis.
- Type numeric values during a drag: move distance in scene units, rotation in degrees, or scale factor (`2` doubles, `0.5` halves). Plane transforms accept comma-separated component values.
- **Shift** enables precision. **Ctrl** snaps to configurable Move, Rotation and Scale increments from the Snap menu.
- **Enter** confirms. **Esc** or right-click cancels and restores the pre-drag state.
- Selected top-level roots transform together; selected descendants follow their selected parent rather than receiving a duplicate transform. Outliner-locked active objects cannot be transformed. The Object Properties panel has independent Location/Rotation/Scale X/Y/Z lock toggles, and gizmo/property edits respect them.
- Each completed operation creates one Undo step.

## Persistence and limitations

Native stage roots continue to use the supported STG transform patcher. Imported character roots and other editable TRS nodes are stored in the project/glTF. Saving an STG copy does not write imported character placement or generic glTF-only edits. Global/local/view/gimbal/cursor/custom orientations are supported; Normal uses the object's local axes as the object-level fallback because this editor does not expose mesh-component selection. Non-uniform scaling of rotated objects is approximated in TRS because glTF node transforms cannot represent arbitrary shear exactly.

## Validation

`test_arika_gizmo.py` covers legacy handles, plane handles, view ring, trackball, uniform scale, combined Transform geometry and quaternion math. The modified Python files compile. Qt/WebGPU interaction cannot be exercised on systems without PySide6, rendercanvas, wgpu and a compatible GPU backend.
