# Lightweight WebGPU scene editor

The new editor is `arika_scene_editor.py`. Install Python 3.10+ and dependencies, then launch:

```sh
python -m pip install -r requirements_scene_editor.txt
python arika_scene_editor.py
```

Windows also has `launch_scene_editor.bat`. The old Tk `arika_stage_editor.py` remains available separately.

## Workspace

Open an extracted STG with matching sibling MDL/PIX and optional HIT. The central viewport renders the full rigid stage meshes, authored transforms, UVs and decoded PIX textures. There is no triangle skipping. A scene outliner and object/material property tabs provide a smaller, focused workflow than a general modeling suite.

Middle mouse drag orbits; Shift + middle mouse pans in the camera plane; Ctrl + middle mouse dollies; wheel zooms. Left click selects without rotating the view. Alt + left mouse provides the same navigation for two-button mice (Shift pans, Ctrl zooms). Right click during a navigation drag cancels it. Home or Fit frames the stage; numpad period frames the selected object or group. Numpad 1/3/7 select front/right/top orthographic views, with Ctrl selecting the opposite side. Numpad 5 toggles perspective/orthographic, 2/4/6/8 orbit in 15-degree steps (Ctrl pans), 9 reverses the view, and numpad +/- zoom. Click inside the viewport before using shortcuts; text fields retain normal typing. Stage coordinates remain Y-up. These are Blender-style navigation controls. The top-right axis compass clicks to align to ±X/±Y/±Z and dragging its empty area orbits the view. Shift+right-click places the 3D Cursor on the Y-up ground plane. Select an unlocked object to show the transform gizmo. Use the combined Transform tool (T), Move (G), Rotate (R), or Scale (S). Move includes axis arrows, XY/XZ/YZ plane handles and a view-plane handle; Rotate includes three axis rings, a view ring and trackball; Scale includes axis handles, plane handles and uniform scaling. Hover highlights a handle. Multi-selection transforms selected top-level roots together. The orientation selector provides Global, Local, Normal, Gimbal, View, Cursor and Custom; the pivot selector provides Median Point, Active Element, Individual Origins and 3D Cursor. Use View > Set 3D Cursor to Active and Align 3D Cursor Orientation to Active to position/orient the cursor; Create Custom Orientation from Active and Clear Custom Orientation manage a custom basis. X/Y/Z constrain a drag, numeric entry types exact move units, rotation degrees or scale factors, Shift enables precision, and Ctrl snaps using increments configured from Snap. Right-click or Esc cancels a transform; Enter confirms it. A completed gizmo operation is one Undo step. Locked active objects cannot be dragged. The Object and World views share the selected object's transform; the material preview has no gizmo. Click a rendered mesh to select it using a GPU object-ID attachment. The outliner also selects nodes and filters by name. Edit known position/rotation/scale fields and click Apply transform. Rotation fields use radians. Selected objects receive an orange tint. Textured, Solid and Wireframe modes and a collision toggle are in the toolbar. Collision is disabled initially.

The material tab lists materials, previews their texture thumbnails, assigns existing textures or no texture, changes base tint/alpha, selects opaque/masked/blended alpha, and controls double-sided rendering. Select a mesh's material slot to locate it in the list. Import image embeds a PNG into the project; select it and click Apply material to assign it. Changes affect every primitive sharing that material.

This viewport is an unlit base-color/texture preview. It does not reproduce PS2 shader logic, vertex color effects, reflections or native stage visibility/destruction. Blended materials currently use submission order rather than full transparency sorting. It is not a mesh topology editor, animation suite, or complete Blender replacement.

## Saving

Save project writes a self-contained `.arika-scene.json`: embedded geometry, textures, edited materials, original STG bytes and committed STG transform edits. Open project restores it without requiring the original assets to render. Undo/Redo cover committed transform, material and image edits, with a 20-step project history. Unapplied property-panel changes are not committed; click Apply first.

Export glTF includes material/image and transform edits. Save STG copy writes only the native transform edits and preserves original STG bytes outside the known fields. Material/image edits are project/glTF data: this editor does not write them back to native MDL/PIX. Save the project to retain them. Saving an STG copy alone does not save the material work. Source STG/MDL/HIT/PIX paths are protected from project/export overwrite.

The included `examples/stage_s00.arika-scene.json` can be opened directly to try a small textured scene.


## 3D transform gizmo

The World and Object viewports support a Blender-style combined transform gizmo and separate Move, Rotate and Scale tools. Move provides X/Y/Z arrows, XY/XZ/YZ plane handles and view-plane movement. Rotate provides local/global axis rings, a camera/view ring and a trackball. Scale provides axis handles, plane handles and uniform scaling. Hover feedback highlights the active handle. Use T for combined Transform, G for Move, R for Rotate and S for Scale. X/Y/Z constrain an active drag; numeric entry accepts move distances, rotation degrees and scale factors. Shift slows interactive changes; Ctrl snaps using configurable increments from the Snap menu. Right-click or Esc cancels; Enter confirms. Each completed transform is one Undo step.

Gizmo edits respect Outliner locks and operate on selected top-level roots so a selected parent does not apply the same drag twice to its descendants. Transform orientation options are Global, Local, Normal (object-local fallback for object-level selections), Gimbal, View, Cursor and Custom. Pivot options are Median Point, Active Element, Individual Origins and 3D Cursor. The cursor can be moved to the active object, placed on the ground plane with Shift+right-click, and aligned to its orientation from the View menu. Object Properties include independent Location/Rotation/Scale X/Y/Z lock toggles; locked components are retained by the property editor and respected by gizmo drags. Snap increments are configurable independently for move, rotate and scale. A cancelled drag restores the original snapshot; a completed drag is one history operation. Native stage roots continue to patch supported STG transform fields; imported character roots and other editable TRS nodes are stored in the editor project/glTF. Save STG copy does not write imported character placement or generic glTF-only node edits.


## Renderer

The renderer uses Python wgpu / wgpu-native and rendercanvas inside Qt. It selects D3D12 on Windows, Vulkan on Linux and Metal on macOS. Only these backends are accepted; no OpenGL fallback exists. Geometry and texture mipmaps are uploaded and cached. Camera changes update a uniform; transform/material changes can reuse geometry. New images, project loads and Undo/Redo currently rebuild resource caches and may pause briefly on large scenes.

Windows uses native screen presentation. If the window surface has platform-specific problems, set `ARIKA_PRESENT_METHOD=bitmap` before launching; this retains WebGPU rendering and changes only Qt presentation. Linux defaults to bitmap presentation. A compatible graphics driver/backend is required. Backend initialization errors appear in the status bar and console.

Framework references: https://rendercanvas.readthedocs.io/stable/backends.html and https://wgpu-py.readthedocs.io/ .

## Validation limits

Project tests cover material assignment, image embedding, undo/redo, save/load/export, transform preservation, invalid values, source protection and rejection of external project buffer URIs. Pure gizmo tests cover axis arrows, plane/view-plane handles, uniform scale, view rotation, trackball geometry, combined Transform handles and quaternion/Euler round-trips. The real Qt/rendercanvas event loop is tested offscreen with a substitute renderer: initial world drawing, scene upload, camera redraw, material preview and visible error reporting. Camera projection is tested independently. Native WebGPU rendering could not be exercised on this host because no suitable Vulkan adapter/ICD is installed. No Windows frame rate or screenshot has been verified. The prior OpenGL experiment was removed after the requested backend change; its screenshots and validation report are not evidence for this version.

Blank viewport fix: both viewports now create their WebGPU canvas context before scheduling drawing. rendercanvas skips the drawing callback when no context exists, so creating the context inside that callback previously prevented the renderer from ever starting. A loaded scene now reports its mesh instance count in the status bar; adapter/render failures report a WebGPU error there and in the console.

## World, material and texture views

The view selector now has World, Material Preview and Texture Browser. World has explicit Textured World, Solid World and Wireframe World modes, defaulting to Textured World. Material Preview uses a separate WebGPU viewport with a UV sphere and the selected material; changing and applying material settings updates this preview and the world. It is an unlit base-color/texture preview, not a physically based lighting sphere.

The bottom Asset Browser is a texture icon shelf. Selecting a texture opens its large image view with dimensions, checkerboard transparency, wheel zoom and drag pan. Browsing does not change material assignment. To assign a texture, use the material's texture dropdown and Apply material.

`launch_stage_editor.bat` and `python arika_stage_editor.py` now launch the WebGPU editor too. The earlier untextured Tk application is available only through `launch_legacy_stage_editor.bat` or `python arika_stage_editor.py --legacy`. A screenshot labelled Arika stage editor with 'untextured diagnostic view' shows that legacy application.


## Blender-style layout

The default Layout workspace keeps the 3D viewport wide, with the Scene Collection / Outliner at the upper right and Properties directly below. Object Properties groups Location, Rotation and Scale into X/Y/Z rows; rotations remain radians. Properties scroll when the window is small. The bottom Asset Browser shows texture thumbnails and can be resized, closed or undocked. This is an asset shelf rather than an animation timeline.

The top workspace tabs select Layout (world), Shading (material preview and Materials Properties), and Textures (image editor). The viewport header retains the view selector, framing menu, display mode and collision toggle. Both selectors stay synchronized. Selecting a shelf texture opens it in the Textures workspace without changing material assignments.

File contains open/save/export actions; Edit contains Undo/Redo. Shortcuts include Ctrl+O (stage), Ctrl+Shift+O (project), Ctrl+S (save project), Ctrl+E (export), Ctrl+Z and Ctrl+Shift+Z. Window lets you reopen panels or Reset layout. Help shows the viewport controls. Panel sizes are adjustable by dragging their borders. All existing WebGPU rendering and Blender-style navigation controls are retained.

Layout placement, workspace switching, image selection, material preview setup, panel reopening, menu actions and a smaller window are checked through Qt offscreen tests. The interface layout was visually inspected offscreen with a substitute renderer; this does not constitute native GPU rendering validation.

Transform field display fix: numeric fields retain their native step buttons. With styled Qt spin boxes, hiding those buttons could collapse the internal text area to one pixel and make loaded values invisible. The layout test now checks all nine text areas at normal and reduced window sizes and types a replacement value into a selected object field.


## Multiple selection

Left click in the viewport replaces the selection. Shift+click (or Ctrl+click) adds or removes an object. Click empty space to clear; modified empty clicks preserve the selection. The Outliner uses extended selection: Ctrl+click toggles individual rows and Shift+click selects a range. Viewport and Outliner selections stay synchronized. A selects all scene rows; Alt+A or Esc deselects when the viewport or Outliner has focus. Text fields retain their normal editing shortcuts.

Selected meshes are tinted together; selecting a group also highlights its descendant meshes. Numpad period frames the combined selection and descendants. The status bar reports the number selected. Properties identifies the active object (normally the last selected); Apply active transform edits that object's local transform only. Multi-object transforms and shared-pivot manipulation are not implemented. Material edits retain their existing shared-material behavior. Selection survives Undo/Redo/project refresh and resets when opening another scene.

Selection tests exercise viewport Shift-click, toggle-off, empty-space clearing, native Outliner Ctrl-click, tree/viewport synchronization, select/deselect shortcuts, combined bounds framing, refresh preservation and group highlight expansion.


## Visibility and transform locks

Each Outliner row now has **Show** and **Lock** checkboxes. Show checked means visible; Lock checked means its local transform cannot be edited. Objects default to visible and locked, including older projects without these flags. Uncheck Lock before editing an object's transform. Locked objects can still be selected and inspected. This is a transform lock, not a material lock: material editing retains its shared-material behavior.

Toggling either checkbox on a group applies that state to its descendants. Right-click selected Outliner rows for Hide/Show selected and Lock/Unlock selected; the same menu has Show all objects and Lock all objects. Checkbox toggles target that row and descendants, while menu commands target the whole selection. H hides selected objects and Alt+H shows all, with the viewport or Outliner focused.

Hidden objects and hidden-group descendants are omitted from world rendering, picking and framing. They remain in the Outliner so they can be shown again. Hiding and locking do not modify STG bytes or native game assets. These editor states are stored in node extras in the project (and exported glTF metadata); ordinary external glTF viewers need not honor the editor visibility flags. Material sphere previews stay visible. States survive project save/load and Undo/Redo. A prior explicit unlock saved in a project remains unlocked when reopened.

Tests cover default locks, keyboard read-only fields, the Apply guard, checkbox toggles, hidden-object picking rejection, visible-only framing, hidden-parent inheritance, save/load, Undo/Redo and invalid state inputs. GPU rendering remains subject to the renderer validation limits above.


## World and Object view options

The viewport header now has a **Viewport** menu with floor grid, world axes, selection highlight, backface culling, orthographic projection and a background color picker. Grid spacing adapts to camera distance; the floor is the world X/Z plane. Axes are X red, Y green (up) and Z blue. World and Object views default to grid and axes enabled; the material sphere preview keeps them disabled. Guides do not receive object IDs. Shading remains an unlit base-color/texture preview, not Blender's lighting or PBR renderer.

The **View** menu adds Front/Back/Right/Left/Top/Bottom orthographic views alongside framing. **Numpad /** or View → Toggle Local View isolates the current selection in the current viewport, including selected groups' descendants; toggling again returns to the full scene. Hidden nodes remain hidden. Framing and picking respect the isolated scope. Local View changes no saved visibility flags.

The **Object** workspace (also Object View in the view selector) is a separate viewport for the selected object or group of objects. Select in the Outliner or World, then switch to Object. Its isolated scope follows the shared selection. With no selection it shows only enabled guides; select an Outliner row to populate it. Textured/Solid/Wireframe, collision, projection, background, guides, camera and highlight controls act on the active viewport, independently of World. Object cameras use the authored world transforms rather than modifying geometry to recenter it. Active-object transform locks and shared-material editing still apply. Transform/material/image changes refresh both world and object previews.

Viewport display settings and Local View are session settings, not project data. Hidden and locked flags still save with the project. Inactive WebGPU viewports defer initialization/uploads until shown, and redraw when made visible. Each initialized viewport maintains its own GPU resources; Object View can therefore increase GPU memory use.

Tests cover workspace routing, independent display settings, projection/alignment, Local View toggling, isolated bounds/picking and grid/axis geometry. The layout was inspected offscreen with a substitute renderer. This host has no compatible native graphics adapter, so the new GPU guide draw pass and Windows performance remain unverified here.

Background color accuracy: picker values are stored as display sRGB. The renderer decodes those values before clearing an sRGB attachment, avoiding a second encoding that made colors too bright. Plain UNORM attachments use the picked values directly. The prior default appearance is preserved on sRGB surfaces. Regression tests round-trip the reported RGB (32, 162, 212), gray, primaries and transfer thresholds, and capture the render-pass clear descriptor for both attachment formats without requiring a GPU.


## Characters in a stage

Open a stage or editor project, then choose **File → Add character…**. Supported inputs are native FMDL `.mdl` with matching FPIX `.pix`, or glTF/GLB. A sibling `.pix` is used automatically; if missing, an optional file picker lets you choose it or continue untextured. The mesh-variant dialog lets you omit alternate hands, costumes and hair that would otherwise overlap. Importing all variants does not reproduce the game's variant selection logic.

**File → Add example Goku** imports the included researched Goku body, hair, prepared face and default hand variants. It is a quick way to try character placement. Native body models do not automatically assemble separate facial assets; use a prepared character glTF for combined facial geometry, as the included example does.

The new character root appears in the Outliner and opens in Object View. It starts locked like other objects. Uncheck its Lock box, then edit Location/Rotation/Scale and Apply active transform. Initial placement uses the world camera's X/Z center with Y=0, without rescaling native units. Root transforms affect all its mesh children. Show/Lock, multi-selection, Local View and framing work as usual. Switch to Layout to see it in the stage. Imported source model/texture paths are protected from project/export overwrite.

Characters are **static authored-pose previews**. Skinning is baked on the CPU using joint world matrices and inverse bind matrices, with up to four nonnegative normalized influences per vertex. Authored default morph weights are baked too. The imported preview keeps embedded positions, UVs, indices, base-color textures and basic alpha settings; skeletons, animation tracks, normals, vertex colors and PS2 material effects are not editable/preserved by this preview import. Native negative skin weights use the existing exporter's clamping approximation. glTF sparse accessors, compressed/required extensions, non-triangle primitives and more than four skin influences are unsupported and rejected.

Save project keeps character instances and placement. Export glTF includes the static character meshes. **Save STG copy does not spawn characters in the native game**; native stage bytes are preserved except for existing supported stage transform edits. Adding and moving characters supports Undo/Redo.

Tests cover native FMDL decoding, rigid transforms, skin/inverse-bind baking, buffer/accessor remapping, example Goku and face textures, actor locking/placement, save/load, Undo/Redo and original stage-byte preservation. The Qt test adds example Goku through the actual menu handler and edits its unlocked root. Rendering on this host is still limited by the lack of a native GPU adapter.


## Deleting objects

Unlock the selected objects first, then press **Delete** or **X** with the viewport or Outliner focused. The Outliner context menu and Edit menu also offer Delete selected. Deleting a group deletes its descendants. If any targeted object or descendant is locked, the entire deletion is blocked; use Unlock selected to unlock the subtree. There is no confirmation dialog because Ctrl+Z restores the operation.

Deletion removes nodes from the editor hierarchy and updates scene roots, children and any optional skin/animation node references. It clears the selection and remaps a remaining Local View scope. Ctrl+Z restores the deleted subtree; Ctrl+Shift+Z deletes it again. Mesh/material/texture resources may remain unused in the project and are not compacted. Numeric fields keep normal Delete behavior, and keypad Delete/decimal retains viewport framing.

Save project and Export glTF retain object deletion. **Native STG deletion is not implemented**: Save STG copy still writes only the supported native transform edits, so deleted editor objects remain in the native stage. The delete status message and STG save message state this distinction.

Regression tests cover subtree deletion, node-reference remapping, save/load, Undo/Redo, mixed locked selections, locked descendants, invalid indices, empty scenes, referenced-joint protection, real Delete key routing, text-field safety and keypad framing safety.

## Editor settings and recent files

The editor stores user-level preferences in `~/.arika/editor_settings.json` (on Windows, `%USERPROFILE%\\.arika\\editor_settings.json`, for example `C:\\Users\\User\\.arika\\editor_settings.json`). The `.arika` directory is created automatically. The JSON stores up to 12 recent stage and project paths, the last-used open directory for each file type, and the main window geometry/dock layout. Missing or malformed settings are ignored and defaults are used; writes are atomic.

Use **File → Open Recent → Stages** or **File → Open Recent → Projects** to reopen either kind. Existing files are selectable; entries whose files have moved or been deleted are shown disabled. **Clear Recent Files** clears only the recent-file list. Opening a stage, opening or saving a project, and saving a native STG copy update the relevant recent list. A project can also be opened from the command line by passing its `.arika-scene.json` path; other command-line scene paths are treated as STG stages.
