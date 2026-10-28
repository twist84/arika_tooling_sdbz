//! STG scene and HIT collision formats.

use crate::container::{f32_at, u32_at};
use crate::error::{ArikaError, Result};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct Stage {
    pub name: String,
    pub names: Vec<String>,
    pub nodes: Vec<StageNode>,
    pub template_count: u32,
    pub roots: Vec<usize>,
}

#[derive(Debug, Clone, Serialize)]
pub struct StageNode {
    pub index: usize,
    pub kind: u8,
    pub name_index: u32,
    pub name: String,
    pub offset: usize,
    pub translation: [f32; 3],
    pub rotation: [f32; 3], // radians
    pub scale: [f32; 3],
    pub flags: u8,
    pub links: u8,
    pub parent: i32,
    pub children: Vec<usize>,
    pub references: Vec<StageRef>,
}

#[derive(Debug, Clone, Serialize)]
pub struct StageRef {
    pub name_index: u32,
    pub name: String,
    pub flags: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct StageInstance {
    pub name: String,
    pub mesh_name: String,
    pub translation: [f32; 3],
    pub rotation_rad: [f32; 3],
    pub scale: [f32; 3],
    pub parent: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct Hit {
    pub objects: Vec<HitObject>,
    pub polygons: Vec<HitPolygon>,
    pub vertices: Vec<[f32; 3]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HitObject {
    pub name: String,
    pub flags: u32,
    pub polygon_count: u32,
    pub first_polygon: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct HitPolygon {
    pub vertex_count: u32,
    pub first_vertex: u32,
    pub normal: [f32; 3],
}

/// Parse an STG file (matches arika_stages.py).
pub fn parse_stg(data: &[u8]) -> Result<Stage> {
    // Header: version 0x00000100 LE, "STG ", name_count, template_count
    if data.len() < 16 {
        return Err(ArikaError::Other("truncated STG".into()));
    }
    if &data[0..8] != b"\x00\x01\x00\x00STG " {
        // also accept if magic is at 4
        if &data[4..8] != b"STG " {
            return Err(ArikaError::Other(format!(
                "expected STG header, got {:?}",
                &data[0..8.min(data.len())]
            )));
        }
    }
    let name_count = u32_at(data, 8)? as usize;
    let template_count = u32_at(data, 12)?;
    if 16 + name_count * 16 > data.len() {
        return Err(ArikaError::Other("truncated STG names".into()));
    }

    let mut names = Vec::with_capacity(name_count);
    for i in 0..name_count {
        let o = 16 + i * 16;
        let raw = &data[o..o + 16];
        let nul = raw.iter().position(|&b| b == 0).unwrap_or(16);
        let (n, _, _) = encoding_rs::SHIFT_JIS.decode(&raw[..nul]);
        names.push(n.into_owned());
    }

    let mut nodes: Vec<StageNode> = Vec::new();
    let mut pending: Vec<usize> = Vec::new();
    let mut roots: Vec<usize> = Vec::new();
    let mut cursor = 16 + name_count * 16;

    while cursor + 8 <= data.len() {
        let kind = data[cursor];
        let reference_count = data[cursor + 1];
        let links = data[cursor + 2];
        let flags = data[cursor + 3];
        let name_index = u32_at(data, cursor + 4)? as usize;

        if !matches!(kind, 1 | 2 | 3 | 4 | 5 | 6) {
            break;
        }
        if name_index >= names.len() {
            return Err(ArikaError::Other(format!(
                "invalid STG name index {name_index}"
            )));
        }
        if reference_count > 0 && kind != 3 {
            return Err(ArikaError::Other(
                "unexpected STG inline references on non-kind-3".into(),
            ));
        }

        let size = match kind {
            4 | 6 => 60,
            5 => 96,
            _ => 44 + reference_count as usize * 8,
        };
        if cursor + size > data.len() {
            return Err(ArikaError::Other("truncated STG node body".into()));
        }

        let index = nodes.len();
        let parent = if let Some(p) = pending.pop() {
            p as i32
        } else {
            -1
        };
        if parent < 0 {
            roots.push(index);
        } else {
            nodes[parent as usize].children.push(index);
        }

        let mut translation = [0.0f32; 3];
        let mut rotation = [0.0f32; 3];
        let mut scale = [1.0f32; 3];
        let mut references = Vec::new();

        if matches!(kind, 1 | 2 | 3) {
            translation = [
                f32_at(data, cursor + 8)?,
                f32_at(data, cursor + 12)?,
                f32_at(data, cursor + 16)?,
            ];
            rotation = [
                f32_at(data, cursor + 20)?,
                f32_at(data, cursor + 24)?,
                f32_at(data, cursor + 28)?,
            ];
            scale = [
                f32_at(data, cursor + 32)?,
                f32_at(data, cursor + 36)?,
                f32_at(data, cursor + 40)?,
            ];
            for j in 0..reference_count as usize {
                let off = cursor + 44 + j * 8;
                let ni = u32_at(data, off)?;
                let bits = u32_at(data, off + 4)?;
                let rname = names
                    .get(ni as usize)
                    .cloned()
                    .unwrap_or_else(|| format!("ref_{ni}"));
                references.push(StageRef {
                    name_index: ni,
                    name: rname,
                    flags: bits,
                });
            }
        }

        // Match Python: stack pop order — push sibling parent first, then child,
        // so the next node is the child (if any).
        if links & 2 != 0 {
            if parent >= 0 {
                pending.push(parent as usize);
            }
        }
        if links & 1 != 0 {
            pending.push(index);
        }

        nodes.push(StageNode {
            index,
            kind,
            name_index: name_index as u32,
            name: names[name_index].clone(),
            offset: cursor,
            translation,
            rotation,
            scale,
            flags,
            links,
            parent,
            children: Vec::new(),
            references,
        });

        cursor += size;
    }

    // Prefer STAGE root name for display
    let stage_name = names
        .iter()
        .find(|n| n.eq_ignore_ascii_case("STAGE") || n.eq_ignore_ascii_case("Stage"))
        .cloned()
        .or_else(|| {
            roots
                .iter()
                .rev()
                .map(|&i| nodes[i].name.clone())
                .next()
        })
        .or_else(|| names.last().cloned())
        .unwrap_or_default();

    Ok(Stage {
        name: stage_name,
        names,
        nodes,
        template_count,
        roots,
    })
}

/// Kind-2 mesh instances, optionally restricted to descendants of STAGE root.
pub fn stage_instances(stage: &Stage) -> Vec<StageInstance> {
    // Python places every kind-2 node; filter to STAGE subtree only when requested.
    stage_instances_filtered(stage, false)
}

pub fn stage_instances_filtered(stage: &Stage, prefer_stage_root: bool) -> Vec<StageInstance> {
    let mut allowed: Option<std::collections::HashSet<usize>> = None;
    if prefer_stage_root {
        // Find STAGE root and collect subtree
        if let Some(&root) = stage.roots.iter().find(|&&i| {
            stage.nodes.get(i).map(|n| n.name.eq_ignore_ascii_case("STAGE")).unwrap_or(false)
        }) {
            let mut set = std::collections::HashSet::new();
            let mut stack = vec![root];
            while let Some(i) = stack.pop() {
                set.insert(i);
                if let Some(n) = stage.nodes.get(i) {
                    stack.extend(&n.children);
                }
            }
            allowed = Some(set);
        }
    }

    stage
        .nodes
        .iter()
        .filter(|n| n.kind == 2)
        .filter(|n| allowed.as_ref().map(|s| s.contains(&n.index)).unwrap_or(true))
        .map(|n| StageInstance {
            name: n.name.clone(),
            mesh_name: n.name.clone(),
            translation: n.translation,
            rotation_rad: n.rotation,
            scale: n.scale,
            parent: n.parent,
        })
        .collect()
}

/// Local TRS matrix for a stage node (column-vector order T*R*S; quaternion from
/// half-angle XYZ Euler — matches Python `local_matrix` / `quaternion` exactly).
pub fn stage_node_local_matrix(node: &StageNode) -> glam::Mat4 {
    let s = glam::Mat4::from_scale(glam::Vec3::new(node.scale[0], node.scale[1], node.scale[2]));
    let (x, y, z) = (
        node.rotation[0] * 0.5,
        node.rotation[1] * 0.5,
        node.rotation[2] * 0.5,
    );
    let (sx, sy, sz) = (x.sin(), y.sin(), z.sin());
    let (cx, cy, cz) = (x.cos(), y.cos(), z.cos());
    let q = glam::Quat::from_xyzw(
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    );
    let r = glam::Mat4::from_quat(q);
    let t = glam::Mat4::from_translation(glam::Vec3::new(
        node.translation[0],
        node.translation[1],
        node.translation[2],
    ));
    t * r * s
}

/// World-space matrices for every stage node, composing the parent chain
/// (`world = parent_world * local`), matching Python's glTF node hierarchy.
/// Nodes are processed in topological order (parents before children).
pub fn stage_world_matrices(stage: &Stage) -> Vec<glam::Mat4> {
    let n = stage.nodes.len();
    let mut worlds = vec![glam::Mat4::IDENTITY; n];
    let mut visited = vec![false; n];
    let mut order = Vec::with_capacity(n);

    fn visit_order(i: usize, nodes: &[StageNode], visited: &mut [bool], order: &mut Vec<usize>) {
        if visited[i] {
            return;
        }
        visited[i] = true;
        let p = nodes[i].parent;
        if p >= 0 && (p as usize) < nodes.len() {
            visit_order(p as usize, nodes, visited, order);
        }
        order.push(i);
    }

    for i in 0..n {
        visit_order(i, &stage.nodes, &mut visited, &mut order);
    }

    for &i in &order {
        let node = &stage.nodes[i];
        let local = stage_node_local_matrix(node);
        worlds[i] = if node.parent >= 0 && (node.parent as usize) < n {
            let parent_world = worlds[node.parent as usize];
            parent_world * local
        } else {
            local
        };
    }
    worlds
}

pub fn parse_hit(data: &[u8]) -> Result<Hit> {
    if data.len() < 32 {
        return Err(ArikaError::Other("truncated HIT".into()));
    }
    // \0\0\x02\0HIT  or similar
    let count = u32_at(data, 8)? as usize;
    let objects_at = u32_at(data, 12)? as usize;
    let polygons_at = u32_at(data, 16)? as usize;
    let vertices_at = u32_at(data, 20)? as usize;

    let mut names = Vec::with_capacity(count);
    for i in 0..count {
        let o = 32 + i * 16;
        if o + 16 > data.len() {
            names.push(format!("obj_{i}"));
            continue;
        }
        let raw = &data[o..o + 16];
        let nul = raw.iter().position(|&b| b == 0).unwrap_or(16);
        let (n, _, _) = encoding_rs::SHIFT_JIS.decode(&raw[..nul]);
        names.push(n.into_owned());
    }

    let mut vertices = Vec::new();
    if vertices_at < data.len() {
        for o in (vertices_at..data.len()).step_by(16) {
            if o + 12 > data.len() {
                break;
            }
            vertices.push([
                f32_at(data, o)?,
                f32_at(data, o + 4)?,
                f32_at(data, o + 8)?,
            ]);
        }
    }

    let mut polygons = Vec::new();
    if polygons_at < vertices_at {
        for o in (polygons_at..vertices_at).step_by(32) {
            if o + 32 > data.len() {
                break;
            }
            polygons.push(HitPolygon {
                vertex_count: u32_at(data, o)?,
                first_vertex: u32_at(data, o + 4)?,
                normal: [
                    f32_at(data, o + 16)?,
                    f32_at(data, o + 20)?,
                    f32_at(data, o + 24)?,
                ],
            });
        }
    }

    let mut objects = Vec::with_capacity(count);
    for i in 0..count {
        let o = objects_at + i * 64;
        if o + 12 > data.len() {
            objects.push(HitObject {
                name: names.get(i).cloned().unwrap_or_default(),
                flags: 0,
                polygon_count: 0,
                first_polygon: 0,
            });
            continue;
        }
        objects.push(HitObject {
            name: names.get(i).cloned().unwrap_or_default(),
            flags: u32_at(data, o)?,
            polygon_count: u32_at(data, o + 4)?,
            first_polygon: u32_at(data, o + 8)?,
        });
    }

    Ok(Hit {
        objects,
        polygons,
        vertices,
    })
}

pub fn stage_to_json(stage: &Stage) -> Result<String> {
    Ok(serde_json::to_string_pretty(stage)?)
}

pub fn hit_to_json(hit: &Hit) -> Result<String> {
    Ok(serde_json::to_string_pretty(hit)?)
}

pub fn write_hit_obj(hit: &Hit, path: impl AsRef<std::path::Path>) -> Result<()> {
    use std::io::Write;
    let mut f = std::fs::File::create(path)?;
    writeln!(f, "# Arika HIT export")?;
    for v in &hit.vertices {
        writeln!(f, "v {} {} {}", v[0], v[1], v[2])?;
    }
    for (oi, obj) in hit.objects.iter().enumerate() {
        writeln!(
            f,
            "o {}",
            if obj.name.is_empty() {
                format!("obj_{oi}")
            } else {
                obj.name.clone()
            }
        )?;
        let start = obj.first_polygon as usize;
        let end = (start + obj.polygon_count as usize).min(hit.polygons.len());
        for pi in start..end {
            let poly = &hit.polygons[pi];
            let mut idxs = Vec::new();
            for k in 0..poly.vertex_count as usize {
                idxs.push((poly.first_vertex as usize + k + 1).to_string());
            }
            if idxs.len() >= 3 {
                writeln!(f, "f {}", idxs.join(" "))?;
            }
        }
    }
    Ok(())
}
