//! Arika Editor — Bevy + egui: load FMDL / STG, simple translate gizmo.

use arika_core::models::{attach_textures, parse_fmdl, Mesh as ArikaMesh};
use arika_core::stages::{
    parse_stg, stage_instances_filtered, stage_world_matrices, Stage, StageInstance, StageNode, parse_hit,
};
use bevy::prelude::*;
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::render::settings::{Backends, RenderCreation, WgpuSettings};
use bevy::render::RenderPlugin;
use bevy::render::mesh::{Indices, PrimitiveTopology};
use bevy::render::render_asset::RenderAssetUsages;
use bevy_egui::{egui, EguiContexts, EguiPlugin};
use egui_dock::{DockArea, DockState, Style, TabViewer};
use clap::Parser;
use std::collections::HashMap;
use std::path::PathBuf;


#[derive(Parser, Debug)]
#[command(name = "arika_editor", about = "Bevy + egui Arika stage/model viewer")]
struct Args {
    #[arg(long, short = 's')]
    stg: Option<PathBuf>,
    #[arg(long, short = 'm')]
    mdl: Option<PathBuf>,
    #[arg(long, short = 'p')]
    pix: Option<PathBuf>,
    #[arg(long)]
    model_only: bool,
}

fn main() {
    #[cfg(target_os = "windows")]
    let backends = Backends::DX12;
    #[cfg(not(target_os = "windows"))]
    let backends = Backends::VULKAN | Backends::GL;

    App::new()
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Arika Editor".into(),
                        resolution: (1280.0_f32, 800.0_f32).into(),
                        ..default()
                    }),
                    ..default()
                })
                .set(ImagePlugin::default_nearest())
                .set(RenderPlugin {
                    render_creation: RenderCreation::Automatic(WgpuSettings {
                        backends: Some(backends),
                        ..default()
                    }),
                    ..default()
                }),
        )
        .add_plugins(EguiPlugin)
        .init_resource::<EditorState>()
        .add_systems(Startup, (setup_scene, apply_cli_args))
        .add_systems(
            Update,
            (
                handle_file_drop,
                ui_system,
                orbit_camera,
                apply_load_request,
                gizmo_system,
                apply_shading_system,
                collision_visibility_system,
            ),
        )
        .run();
}


/// Drag-and-drop
fn handle_file_drop(
    mut events: EventReader<FileDragAndDrop>,
    mut state: ResMut<EditorState>,
) {
    for ev in events.read() {
        let FileDragAndDrop::DroppedFile { path_buf, .. } = ev else {
            continue;
        };
        let path = path_buf.clone();
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        match ext.as_str() {
            "stg" => {
                state.stg_path = path.to_string_lossy().into_owned();
                let mdl = path.with_extension("mdl");
                let pix = path.with_extension("pix");
                if mdl.exists() {
                    state.mdl_path = mdl.to_string_lossy().into_owned();
                }
                if pix.exists() {
                    state.pix_path = pix.to_string_lossy().into_owned();
                }
                state.pending_load_stg = true;
                state.status = format!("Dropped stage {}", path.display());
            }
            "mdl" | "fmdl" => {
                state.mdl_path = path.to_string_lossy().into_owned();
                let pix = path.with_extension("pix");
                if state.pix_path.trim().is_empty() && pix.exists() {
                    state.pix_path = pix.to_string_lossy().into_owned();
                }
                let stg = path.with_extension("stg");
                if stg.exists() {
                    state.stg_path = stg.to_string_lossy().into_owned();
                    if pix.exists() {
                        state.pix_path = pix.to_string_lossy().into_owned();
                    }
                    state.pending_load_stg = true;
                    state.status = format!("Dropped model {} (sibling STG found)", path.display());
                } else {
                    state.pending_load_mdl = true;
                    state.status = format!("Dropped model {}", path.display());
                }
            }
            "pix" | "fpix" => {
                state.pix_path = path.to_string_lossy().into_owned();
                if !state.stg_path.trim().is_empty() {
                    state.pending_load_stg = true;
                    state.status = format!("Dropped PIX {} — reloading stage", path.display());
                } else if !state.mdl_path.trim().is_empty() {
                    state.pending_load_mdl = true;
                    state.status = format!("Dropped PIX {} — reloading model", path.display());
                } else {
                    state.status = format!("Dropped PIX {} (set MDL/STG to apply)", path.display());
                }
            }
            "hit" => {
                state.status = format!(
                    "Dropped HIT {} (collision preview not drawn yet; stage uses sibling HIT)",
                    path.display()
                );
            }
            other => {
                state.status = format!("Ignored drop (.{other}): {}", path.display());
            }
        }
    }
}

fn apply_cli_args(mut state: ResMut<EditorState>) {
    let args = Args::parse();
    if let Some(stg) = args.stg {
        state.stg_path = stg.to_string_lossy().into_owned();
        let mdl = args.mdl.clone().unwrap_or_else(|| stg.with_extension("mdl"));
        let pix = args.pix.clone().unwrap_or_else(|| stg.with_extension("pix"));
        if mdl.exists() {
            state.mdl_path = mdl.to_string_lossy().into_owned();
        }
        if pix.exists() {
            state.pix_path = pix.to_string_lossy().into_owned();
        }
        if args.model_only {
            state.pending_load_mdl = true;
            state.status = format!("CLI: loading model {}", state.mdl_path);
        } else {
            state.pending_load_stg = true;
            state.status = format!("CLI: loading stage {}", state.stg_path);
        }
    } else if let Some(mdl) = args.mdl {
        state.mdl_path = mdl.to_string_lossy().into_owned();
        let pix = args.pix.unwrap_or_else(|| mdl.with_extension("pix"));
        if pix.exists() {
            state.pix_path = pix.to_string_lossy().into_owned();
        }
        state.pending_load_mdl = true;
        state.status = format!("CLI: loading model {}", state.mdl_path);
    }
}

#[derive(Resource)]
struct EditorState {
    status: String,
    selected: Vec<String>,
    workspace: String,
    need_frame_all: bool,
    need_frame_sel: bool,
    texture_count: usize,
    undo_stack: Vec<Vec<u8>>,
    redo_stack: Vec<Vec<u8>>,
    stage_bytes: Vec<u8>,
    stage: Option<arika_core::stages::Stage>,
    expanded: std::collections::HashSet<usize>,
    hit: Option<arika_core::stages::Hit>,
    collision_entity: Option<Entity>,
    collision_mesh: Option<Handle<Mesh>>,
    shading_mode: u8,
    show_collision: bool,
    outliner_filter: String,
    snap_move: f32,
    snap_rotate: f32,
    snap_scale: f32,
    last_shading_mode: u8,
    material_textures: std::collections::HashMap<bevy::asset::AssetId<StandardMaterial>, Option<Handle<Image>>>,
    show_outliner: bool,
    show_properties: bool,
    show_console: bool,
    hierarchy: Vec<String>,
    mdl_path: String,
    pix_path: String,
    stg_path: String,
    pending_load_mdl: bool,
    pending_load_stg: bool,
    pending_reload_from_bytes: bool,
    pending_delete_selected: bool,
    clear_scene: bool,
    edit_t: [f32; 3],
    edit_r: [f32; 3],
    edit_s: [f32; 3],
    apply_transform: bool,
    lock_t: [bool; 3],
    lock_r: [bool; 3],
    lock_s: [bool; 3],
    visible: std::collections::HashMap<String, bool>,
    locked: std::collections::HashMap<String, bool>,
    materials: Vec<arika_core::models::Material>,
    dock_state: Option<egui_dock::DockState<DockTab>>,
}

impl Default for EditorState {
    fn default() -> Self {
        Self {
            status: "Drop .stg / .mdl / .pix here, or use paths. MMB orbit · Shift+MMB pan · +/- zoom · Home reset."
                .into(),
            selected: Vec::new(),
            workspace: "Layout".into(),
            need_frame_all: false,
            need_frame_sel: false,
            texture_count: 0,
            undo_stack: Vec::new(),
            redo_stack: Vec::new(),
            stage_bytes: Vec::new(),
            stage: None,
            expanded: Default::default(),
            hit: None,
            collision_entity: None,
            collision_mesh: None,
            shading_mode: 0,
            show_collision: false,
            outliner_filter: String::new(),
            snap_move: 1.0,
            snap_rotate: 15.0,
            snap_scale: 0.1,
            last_shading_mode: 255,
            material_textures: Default::default(),
            show_outliner: true,
            show_properties: true,
            show_console: true,
            hierarchy: vec!["(empty)".into()],
            mdl_path: String::new(),
            pix_path: String::new(),
            stg_path: String::new(),
            pending_load_mdl: false,
            pending_load_stg: false,
            pending_reload_from_bytes: false,
            pending_delete_selected: false,
            clear_scene: false,
            edit_t: [0.0; 3],
            edit_r: [0.0; 3],
            edit_s: [1.0; 3],
            apply_transform: false,
            lock_t: [false; 3],
            lock_r: [false; 3],
            lock_s: [false; 3],
            visible: Default::default(),
            locked: Default::default(),
            materials: Vec::new(),
            dock_state: {
                let mut ds = egui_dock::DockState::new(vec![DockTab::Outliner]);
                let [_o, props] = ds.main_surface_mut().split_below(egui_dock::NodeIndex::root(), 0.6, vec![DockTab::Properties, DockTab::Materials, DockTab::Console]);
                Some(ds)
            },
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum DockTab {
    Outliner,
    Properties,
    Materials,
    Console,
    AssetBrowser,
}

struct DockTabViewer<'a> {
    state: &'a mut EditorState,
}

impl<'a> egui_dock::TabViewer for DockTabViewer<'a> {
    type Tab = DockTab;

    fn title(&mut self, tab: &mut Self::Tab) -> egui::WidgetText {
        match tab {
            DockTab::Outliner => "Outliner".into(),
            DockTab::Properties => "Properties".into(),
            DockTab::Materials => "Materials".into(),
            DockTab::Console => "Console".into(),
            DockTab::AssetBrowser => "Assets".into(),
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, tab: &mut Self::Tab) {
        let state = &mut self.state;
        match tab {
            DockTab::Outliner => {
                ui.heading("Outliner");
                ui.separator();
                ui.horizontal(|ui| {
                    ui.label("Filter:");
                    ui.text_edit_singleline(&mut state.outliner_filter);
                });
                let filter = state.outliner_filter.to_lowercase();
                ui.separator();
                egui::ScrollArea::vertical().show(ui, |ui| {
                    if let Some(stage) = state.stage.clone() {
                        let roots: Vec<usize> = stage.roots.clone();
                        for r in roots {
                            if r < stage.nodes.len() {
                                render_outliner_node(state, &stage, r, 0, ui, &filter);
                            }
                        }
                        if stage.roots.is_empty() {
                            for i in 0..stage.nodes.len() {
                                render_outliner_node(state, &stage, i, 0, ui, &filter);
                            }
                        }
                    } else {
                        for name in state.hierarchy.clone() {
                            if !filter.is_empty() && !name.to_lowercase().contains(&filter) {
                                continue;
                            }
                            let sel = state.selected.iter().any(|s| s == &name);
                            ui.horizontal(|ui| {
                                let vis = state.visible.get(&name).copied().unwrap_or(true);
                                if ui.checkbox(&mut state.visible.entry(name.clone()).or_insert(true), "").changed() {}
                                let _ = vis;
                                let locked = state.locked.get(&name).copied().unwrap_or(true);
                                if ui.checkbox(&mut state.locked.entry(name.clone()).or_insert(true), "").changed() {}
                                let _ = locked;
                                if ui.selectable_label(sel, &name).clicked() {
                                    state.selected = vec![name.clone()];
                                }
                            });
                        }
                    }
                });
            }
            DockTab::Properties => {
                ui.heading("Properties");
                ui.separator();
                if let Some(sel) = state.selected.last().cloned() {
                    let is_locked = state.locked.get(&sel).copied().unwrap_or(true);
                    let badge = if is_locked { " [Locked]" } else { "" };
                    ui.label(egui::RichText::new(format!("Selected: {sel}{badge}")).strong());
                    ui.add_space(6.0);
                    ui.label("Transform");
                    ui.separator();
                    ui.horizontal(|ui| {
                        ui.label("T:");
                        ui.add_enabled(!state.lock_t[0], egui::DragValue::new(&mut state.edit_t[0]).speed(0.05));
                        ui.add_enabled(!state.lock_t[1], egui::DragValue::new(&mut state.edit_t[1]).speed(0.05));
                        ui.add_enabled(!state.lock_t[2], egui::DragValue::new(&mut state.edit_t[2]).speed(0.05));
                        ui.checkbox(&mut state.lock_t[0], "X");
                        ui.checkbox(&mut state.lock_t[1], "Y");
                        ui.checkbox(&mut state.lock_t[2], "Z");
                    });
                    ui.horizontal(|ui| {
                        ui.label("R:");
                        ui.add_enabled(!state.lock_r[0], egui::DragValue::new(&mut state.edit_r[0]).speed(1.0));
                        ui.add_enabled(!state.lock_r[1], egui::DragValue::new(&mut state.edit_r[1]).speed(1.0));
                        ui.add_enabled(!state.lock_r[2], egui::DragValue::new(&mut state.edit_r[2]).speed(1.0));
                        ui.checkbox(&mut state.lock_r[0], "X");
                        ui.checkbox(&mut state.lock_r[1], "Y");
                        ui.checkbox(&mut state.lock_r[2], "Z");
                    });
                    ui.horizontal(|ui| {
                        ui.label("S:");
                        ui.add_enabled(!state.lock_s[0], egui::DragValue::new(&mut state.edit_s[0]).speed(0.01));
                        ui.add_enabled(!state.lock_s[1], egui::DragValue::new(&mut state.edit_s[1]).speed(0.01));
                        ui.add_enabled(!state.lock_s[2], egui::DragValue::new(&mut state.edit_s[2]).speed(0.01));
                        ui.checkbox(&mut state.lock_s[0], "X");
                        ui.checkbox(&mut state.lock_s[1], "Y");
                        ui.checkbox(&mut state.lock_s[2], "Z");
                    });
                    if ui.button("Apply transform").clicked() {
                        state.apply_transform = true;
                    }
                } else {
                    ui.label("No mesh selected.");
                }
            }
            DockTab::Materials => {
                ui.heading("Materials");
                ui.separator();
                ui.label(format!("{} materials", state.materials.len()));
                for (i, m) in state.materials.iter().enumerate() {
                    ui.label(format!("#{} tex={} color_a={:?}", i, m.texture_index, m.color_a));
                }
            }
            DockTab::Console => {
                ui.heading("Console");
                ui.separator();
                ui.label(&state.status);
            }
            DockTab::AssetBrowser => {
                ui.heading("Asset Browser");
                ui.separator();
                ui.label(format!("{} textures", state.texture_count));
            }
        }
    }
}

#[derive(Component)]
struct LoadedMesh {
    name: String,
}

#[derive(Component)]
struct OrbitCamera {
    focus: Vec3,
    distance: f32,
    pitch: f32,
    yaw: f32,
}

fn setup_scene(mut commands: Commands) {
    commands.spawn((
        DirectionalLight {
            illuminance: 15_000.0,
            shadows_enabled: true,
            ..default()
        },
        Transform::from_xyz(10.0, 18.0, 10.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn((
        DirectionalLight {
            illuminance: 2_500.0,
            shadows_enabled: false,
            ..default()
        },
        Transform::from_xyz(-6.0, 8.0, -4.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn((
        Camera3d::default(),
        Tonemapping::Reinhard,
        Transform::from_xyz(12.0, 10.0, 18.0).looking_at(Vec3::new(0.0, 1.0, 0.0), Vec3::Y),
        OrbitCamera {
            focus: Vec3::new(0.0, 1.0, 0.0),
            distance: 22.0,
            pitch: -0.4,
            yaw: 0.6,
        },
    ));
}

fn orbit_camera(
    mut query: ParamSet<(
        Query<(&mut Transform, &mut OrbitCamera)>,
        Query<(&LoadedMesh, &Transform)>,
    )>,
    mouse: Res<ButtonInput<MouseButton>>,
    mut motion: EventReader<CursorMoved>,
    keys: Res<ButtonInput<KeyCode>>,
    time: Res<Time>,
    mut state: ResMut<EditorState>,
) {
    let mut delta = Vec2::ZERO;
    for ev in motion.read() {
        if let Some(d) = ev.delta {
            delta += d;
        }
    }
    let frame_target: Option<(Vec3, f32)> = if state.need_frame_all || state.need_frame_sel {
        let mut min = Vec3::splat(f32::MAX);
        let mut max = Vec3::splat(f32::MIN);
        let mut any = false;
        for (lm, tf) in query.p1().iter() {
            let include = if state.need_frame_sel {
                state.selected.is_empty() || state.selected.iter().any(|s| lm.name == *s || s.ends_with(&lm.name))
            } else {
                true
            };
            if include {
                min = min.min(tf.translation);
                max = max.max(tf.translation);
                any = true;
            }
        }
        if any {
            let focus = (min + max) * 0.5;
            let radius = (max - min).length() * 0.5;
            let dist = (radius * 2.5).max(3.0);
            Some((focus, dist))
        } else {
            None
        }
    } else if keys.just_pressed(KeyCode::KeyF) {
        let mut min = Vec3::splat(f32::MAX);
        let mut max = Vec3::splat(f32::MIN);
        let mut any = false;
        for (lm, tf) in query.p1().iter() {
            if state.selected.is_empty() || state.selected.iter().any(|s| lm.name == *s || s.ends_with(&lm.name)) {
                min = min.min(tf.translation);
                max = max.max(tf.translation);
                any = true;
            }
        }
        if any {
            let focus = (min + max) * 0.5;
            let radius = (max - min).length() * 0.5;
            let dist = (radius * 2.5).max(3.0);
            Some((focus, dist))
        } else {
            None
        }
    } else {
        None
    };

    for (mut transform, mut cam) in query.p0().iter_mut() {
        if let Some((focus, dist)) = frame_target {
            cam.focus = focus;
            cam.distance = dist;
            state.need_frame_all = false;
            state.need_frame_sel = false;
        }
        if mouse.pressed(MouseButton::Middle) {
            if keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight) {
                let right = *transform.right();
                let up = *transform.up();
                let pan = cam.distance * 0.002;
                cam.focus += right * -delta.x * pan + up * delta.y * pan;
            } else {
                cam.yaw -= delta.x * 0.005;
                cam.pitch = (cam.pitch - delta.y * 0.005).clamp(-1.4, 1.4);
            }
        }
        if keys.pressed(KeyCode::Equal) || keys.pressed(KeyCode::NumpadAdd) {
            cam.distance = (cam.distance * (1.0 - time.delta_secs() * 1.5)).max(1.0);
        }
        if keys.pressed(KeyCode::Minus) || keys.pressed(KeyCode::NumpadSubtract) {
            cam.distance = (cam.distance * (1.0 + time.delta_secs() * 1.5)).min(500.0);
        }
        if keys.just_pressed(KeyCode::Home) {
            cam.focus = Vec3::ZERO;
            cam.distance = 22.0;
            cam.pitch = -0.4;
            cam.yaw = 0.6;
        }
        let rot = Quat::from_euler(EulerRot::YXZ, cam.yaw, cam.pitch, 0.0);
        transform.translation = cam.focus + rot * Vec3::new(0.0, 0.0, cam.distance);
        transform.look_at(cam.focus, Vec3::Y);
    }
}

fn render_outliner_node(state: &mut EditorState, stage: &arika_core::stages::Stage, idx: usize, depth: usize, ui: &mut egui_dock::egui::Ui, filter: &str) {
    let node = &stage.nodes[idx];
    let name = if node.name.is_empty() { format!("node {}", idx) } else { node.name.clone() };
    if !filter.is_empty() && !name.to_lowercase().contains(filter) {
        return;
    }
    let has_children = !node.children.is_empty();
    ui.horizontal(|ui| {
        ui.add_space(depth as f32 * 14.0);
        if has_children {
            let expanded = state.expanded.contains(&idx);
            if ui.button(if expanded { "▾" } else { "▸" }).clicked() {
                if expanded { state.expanded.remove(&idx); } else { state.expanded.insert(idx); }
            }
        } else {
            ui.label(" ");
        }
        let sel = state.selected.iter().any(|s| s == &name);
        if ui.selectable_label(sel, &name).clicked() {
            if ui.input(|i| i.modifiers.shift || i.modifiers.ctrl) {
                if sel { state.selected.retain(|s| s != &name); } else { state.selected.push(name.clone()); }
            } else {
                state.selected = vec![name.clone()];
            }
        }
        let vis = state.visible.entry(name.clone()).or_insert(true);
        ui.checkbox(vis, "V");
        let locked = state.locked.entry(name.clone()).or_insert(true);
        ui.checkbox(locked, "L");
        ui.label(format!("k{}", node.kind));
    });
    if has_children && state.expanded.contains(&idx) {
        for &c in &node.children {
            if c < stage.nodes.len() {
                render_outliner_node(state, stage, c, depth + 1, ui, filter);
            }
        }
    }
}

fn ui_system(mut contexts: EguiContexts, mut state: ResMut<EditorState>) {
    let ctx = contexts.ctx_mut();

    apply_theme(ctx);

    if ctx.input(|i| i.key_pressed(egui::Key::Z) && i.modifiers.ctrl && i.modifiers.shift) {
        if !state.redo_stack.is_empty() {
            let snap = state.stage_bytes.clone();
            state.undo_stack.push(snap);
            state.stage_bytes = state.redo_stack.pop().unwrap();
            state.pending_reload_from_bytes = true;
            state.status = "Redo".into();
        }
    } else if ctx.input(|i| i.key_pressed(egui::Key::Z) && i.modifiers.ctrl) {
        if !state.undo_stack.is_empty() {
            let snap = state.stage_bytes.clone();
            state.redo_stack.push(snap);
            state.stage_bytes = state.undo_stack.pop().unwrap();
            state.pending_reload_from_bytes = true;
            state.status = "Undo".into();
        }
    } else if ctx.input(|i| i.key_pressed(egui::Key::Delete)) {
        state.pending_delete_selected = true;
    }

    egui::TopBottomPanel::top("menu_bar").show(ctx, |ui| {
        egui::menu::bar(ui, |ui| {
            ui.menu_button("File", |ui| {
                if ui.button("Open stage…").clicked() {
                    if let Some(path) = rfd::FileDialog::new()
                        .add_filter("Stage scene", &["stg"])
                        .set_title("Open stage")
                        .pick_file()
                    {
                        state.stg_path = path.to_string_lossy().into_owned();
                        let mdl = path.with_extension("mdl");
                        let pix = path.with_extension("pix");
                        if mdl.exists() {
                            state.mdl_path = mdl.to_string_lossy().into_owned();
                        }
                        if pix.exists() {
                            state.pix_path = pix.to_string_lossy().into_owned();
                        }
                        state.pending_load_stg = true;
                    }
                    ui.close_menu();
                }
                ui.separator();
                if ui.button("Save stage…").clicked() {
                    state.status = "Save stage not yet implemented".into();
                }
                if ui.button("Export glTF…").clicked() {
                    if let Some(path) = rfd::FileDialog::new()
                        .add_filter("glTF", &["gltf"])
                        .set_title("Export glTF")
                        .save_file()
                    {
                        let mut msg = String::new();
                        if let Some(stage) = state.stage.clone() {
                            let mdl_path = state.mdl_path.clone();
                            let pix_path = state.pix_path.clone();
                            let materials = state.materials.clone();
                            let hit = state.hit.clone();
                            let data = std::fs::read(&mdl_path).unwrap_or_default();
                            let name = std::path::Path::new(&mdl_path).file_stem().and_then(|s| s.to_str()).unwrap_or("model");
                            let mut model = match arika_core::models::parse_fmdl(&data, name) {
                                Ok(m) => m,
                                Err(e) => { state.status = e.to_string(); arika_core::models::Model { name: name.to_string(), nodes: vec![], meshes: vec![], materials: materials.clone(), textures: vec![] } }
                            };
                            let pix = if !pix_path.trim().is_empty() { Some(pix_path.clone()) } else {
                                let sib = std::path::Path::new(&mdl_path).with_extension("pix");
                                if sib.exists() { Some(sib.to_string_lossy().into_owned()) } else { None }
                            };
                            if let Some(pp) = pix {
                                if let Ok(pd) = std::fs::read(&pp) {
                                    let _ = arika_core::models::attach_textures(&mut model, &pd);
                                }
                            }
                            model.materials = materials;
                            match arika_core::gltf::build_stage_gltf(&model, &stage, hit.as_ref()) {
                                Ok(doc) => {
                                    if let Ok(text) = serde_json::to_string(&doc) {
                                        if std::fs::write(&path, text).is_ok() {
                                            state.status = format!("Exported glTF {}", path.display());
                                        } else {
                                            state.status = "Export write failed".into();
                                        }
                                    }
                                }
                                Err(e) => state.status = e.to_string(),
                            }
                        } else {
                            state.status = "No stage loaded".into();
                        }
                        let _ = msg;
                    }
                    ui.close_menu();
                }
                ui.separator();
                if ui.button("Clear scene").clicked() {
                    state.clear_scene = true;
                    state.hierarchy = vec!["(empty)".into()];
                    state.selected.clear();
                    state.status = "Scene cleared".into();
                    ui.close_menu();
                }
                ui.separator();
                if ui.button("Quit").clicked() {
                    std::process::exit(0);
                }
            });
            ui.menu_button("Edit", |ui| {
                if ui.button("Undo").clicked() {
                    if !state.undo_stack.is_empty() {
                        let snap = state.stage_bytes.clone();
                        state.redo_stack.push(snap);
                        state.stage_bytes = state.undo_stack.pop().unwrap();
                        state.pending_reload_from_bytes = true;
                        state.status = "Undo".into();
                    }
                }
                if ui.button("Redo").clicked() {
                    if !state.redo_stack.is_empty() {
                        let snap = state.stage_bytes.clone();
                        state.undo_stack.push(snap);
                        state.stage_bytes = state.redo_stack.pop().unwrap();
                        state.pending_reload_from_bytes = true;
                        state.status = "Redo".into();
                    }
                }
                ui.separator();
                if ui.button("Delete selected").clicked() {
                    state.pending_delete_selected = true;
                }
                if ui.button("Duplicate selected").clicked() {
                    state.status = "Duplicate not yet implemented".into();
                }
            });
            ui.menu_button("View", |ui| {
                ui.checkbox(&mut state.show_outliner, "Outliner");
                ui.checkbox(&mut state.show_properties, "Properties");
                ui.checkbox(&mut state.show_console, "Console");
                ui.checkbox(&mut state.show_collision, "Collision overlay");
            });
            ui.menu_button("Viewports", |ui| {
                ui.radio_value(&mut state.shading_mode, 0, "Textured");
                ui.radio_value(&mut state.shading_mode, 1, "Solid");
                ui.radio_value(&mut state.shading_mode, 2, "Wireframe");
            });
            ui.menu_button("Window", |ui| {
                if ui.button("Outliner").clicked() {
                    state.show_outliner = !state.show_outliner;
                    state.status = format!("Outliner: {}", state.show_outliner);
                }
                if ui.button("Properties").clicked() {
                    state.show_properties = !state.show_properties;
                    state.status = format!("Properties: {}", state.show_properties);
                }
                if ui.button("Console").clicked() {
                    state.show_console = !state.show_console;
                    state.status = format!("Console: {}", state.show_console);
                }
                ui.separator();
                if ui.button("Reset Layout").clicked() {
                    state.status = "Reset layout not yet implemented".into();
                }
            });
            ui.menu_button("Help", |ui| {
                if ui.button("About").clicked() {
                    state.status = "Arika Editor — Bevy + egui scene/stage editor".into();
                }
                if ui.button("Controls").clicked() {
                    state.status = "MMB orbit · Shift+MMB pan · +/- zoom · Home reset".into();
                }
            });
        });
    });
    egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
        ui.horizontal(|ui| {
            ui.label("Workspace:");
            for name in ["Layout", "Shading", "Textures", "Object"] {
                let selected = state.workspace == name;
                if ui.selectable_label(selected, name).clicked() {
                    state.workspace = name.to_string();
                }
            }
            ui.separator();
            ui.label("View:");
            if ui.button("Frame all").clicked() {
                state.need_frame_all = true;
            }
            if ui.button("Frame sel").clicked() {
                state.need_frame_sel = true;
            }
            ui.separator();
            ui.label("Shading:");
            egui::ComboBox::from_label("")
                .selected_text(match state.shading_mode { 0 => "Textured", 1 => "Solid", 2 => "Wireframe", _ => "Textured" })
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut state.shading_mode, 0, "Textured");
                    ui.selectable_value(&mut state.shading_mode, 1, "Solid");
                    ui.selectable_value(&mut state.shading_mode, 2, "Wireframe");
                });
            ui.separator();
            ui.checkbox(&mut state.show_collision, "Collision");
            ui.separator();
            ui.label("3D Viewport:");
            if ui.button("Perspective").clicked() {
                state.status = "3D Viewport: Perspective".into();
            }
            ui.separator();
            ui.label("World:");
            if ui.button("Default World").clicked() {
                state.status = "World: Default".into();
            }
            ui.separator();
            ui.label("View:");
            if ui.button("Top").clicked() { state.status = "View: Top".into(); }
            if ui.button("Front").clicked() { state.status = "View: Front".into(); }
            if ui.button("Side").clicked() { state.status = "View: Side".into(); }
            ui.separator();
            ui.label("Transform:");
            if ui.button("Move").clicked() { state.status = "Tool: Move".into(); }
            if ui.button("Rotate").clicked() { state.status = "Tool: Rotate".into(); }
            if ui.button("Scale").clicked() { state.status = "Tool: Scale".into(); }
            ui.separator();
            ui.label("Local:");
            if ui.button("Local").clicked() { state.status = "Transform orientation: Local".into(); }
            ui.separator();
            ui.label("Median Point:");
            if ui.button("Median Point").clicked() { state.status = "Pivot: Median Point".into(); }
            ui.separator();
            ui.label("Snap:");
            if ui.button("Snap").clicked() { state.status = "Snap toggle".into(); }
            ui.separator();
            ui.label("Textured:");
            if ui.button("Textured").clicked() { state.status = "Viewport shading: Textured".into(); }
            ui.separator();
            if ui.button("Viewport").clicked() {
                state.status = "Viewport button clicked".into();
            }
        });
    });

    egui::SidePanel::right("dock_panel")
        .default_width(360.0)
        .resizable(true)
        .show(ctx, |ui| {
            let mut dock_state = state.dock_state.take().unwrap();
            let mut viewer = DockTabViewer { state: &mut *state };
            egui_dock::DockArea::new(&mut dock_state)
                .style(egui_dock::Style::from_egui(ui.style().as_ref()))
                .show_inside(ui, &mut viewer);
            viewer.state.dock_state = Some(dock_state);
        });

    egui::TopBottomPanel::bottom("asset_browser")
        .default_height(110.0)
        .resizable(true)
        .show(ctx, |ui| {
            ui.heading("Asset Browser — Textures");
            ui.separator();
            ui.horizontal(|ui| {
                ui.label(format!("{} textures", state.texture_count));
                ui.separator();
                ui.label("Click to preview (not yet wired)");
            });
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.horizontal_wrapped(|ui| {
                    for i in 0..state.texture_count {
                        let (rect, _) = ui.allocate_exact_size(egui::Vec2::splat(64.0), egui::Sense::click());
                        ui.painter().rect_stroke(rect, 4.0, egui::Stroke::new(1.0, egui::Color32::from_gray(80)));
                        ui.painter().text(rect.center(), egui::Align2::CENTER_CENTER, format!("{}", i), egui::FontId::proportional(10.0), egui::Color32::LIGHT_GRAY);
                    }
                });
            });
        });

    egui::TopBottomPanel::bottom("status_bar").show(ctx, |ui| {
        ui.set_min_height(24.0);
        ui.add_space(4.0);
        ui.label(&state.status);
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            ui.label(format!("{} selected", state.selected.len()));
            ui.separator();
            ui.label(match state.shading_mode {
                0 => "Textured",
                1 => "Solid",
                2 => "Wireframe",
                _ => "Textured",
            });
        });
    });
}

fn apply_load_request(
    mut commands: Commands,
    mut state: ResMut<EditorState>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
    loaded: Query<Entity, With<LoadedMesh>>,
    mut cameras: Query<&mut OrbitCamera>,
) {
    if state.pending_delete_selected {
        state.pending_delete_selected = false;
        let sel_set: std::collections::HashSet<String> = state.selected.iter().cloned().collect();
        state.status = format!("Delete requested for {} selected (entity-level delete requires scene rebuild; use Clear scene)", sel_set.len());
        state.selected.clear();
    }
    if state.clear_scene {
        for e in &loaded {
            commands.entity(e).despawn();
        }
        state.clear_scene = false;
    }

    if state.apply_transform {
        state.apply_transform = false;
    }

    if state.pending_load_mdl {
        state.pending_load_mdl = false;
        match load_model_into_scene(
            &mut commands,
            &mut state,
            &mut meshes,
            &mut materials,
            &mut images,
            &loaded,
            &mut cameras,
            None,
            None,
        ) {
            Ok(msg) => state.status = msg,
            Err(e) => state.status = e,
        }
    }

    if state.pending_reload_from_bytes {
        state.pending_reload_from_bytes = false;
        let stg_data = state.stage_bytes.clone();
        let stage = match parse_stg(&stg_data) {
            Ok(s) => s,
            Err(e) => { state.status = format!("STG parse: {e}"); return; }
        };
        state.stage = Some(stage.clone());
        let instances = stage_instances_filtered(&stage, false);
        for e in &loaded { commands.entity(e).despawn(); }
        match load_model_into_scene(
            &mut commands, &mut state, &mut meshes, &mut materials, &mut images,
            &loaded, &mut cameras, Some(&stage), Some(&instances),
        ) {
            Ok(msg) => state.status = format!("Reloaded: {msg}"),
            Err(e) => state.status = e,
        }
        return;
    }

    if state.pending_load_stg {
        state.pending_load_stg = false;
        let stg_path = state.stg_path.trim().to_string();
        if stg_path.is_empty() {
            state.status = "No STG path".into();
            return;
        }
        let stg = std::path::Path::new(&stg_path);
        let mdl_auto = stg.with_extension("mdl");
        let pix_auto = stg.with_extension("pix");
        let hit_auto = stg.with_extension("hit");
        if state.mdl_path.trim().is_empty() && mdl_auto.exists() {
            state.mdl_path = mdl_auto.to_string_lossy().into_owned();
        }
        if state.pix_path.trim().is_empty() && pix_auto.exists() {
            state.pix_path = pix_auto.to_string_lossy().into_owned();
        }
        if mdl_auto.exists() {
            state.mdl_path = mdl_auto.to_string_lossy().into_owned();
        }
        if pix_auto.exists() {
            state.pix_path = pix_auto.to_string_lossy().into_owned();
        }

        let stg_data = match std::fs::read(&stg_path) {
            Ok(d) => d,
            Err(e) => {
                state.status = format!("STG read: {e}");
                return;
            }
        };
        let stage = match parse_stg(&stg_data) {
            Ok(s) => s,
            Err(e) => {
                state.status = format!("STG parse: {e}");
                return;
            }
        };
        let instances = stage_instances_filtered(&stage, false);
        let kind2 = stage.nodes.iter().filter(|n| n.kind == 2).count();
        state.stage_bytes = stg_data.clone();
        state.undo_stack.clear();
        state.redo_stack.clear();
        state.hit = if hit_auto.exists() {
            std::fs::read(&hit_auto).ok().and_then(|d| parse_hit(&d).ok())
        } else {
            None
        };
        if let Some(hit) = state.hit.clone() {
            if let Some(e) = state.collision_entity.take() {
                commands.entity(e).despawn();
            }
            let mut positions: Vec<[f32; 3]> = Vec::new();
            let mut indices: Vec<u32> = Vec::new();
            for obj in &hit.objects {
                for pi in 0..obj.polygon_count {
                    let poly = &hit.polygons[(obj.first_polygon + pi) as usize];
                    let first = poly.first_vertex as usize;
                    let vc = poly.vertex_count as usize;
                    if vc < 2 { continue; }
                    let base = positions.len() as u32;
                    for v in 0..vc {
                        let vert = hit.vertices[first + v];
                        positions.push(vert);
                    }
                    for v in 0..vc {
                        indices.push(base + v as u32);
                        indices.push(base + ((v + 1) % vc) as u32);
                    }
                }
            }
            if !positions.is_empty() {
                let mut mesh = Mesh::new(PrimitiveTopology::LineList, RenderAssetUsages::default());
                mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, positions);
                mesh.insert_indices(Indices::U32(indices));
                let h = meshes.add(mesh);
                state.collision_mesh = Some(h.clone());
                let mat = materials.add(StandardMaterial {
                    base_color: Color::srgb(0.0, 1.0, 0.5),
                    unlit: true,
                    ..default()
                });
                let e = commands.spawn((Mesh3d(h), MeshMaterial3d(mat), Transform::default(), Visibility::Hidden)).id();
                state.collision_entity = Some(e);
            }
        }
        let hit_note = if hit_auto.exists() {
            format!(" | HIT {}", hit_auto.file_name().unwrap_or_default().to_string_lossy())
        } else {
            String::new()
        };
        match load_model_into_scene(
            &mut commands,
            &mut state,
            &mut meshes,
            &mut materials,
            &mut images,
            &loaded,
            &mut cameras,
            Some(&stage),
            Some(&instances),
        ) {
            Ok(msg) => {
                state.status = format!(
                    "{msg} | stage “{}”: {} kind-2 (placed {}) · {} nodes · MDL {}{hit_note}",
                    stage.name,
                    kind2,
                    instances.len(),
                    stage.nodes.len(),
                    std::path::Path::new(&state.mdl_path)
                        .file_name()
                        .map(|s| s.to_string_lossy().into_owned())
                        .unwrap_or_else(|| state.mdl_path.clone()),
                );
            }
            Err(e) => state.status = e,
        }
    }
}

fn load_model_into_scene(
    commands: &mut Commands,
    state: &mut EditorState,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    images: &mut Assets<Image>,
    loaded: &Query<Entity, With<LoadedMesh>>,
    cameras: &mut Query<&mut OrbitCamera>,
    stage: Option<&Stage>,
    instances: Option<&[StageInstance]>,
) -> Result<String, String> {
    let path = state.mdl_path.trim().to_string();
    if path.is_empty() {
        return Err("No MDL path".into());
    }
    let data = std::fs::read(&path).map_err(|e| format!("MDL read: {e}"))?;
    let name = std::path::Path::new(&path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("model");
    let mut model = parse_fmdl(&data, name).map_err(|e| format!("FMDL: {e}"))?;
    state.stage = stage.cloned();
    state.materials = model.materials.clone();

    let pix = if !state.pix_path.trim().is_empty() {
        Some(state.pix_path.trim().to_string())
    } else {
        let sib = std::path::Path::new(&path).with_extension("pix");
        sib.exists()
            .then(|| sib.to_string_lossy().into_owned())
    };
    let mut tex_note = String::new();
    if let Some(pp) = pix {
        match std::fs::read(&pp) {
            Ok(pd) => match attach_textures(&mut model, &pd) {
                Ok(()) => tex_note = format!(" · PIX {} tex", model.textures.len()),
                Err(e) => tex_note = format!(" · PIX err: {e}"),
            },
            Err(e) => tex_note = format!(" · PIX read: {e}"),
        }
    } else {
        tex_note = " · no PIX".into();
    }
    state.texture_count = model.textures.len();

    for e in loaded {
        commands.entity(e).despawn();
    }

    let mut bevy_images: Vec<Option<Handle<Image>>> = Vec::new();
    for tex in &model.textures {
        if tex.rgba.is_empty() {
            bevy_images.push(None);
            continue;
        }
        let image = Image::new(
            bevy::render::render_resource::Extent3d {
                width: tex.width,
                height: tex.height,
                depth_or_array_layers: 1,
            },
            bevy::render::render_resource::TextureDimension::D2,
            tex.rgba.clone(),
            bevy::render::render_resource::TextureFormat::Rgba8UnormSrgb,
            RenderAssetUsages::default(),
        );
        bevy_images.push(Some(images.add(image)));
    }

    let mut mesh_assets: HashMap<String, Vec<(Handle<Mesh>, Handle<StandardMaterial>)>> = HashMap::new();
    let mut bounds_min = Vec3::splat(f32::MAX);
    let mut bounds_max = Vec3::splat(f32::MIN);

    let mut mat_handles: Vec<Handle<StandardMaterial>> = Vec::new();
    for (mi, mat) in model.materials.iter().enumerate() {
        let tex_i = if mat.texture_index >= 0 {
            mat.texture_index as usize
        } else {
            mi
        };
        let base_texture = bevy_images.get(tex_i).and_then(|h| h.clone())
            .or_else(|| bevy_images.get(mi).and_then(|h| h.clone()));
        let base_color = Color::WHITE;
        mat_handles.push(materials.add(StandardMaterial {
            base_color,
            base_color_texture: base_texture,
            perceptual_roughness: 1.0,
            metallic: 0.0,
            reflectance: 0.0,
            double_sided: true,
            cull_mode: None,
            alpha_mode: AlphaMode::Mask(0.1),
            unlit: true,
            ..default()
        }));
    }
    let default_mat = materials.add(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        double_sided: true,
        cull_mode: None,
        ..default()
    });

    for (mesh_i, mesh) in model.meshes.iter().enumerate() {
        if mesh.positions.is_empty() || mesh.indices.is_empty() {
            continue;
        }
        for p in &mesh.positions {
            let v = Vec3::new(p[0], p[1], p[2]);
            bounds_min = bounds_min.min(v);
            bounds_max = bounds_max.max(v);
        }
        let parts = split_mesh_by_material(mesh);
        let mut parts_out = Vec::new();
        for (mat_i, part_indices) in parts {
            let mut part = mesh.clone();
            part.indices = part_indices;
            let handle = meshes.add(arika_mesh_to_bevy(&part));
            let mat = if mat_i >= 0 {
                mat_handles.get(mat_i as usize).cloned().unwrap_or_else(|| default_mat.clone())
            } else {
                default_mat.clone()
            };
            parts_out.push((handle, mat));
        }
        if parts_out.is_empty() {
            let handle = meshes.add(arika_mesh_to_bevy(mesh));
            let mat = mat_handles.get(mesh_i).cloned().unwrap_or_else(|| default_mat.clone());
            parts_out.push((handle, mat));
        }
        mesh_assets.insert(mesh.name.clone(), parts_out);
    }

    let mut hierarchy = Vec::new();
    let mut spawned = 0usize;

    if let Some(insts) = instances {
        hierarchy.push(format!("Stage instances ({})", insts.len()));
        let lower: HashMap<String, String> = mesh_assets
            .keys()
            .map(|k| (k.to_lowercase(), k.clone()))
            .collect();
        let worlds = stage.as_ref().map(|s| stage_world_matrices(s));
        let stage_nodes: &[StageNode] = match stage {
            Some(s) => &s.nodes,
            None => &[],
        };
        for node in stage_nodes {
            if node.kind != 2 {
                continue;
            }
            let key = mesh_assets
                .get(&node.name)
                .map(|_| node.name.clone())
                .or_else(|| lower.get(&node.name.to_lowercase()).cloned());
            let Some(mesh_key) = key else {
                hierarchy.push(format!("  {} (missing mesh {})", node.name, node.name));
                continue;
            };
            let Some(parts) = mesh_assets.get(&mesh_key) else {
                continue;
            };
            let (scale, rot, translation) = match worlds
                .as_ref()
                .and_then(|w| w.get(node.index))
            {
                Some(w) => w.to_scale_rotation_translation(),
                None => (
                    Vec3::new(node.scale[0], node.scale[1], node.scale[2]),
                    Quat::from_euler(
                        EulerRot::XYZ,
                        node.rotation[0],
                        node.rotation[1],
                        node.rotation[2],
                    ),
                    Vec3::new(
                        node.translation[0],
                        node.translation[1],
                        node.translation[2],
                    ),
                ),
            };
            let tf = Transform {
                translation,
                rotation: rot,
                scale,
            };
            bounds_min = bounds_min.min(tf.translation);
            bounds_max = bounds_max.max(tf.translation);

            let label = format!("{} [{}]", node.name, mesh_key);
            for (pi, (mh, mat)) in parts.iter().enumerate() {
                let name = if parts.len() == 1 {
                    label.clone()
                } else {
                    format!("{label}#{pi}")
                };
                commands.spawn((
                    Mesh3d(mh.clone()),
                    MeshMaterial3d(mat.clone()),
                    tf,
                    Name::new(name.clone()),
                    LoadedMesh { name: name.clone() },
                ));
            }
            hierarchy.push(format!("  {label}"));
            spawned += 1;
        }
        if spawned == 0 && !mesh_assets.is_empty() {
            hierarchy.push("  (no name matches — showing all meshes at origin)".into());
            for (name, parts) in &mesh_assets {
                for (pi, (mh, mat)) in parts.iter().enumerate() {
                    let label = if parts.len() == 1 {
                        name.clone()
                    } else {
                        format!("{name}#{pi}")
                    };
                    commands.spawn((
                        Mesh3d(mh.clone()),
                        MeshMaterial3d(mat.clone()),
                        Transform::default(),
                        Name::new(label.clone()),
                        LoadedMesh { name: label },
                    ));
                }
                hierarchy.push(format!("  {name}"));
                spawned += 1;
            }
        }
    } else {
        hierarchy.push(format!("{} ({} meshes)", model.name, mesh_assets.len()));
        for (name, parts) in &mesh_assets {
            for (pi, (mh, mat)) in parts.iter().enumerate() {
                let label = if parts.len() == 1 {
                    name.clone()
                } else {
                    format!("{name}#{pi}")
                };
                commands.spawn((
                    Mesh3d(mh.clone()),
                    MeshMaterial3d(mat.clone()),
                    Transform::default(),
                    Name::new(label.clone()),
                    LoadedMesh { name: label },
                ));
            }
            hierarchy.push(format!("  {name}"));
            spawned += 1;
        }
    }

    if spawned > 0 && bounds_min.x.is_finite() {
        let center = (bounds_min + bounds_max) * 0.5;
        let radius = (bounds_max - bounds_min).length() * 0.5;
        for mut cam in cameras.iter_mut() {
            cam.focus = center;
            cam.distance = (radius * 2.5).max(3.0);
        }
    }

    state.hierarchy = hierarchy;
    Ok(format!(
        "Spawned {spawned} · {} mesh defs · {} textures · {} materials{tex_note}",
        model.meshes.len(),
        model.textures.len(),
        model.materials.len()
    ))
}

fn apply_shading_system(
    mut state: ResMut<EditorState>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    if state.shading_mode == state.last_shading_mode {
        return;
    }
    if state.material_textures.is_empty() {
        for (h, mat) in materials.iter() {
            state.material_textures.insert(h, mat.base_color_texture.clone());
        }
    }
    state.last_shading_mode = state.shading_mode;
    for (h, mat) in materials.iter_mut() {
        let orig = state.material_textures.get(&h).cloned().flatten();
        match state.shading_mode {
            0 => {
                mat.base_color_texture = orig;
                mat.base_color = Color::WHITE;
            }
            1 => {
                mat.base_color_texture = None;
                mat.base_color = Color::WHITE;
            }
            2 => {
                mat.base_color_texture = None;
                mat.base_color = Color::srgb(0.7, 0.7, 0.75);
            }
            _ => {}
        }
    }
}

fn collision_visibility_system(
    state: Res<EditorState>,
    mut commands: Commands,
) {
    if let Some(e) = state.collision_entity {
        if state.show_collision {
            commands.entity(e).insert(Visibility::Visible);
        } else {
            commands.entity(e).insert(Visibility::Hidden);
        }
    }
}

fn split_mesh_by_material(mesh: &ArikaMesh) -> Vec<(i32, Vec<u32>)> {
    use std::collections::BTreeMap;
    let mut map: BTreeMap<i32, Vec<u32>> = BTreeMap::new();
    let ntri = mesh.indices.len() / 3;
    for ti in 0..ntri {
        let mat = mesh
            .material_indices
            .get(ti)
            .copied()
            .unwrap_or(-1);
        let tri = &mesh.indices[ti * 3..ti * 3 + 3];
        map.entry(mat).or_default().extend_from_slice(tri);
    }
    if map.is_empty() {
        map.insert(-1, mesh.indices.clone());
    }
    map.into_iter().collect()
}

fn arika_mesh_to_bevy(mesh: &ArikaMesh) -> Mesh {
    let mut bevy = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
    let n = mesh.positions.len();
    let normals = if mesh.normals.len() == n {
        mesh.normals.clone()
    } else {
        vec![[0.0, 1.0, 0.0]; n]
    };
    let uvs = if mesh.uvs.len() == n {
        mesh.uvs.clone()
    } else {
        vec![[0.0, 0.0]; n]
    };
    bevy.insert_attribute(Mesh::ATTRIBUTE_POSITION, mesh.positions.clone());
    bevy.insert_attribute(Mesh::ATTRIBUTE_NORMAL, normals);
    bevy.insert_attribute(Mesh::ATTRIBUTE_UV_0, uvs);
    bevy.insert_indices(Indices::U32(mesh.indices.clone()));
    bevy
}

fn gizmo_system(
    mut state: ResMut<EditorState>,
    mut query: Query<(&LoadedMesh, &mut Transform)>,
) {
    if state.apply_transform {
        state.apply_transform = false;
        if let Some(sel) = state.selected.last().cloned() {
            if !state.stage_bytes.is_empty() {
                if let Ok(stage) = parse_stg(&state.stage_bytes) {
                    if let Some(node) = stage.nodes.iter().find(|n| n.name == sel) {
                        let t = [
                            if state.lock_t[0] { node.translation[0] } else { state.edit_t[0] },
                            if state.lock_t[1] { node.translation[1] } else { state.edit_t[1] },
                            if state.lock_t[2] { node.translation[2] } else { state.edit_t[2] },
                        ];
                        let r = [
                            if state.lock_r[0] { node.rotation[0] } else { state.edit_r[0].to_radians() },
                            if state.lock_r[1] { node.rotation[1] } else { state.edit_r[1].to_radians() },
                            if state.lock_r[2] { node.rotation[2] } else { state.edit_r[2].to_radians() },
                        ];
                        let s = [
                            if state.lock_s[0] { node.scale[0] } else { state.edit_s[0] },
                            if state.lock_s[1] { node.scale[1] } else { state.edit_s[1] },
                            if state.lock_s[2] { node.scale[2] } else { state.edit_s[2] },
                        ];
                        let vals = [
                            t[0], t[1], t[2],
                            r[0], r[1], r[2],
                            s[0], s[1], s[2],
                        ];
                        let offset = node.offset;
                        if vals.iter().all(|v| v.is_finite()) {
                            let snapshot = state.stage_bytes.clone();
                            state.undo_stack.push(snapshot);
                            if state.undo_stack.len() > 100 { state.undo_stack.remove(0); }
                            state.redo_stack.clear();
                            let mut data = state.stage_bytes.clone();
                            for (i, v) in vals.iter().enumerate() {
                                let start = offset + 8 + i * 4;
                                if start + 4 <= data.len() {
                                    data[start..start + 4].copy_from_slice(&v.to_le_bytes());
                                }
                            }
                            state.stage_bytes = data;
                            state.pending_reload_from_bytes = true;
                            state.status = format!("Applied transform to {sel}");
                        }
                    }
                }
            }
            for (lm, mut tf) in &mut query {
                if lm.name == sel || sel.ends_with(&lm.name) {
                    let mut tr = tf.translation;
                    if !state.lock_t[0] { tr.x = state.edit_t[0]; }
                    if !state.lock_t[1] { tr.y = state.edit_t[1]; }
                    if !state.lock_t[2] { tr.z = state.edit_t[2]; }
                    tf.translation = tr;
                    let (rx, ry, rz) = tf.rotation.to_euler(EulerRot::XYZ);
                    let mut r = [rx, ry, rz];
                    if !state.lock_r[0] { r[0] = state.edit_r[0].to_radians(); }
                    if !state.lock_r[1] { r[1] = state.edit_r[1].to_radians(); }
                    if !state.lock_r[2] { r[2] = state.edit_r[2].to_radians(); }
                    tf.rotation = Quat::from_euler(EulerRot::XYZ, r[0], r[1], r[2]);
                    let mut sc = tf.scale;
                    if !state.lock_s[0] { sc.x = state.edit_s[0]; }
                    if !state.lock_s[1] { sc.y = state.edit_s[1]; }
                    if !state.lock_s[2] { sc.z = state.edit_s[2]; }
                    tf.scale = sc;
                }
            }
        }
    }

    if let Some(sel) = state.selected.last().cloned() {
        for (lm, tf) in &query {
            if lm.name == sel || sel.ends_with(&lm.name) {
                let (rx, ry, rz) = tf.rotation.to_euler(EulerRot::XYZ);
                let _ = (rx, ry, rz, &tf);
                break;
            }
        }
    }
}

fn apply_theme(ctx: &egui::Context) {
    let mut visuals = egui::Visuals::dark();
    visuals.window_fill = egui::Color32::from_rgb(0x1a, 0x1a, 0x1a);
    visuals.panel_fill = egui::Color32::from_rgb(0x22, 0x22, 0x22);
    visuals.selection.bg_fill = egui::Color32::from_rgb(0x4a, 0x90, 0xd9);
    visuals.widgets.noninteractive.bg_fill = egui::Color32::from_rgb(0x2a, 0x2a, 0x2a);
    visuals.widgets.inactive.bg_fill = egui::Color32::from_rgb(0x2d, 0x2d, 0x2d);
    visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, egui::Color32::from_rgb(0x44, 0x44, 0x44));
    visuals.widgets.active.bg_fill = egui::Color32::from_rgb(0x3a, 0x3a, 0x3a);
    visuals.widgets.hovered.bg_fill = egui::Color32::from_rgb(0x38, 0x38, 0x38);
    visuals.faint_bg_color = egui::Color32::from_rgb(0x22, 0x22, 0x22);
    visuals.extreme_bg_color = egui::Color32::from_rgb(0x14, 0x14, 0x1a);
    visuals.code_bg_color = egui::Color32::from_rgb(0x1a, 0x1a, 0x1a);
    visuals.window_stroke = egui::Stroke::new(1.0, egui::Color32::from_rgb(0x33, 0x33, 0x33));
    visuals.window_rounding = egui::Rounding::same(4.0);
    ctx.set_visuals(visuals);

    let mut style: egui::Style = Default::default();
    style.spacing.button_padding = egui::Vec2::new(8.0, 4.0);
    style.spacing.item_spacing = egui::Vec2::new(8.0, 6.0);
    style.spacing.menu_margin = egui::Margin::symmetric(8.0, 4.0);
    style.spacing.indent = 16.0;
    ctx.set_style(style);
}
