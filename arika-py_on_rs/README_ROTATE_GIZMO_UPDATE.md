# Rotation gizmo update

This update adds true local-axis rotation composition to the scene editor gizmo.

- Select **Rotate** in the toolbar or press `R`.
- Drag the red, green, or blue ring to rotate around the selected object's local X, Y, or Z axis.
- Hold `Shift` for precision rotation and `Ctrl` to snap in 15-degree increments.
- Rotation is composed through quaternions before being converted back to XYZ Euler fields, so rotating an already-rotated object does not merely increment one Euler component.

Apply by extracting this patch over the existing `arika_dat_tools` directory. The update contains the editor, gizmo helper, focused tests, and this note.
