# Stage GUI editor

Run `python arika_stage_editor.py` or double-click launch_stage_editor.bat on Windows. Python 3.9+ with Tkinter is required; no pip packages. An STG path can be passed as the first argument.

Open an extracted STG; sibling HIT collision is loaded automatically. Select nodes in the hierarchy or click a blue mesh-origin marker. Edit position, rotation in radians, and scale, then click Apply transform. Opaque control records remain read-only. Undo/Redo retain 100 committed edits. Save As patches only known transform bytes and refuses to overwrite the original opened file. Un-applied entry text is not saved or tracked by the unsaved-change prompt.

The orthographic map supports XZ/XY/YZ, wheel zoom, right-drag pan and Fit view. Green outlines are collision polygons; blue dots are mesh origins. This is not a textured 3D renderer. Preview drawing is limited to 5,000 polygons. Templates/effects can be included using the checkbox. Runtime visibility, spawning and destruction are not simulated.

Ctrl+O opens; Ctrl+S saves a copy; Ctrl+Z/Ctrl+Y undo/redo. Saved STG files require the existing archive replacement/repack workflow before use in game. Original bytes, names and opaque records are preserved outside edited transform fields. No collision vertices or model assets are modified.

Document edits, source preservation, saved-file reparsing and undo/redo have automated coverage. Interactive GUI behavior remains unverified because this environment has no display server. See STAGES.md for format and runtime limitations.

## Map editing and search

Drag a blue mesh-origin marker, or the selected node marker, with the left mouse button. A dashed guide shows the proposed move; release commits one undoable transform edit and rebuilds the collision map. World-space map movement is converted through the inverse parent transform, so rotated/scaled parents are handled. Singular parent transforms reject the move. Wheel zoom and right-drag pan remain available.

Use the hierarchy search box and Find next (or Enter) for case-insensitive name matching. Repeated searches cycle through matching nodes, including template/effect nodes. The hierarchy reveals the selected result even if that root is not currently included in the map. Interactive GUI testing remains pending in a graphical environment.

## Export and snapped dragging

Export glTF writes the committed in-memory scene directly, using the opened STG basename's sibling MDL, optional HIT and PIX files. Apply text-field edits first. No intermediate saved STG is required, and the source files remain unchanged. Export includes the separate authored stage/effect/template/collision scenes and retains their documented runtime limitations. Export runs synchronously and can briefly block the window on large stages.

Drag step sets a nonnegative spacing in native map units; zero disables snapping. Each drag displacement is rounded to the nearest step in the selected world/map plane before conversion through the parent transform. This is relative movement snapping, not absolute grid alignment. The dashed guide remains unsnapped; the committed result snaps on release.

## 3D viewport

The view selector now starts in 3D. A sibling MDL is loaded automatically: authored rigid mesh instances appear as shaded triangles, with collision edges overlaid. Left-drag orbits, right-drag pans and the wheel zooms. Click near a mesh origin to select it; selected mesh triangles are highlighted. Fit view reframes the scene. Missing MDL permits collision/origin inspection only.

This dependency-free Tk viewport uses orthographic projection and depth-sorted polygons, not a GPU/depth-buffer renderer. Textures, transparency, exact intersecting-surface occlusion and native visibility/shader effects are not reproduced. Meshes above 12,000 triangles are sampled; the status bar reports drawn/total counts. Collision remains capped at 5,000 polygons. Switch to XZ/XY/YZ for drag-to-move; transform fields and exports work in either mode. Interactive desktop testing remains pending; projection, world transforms and sampling have automated tests.

## 3D renderer correction

Install the image renderer dependency once: `python -m pip install Pillow`. The document editor and 2D maps still work without Pillow; 3D displays installation instructions if it is absent.

The default 3D path now keeps every mesh triangle. Earlier versions skipped faces for responsiveness, which caused visible holes. Rendering now batches the scene into one Pillow image instead of thousands of Tk polygon objects, caches vertex projection and face shading, skips off-screen faces, and coalesces redraw requests. The collision overlay is off initially and can be enabled in the inspector. Old triangle-sampling/default-overlay descriptions above are superseded by this correction.

This remains an untextured orthographic software renderer using painter sorting, not a depth buffer. Intersecting surfaces and transparent materials can still be incorrect. Performance depends on mesh size and viewport resolution; no Windows interactive frame rate has been measured here.

Depth ordering was also corrected: with the elevated orbit camera, larger camera-depth values are nearer and must draw last. A regression test checks overlapping near/far triangles.

## Default launcher changed

The standard stage-editor launcher now opens the Qt/WebGPU editor with World/Material Preview/Texture Browser views. Install requirements_scene_editor.txt. This document describes the older Tk implementation: use `python arika_stage_editor.py --legacy` to run that version. See SCENE_EDITOR.md for the current UI.
