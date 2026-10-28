//! FMDL geometry, hierarchy, materials and basic export structures.
//! Port of arika_models.py / MODEL_FORMAT.md.

use crate::container::{
    group_by_magic, i32_at, parse_directory, read_vec4, string_list, u32_at, Chunk,
};
use crate::error::{ArikaError, Result};
use crate::tim2::decode_xpix;
use glam::{Mat4, Quat, Vec3};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize)]
pub struct Model {
    pub name: String,
    pub nodes: Vec<HierarchyNode>,
    pub meshes: Vec<Mesh>,
    pub materials: Vec<Material>,
    pub textures: Vec<TextureSlot>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HierarchyNode {
    pub index: i32,
    pub name: String,
    pub parent: i32,
    pub first_child: i32,
    pub next_sibling: i32,
    pub scale: [f32; 3],
    pub euler_degrees: [f32; 3],
    pub translation: [f32; 3],
    #[serde(skip)]
    pub local: Mat4,
    #[serde(skip)]
    pub world: Mat4,
}

#[derive(Debug, Clone, Serialize)]
pub struct Mesh {
    pub name: String,
    pub flags: u32,
    pub positions: Vec<[f32; 3]>,
    pub normals: Vec<[f32; 3]>,
    pub uvs: Vec<[f32; 2]>,
    pub colors: Vec<[f32; 4]>,
    pub joints: Vec<[u16; 4]>,
    pub weights: Vec<[f32; 4]>,
    pub indices: Vec<u32>,
    pub material_indices: Vec<i32>,
    pub skinned: bool,
    pub morph: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Material {
    pub color_a: [f32; 4],
    pub color_b: [f32; 4],
    pub texture_index: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct TextureSlot {
    pub index: usize,
    pub width: u32,
    pub height: u32,
    #[serde(skip)]
    pub rgba: Vec<u8>,
}

/// Parse an FMDL file.
pub fn parse_fmdl(data: &[u8], name: &str) -> Result<Model> {
    if data.len() < 32 || &data[0..4] != b"FMDL" {
        return Err(ArikaError::Other("expected FMDL".into()));
    }
    let chunks = parse_directory(data, Some(b"FMDL"))?;
    let by_magic = group_by_magic(&chunks);

    let nodes = parse_hierarchy(&by_magic)?;
    let (meshes, materials) = parse_geometry(&by_magic, &nodes)?;
    // Textures come from sibling FPIX — left empty here; caller can attach.
    Ok(Model {
        name: name.to_string(),
        nodes,
        meshes,
        materials,
        textures: Vec::new(),
    })
}

/// Attach textures from a sibling FPIX container.
pub fn attach_textures(model: &mut Model, fpix_data: &[u8]) -> Result<()> {
    if fpix_data.len() < 32 || &fpix_data[0..4] != b"FPIX" {
        return Err(ArikaError::Other("expected FPIX".into()));
    }
    let chunks = parse_directory(fpix_data, Some(b"FPIX"))?;
    model.textures.clear();
    let mut errors = Vec::new();
    for (i, chunk) in chunks.iter().enumerate() {
        if chunk.magic != *b"XPIX" {
            continue;
        }
        match decode_xpix(&chunk.data) {
            Ok(img) => {
                model.textures.push(TextureSlot {
                    index: model.textures.len(),
                    width: img.width,
                    height: img.height,
                    rgba: img.rgba,
                });
            }
            Err(e) => errors.push(format!("XPIX[{i}]: {e}")),
        }
    }
    if model.textures.is_empty() && !errors.is_empty() {
        return Err(ArikaError::Other(format!(
            "no textures decoded ({})",
            errors.join("; ")
        )));
    }
    Ok(())
}

fn parse_hierarchy(by_magic: &HashMap<String, Vec<&Chunk>>) -> Result<Vec<HierarchyNode>> {
    let dhie = match by_magic.get("DHIE").and_then(|v| v.first()) {
        Some(c) => c,
        None => return Ok(Vec::new()),
    };
    let children = parse_directory(&dhie.data, Some(b"DHIE"))?;
    let hierarchy = children
        .iter()
        .find(|c| c.magic == *b"XHIE")
        .ok_or_else(|| ArikaError::Other("DHIE has no XHIE".into()))?;
    let count = u32_at(&hierarchy.data, 8)? as usize;
    if hierarchy.data.len() != 32 + count * 64 {
        return Err(ArikaError::Other("unexpected XHIE record size".into()));
    }
    let names = if let Some(xnon) = by_magic.get("XNON").and_then(|v| v.first()) {
        string_list(&xnon.data, count)?
    } else {
        (0..count).map(|i| format!("node_{i}")).collect()
    };

    let mut nodes = Vec::with_capacity(count);
    for i in 0..count {
        let offset = 32 + i * 64;
        let index = i32_at(&hierarchy.data, offset)?;
        let parent = i32_at(&hierarchy.data, offset + 4)?;
        let child = i32_at(&hierarchy.data, offset + 8)?;
        let sibling = i32_at(&hierarchy.data, offset + 12)?;
        if index != i as i32 {
            return Err(ArikaError::Other("invalid skeleton index".into()));
        }
        let s = read_vec4(&hierarchy.data, offset + 16)?;
        let r = read_vec4(&hierarchy.data, offset + 32)?;
        let t = read_vec4(&hierarchy.data, offset + 48)?;
        let euler = [r[0], r[1], r[2]];
        let local = srt_matrix([s[0], s[1], s[2]], euler, [t[0], t[1], t[2]]);
        nodes.push(HierarchyNode {
            index,
            name: names.get(i).cloned().unwrap_or_else(|| format!("node_{i}")),
            parent,
            first_child: child,
            next_sibling: sibling,
            scale: [s[0], s[1], s[2]],
            euler_degrees: euler,
            translation: [t[0], t[1], t[2]],
            local,
            world: Mat4::IDENTITY,
        });
    }
    compute_world_matrices(&mut nodes);
    Ok(nodes)
}

fn srt_matrix(scale: [f32; 3], euler_deg: [f32; 3], translation: [f32; 3]) -> Mat4 {
    let sx = scale[0];
    let sy = scale[1];
    let sz = scale[2];
    let s = Mat4::from_scale(Vec3::new(sx, sy, sz));
    // degrees → radians, XYZ order → quaternion (verified against EE)
    let (x, y, z) = (
        euler_deg[0].to_radians() * 0.5,
        euler_deg[1].to_radians() * 0.5,
        euler_deg[2].to_radians() * 0.5,
    );
    let (sx_, sy_, sz_) = (x.sin(), y.sin(), z.sin());
    let (cx, cy, cz) = (x.cos(), y.cos(), z.cos());
    let qx = sx_ * cy * cz - cx * sy_ * sz_;
    let qy = cx * sy_ * cz + sx_ * cy * sz_;
    let qz = cx * cy * sz_ - sx_ * sy_ * cz;
    let qw = cx * cy * cz + sx_ * sy_ * sz_;
    let r = Mat4::from_quat(Quat::from_xyzw(qx, qy, qz, qw));
    let t = Mat4::from_translation(Vec3::new(translation[0], translation[1], translation[2]));
    t * r * s
}

fn compute_world_matrices(nodes: &mut [HierarchyNode]) {
    // topological: parents before children
    let n = nodes.len();
    let mut order = Vec::with_capacity(n);
    let mut visited = vec![false; n];
    fn visit(i: usize, nodes: &[HierarchyNode], visited: &mut [bool], order: &mut Vec<usize>) {
        if visited[i] {
            return;
        }
        visited[i] = true;
        let p = nodes[i].parent;
        if p >= 0 && (p as usize) < nodes.len() {
            visit(p as usize, nodes, visited, order);
        }
        order.push(i);
    }
    for i in 0..n {
        visit(i, nodes, &mut visited, &mut order);
    }
    for &i in &order {
        let p = nodes[i].parent;
        nodes[i].world = if p >= 0 && (p as usize) < n {
            nodes[p as usize].world * nodes[i].local
        } else {
            nodes[i].local
        };
    }
}

fn parse_geometry(
    by_magic: &HashMap<String, Vec<&Chunk>>,
    nodes: &[HierarchyNode],
) -> Result<(Vec<Mesh>, Vec<Material>)> {
    let materials = parse_materials(by_magic)?;
    let mut meshes = Vec::new();

    // Mesh names from XMON (sequential CP932 strings after 0x20 header)
    let mesh_names: Vec<String> = if let Some(xmon) = by_magic.get("XMON").and_then(|v| v.first()) {
        let count_hint = by_magic
            .get("XMTX")
            .map(|v| v.len())
            .or_else(|| {
                by_magic.get("DMOD").and_then(|d| d.first()).and_then(|c| {
                    parse_directory(&c.data, None).ok().map(|ch| {
                        ch.iter().filter(|x| x.magic == *b"XMOD").count()
                    })
                })
            })
            .or_else(|| by_magic.get("XMOD").map(|v| v.len()))
            .unwrap_or(0);
        match string_list(&xmon.data, count_hint.max(1)) {
            Ok(n) => n,
            Err(_) => {
                // fall back: split all strings in body
                let body = if xmon.data.len() > 32 { &xmon.data[32..] } else { &xmon.data[..] };
                let mut names = Vec::new();
                let mut at = 0usize;
                while at < body.len() && names.len() < 4096 {
                    if body[at] == 0 { at += 1; continue; }
                    let end = body[at..].iter().position(|&b| b == 0).map(|p| at + p).unwrap_or(body.len());
                    let (name, _, _) = encoding_rs::SHIFT_JIS.decode(&body[at..end]);
                    if !name.is_empty() {
                        names.push(name.into_owned());
                    }
                    at = end + 1;
                }
                names
            }
        }
    } else {
        Vec::new()
    };

    // Palettes from XMTX
    let palettes: Vec<Vec<i32>> = by_magic
        .get("XMTX")
        .map(|chunks| {
            chunks
                .iter()
                .filter_map(|c| {
                    if c.data.len() < 32 + 128 {
                        return None;
                    }
                    let mut row = Vec::with_capacity(32);
                    for i in 0..32 {
                        row.push(i32_at(&c.data, 32 + i * 4).ok()?);
                    }
                    Some(row)
                })
                .collect()
        })
        .unwrap_or_default();

    // Material assignment lists (XMAL) — stored inside DMAT directory
    let mut mat_lists: Vec<Vec<i32>> = Vec::new();
    if let Some(dmats) = by_magic.get("DMAT") {
        for d in dmats {
            if let Ok(children) = parse_directory(&d.data, None) {
                for c in children {
                    if c.magic == *b"XMAL" {
                        // One XMAL chunk contains N rows (32 + N*128 bytes)
                        let data = &c.data;
                        let n_rows = if data.len() >= 32 { (data.len() - 32) / 128 } else { 0 };
                        for ri in 0..n_rows {
                            let off = 32 + ri * 128;
                            if off + 128 > data.len() { break; }
                            let mut row = Vec::with_capacity(32);
                            for i in 0..32 {
                                if let Ok(v) = i32_at(data, off + i * 4) {
                                    row.push(v);
                                }
                            }
                            row.retain(|&v| v >= 0);
                            mat_lists.push(row);
                        }
                    }
                }
            }
        }
    }
    // Fallback: top-level XMAL chunks
    if mat_lists.is_empty() {
        if let Some(chunks) = by_magic.get("XMAL") {
            for c in chunks {
                if c.data.len() >= 32 + 128 {
                    let mut row = Vec::with_capacity(32);
                    for i in 0..32 {
                        if let Ok(v) = i32_at(&c.data, 32 + i * 4) {
                            row.push(v);
                        }
                    }
                    row.retain(|&v| v >= 0);
                    mat_lists.push(row);
                }
            }
        }
    }

    eprintln!("parse_geometry: mat_lists.len()={}", mat_lists.len());
    let mut xmods: Vec<&Chunk> = Vec::new();
    if let Some(dmod) = by_magic.get("DMOD").and_then(|v| v.first()) {
        if let Ok(children) = parse_directory(&dmod.data, Some(b"DMOD")) {
            for c in &children {
                if c.magic == *b"XMOD" {
                    // need owned or re-parse; for simplicity re-collect from top-level if present
                }
            }
            // Fall through: also check top-level XMOD
        }
    }
    if let Some(xs) = by_magic.get("XMOD") {
        xmods.extend(xs.iter().copied());
    }
    // Also search inside DMOD
    if let Some(dmods) = by_magic.get("DMOD") {
        for d in dmods {
            if let Ok(children) = parse_directory(&d.data, None) {
                let mut dmod_mi = 0usize;
                for c in children {
                    if c.magic == *b"XMOD" {
                        // We need to keep data; push into a owned list later
                        // For now parse inline
                        if let Ok(mesh) = parse_xmod(
                            &c.data,
                            mesh_names.get(meshes.len()).map(|s| s.as_str()).unwrap_or(""),
                            palettes.get(meshes.len()),
                            mat_lists.get(dmod_mi),
                            nodes.len(),
                        ) {
                            meshes.push(mesh);
                            dmod_mi += 1;
                        }
                    }
                }
            }
        }
    }

    for (mi, chunk) in xmods.iter().enumerate() {
        let name = mesh_names
            .get(mi)
            .map(|s| s.as_str())
            .unwrap_or("");
        if let Ok(mesh) = parse_xmod(
            &chunk.data,
            name,
            palettes.get(mi),
            mat_lists.get(mi),
            nodes.len(),
        ) {
            meshes.push(mesh);
        }
    }

    Ok((meshes, materials))
}

fn parse_materials(by_magic: &HashMap<String, Vec<&Chunk>>) -> Result<Vec<Material>> {
    let mut materials = Vec::new();
    // DMAT → XMAT
    if let Some(dmats) = by_magic.get("DMAT") {
        for d in dmats {
            if let Ok(children) = parse_directory(&d.data, None) {
                for c in children {
                    if c.magic == *b"XMAT" {
                        materials.extend(parse_xmat(&c.data)?);
                    }
                }
            }
        }
    }
    if let Some(xmats) = by_magic.get("XMAT") {
        for c in xmats {
            materials.extend(parse_xmat(&c.data)?);
        }
    }
    Ok(materials)
}

fn parse_xmat(data: &[u8]) -> Result<Vec<Material>> {
    if data.len() < 32 {
        return Ok(Vec::new());
    }
    let count = u32_at(data, 8)? as usize;
    let mut out = Vec::with_capacity(count);
    for i in 0..count {
        let offset = 32 + i * 0x30;
        if offset + 0x30 > data.len() {
            break;
        }
        let color_a = read_vec4(data, offset)?;
        let color_b = read_vec4(data, offset + 16)?;
        let tex = i32_at(data, offset + 32)?;
        out.push(Material {
            color_a,
            color_b,
            texture_index: tex,
        });
    }
    Ok(out)
}

fn parse_xmod(
    data: &[u8],
    name: &str,
    palette: Option<&Vec<i32>>,
    mat_list: Option<&Vec<i32>>,
    _bone_count: usize,
) -> Result<Mesh> {
    if data.len() < 0x1B0 || &data[0..4] != b"XMOD" {
        return Err(ArikaError::Other("invalid XMOD".into()));
    }
    let flags = u32_at(data, 12)?;
    if ![0, 1, 2, 3, 4, 6, 11].contains(&flags) {
        return Err(ArikaError::Other(format!("unsupported XMOD flags {flags}")));
    }
    let skinned = (flags & 2) != 0 && (flags & 8) == 0;
    let morph = (flags & 8) != 0;
    let colored = (flags & 4) != 0;
    let stride_vecs = 3 + 2 * ((flags & 2) != 0) as u32 + colored as u32;

    let mut positions = Vec::new();
    let mut normals = Vec::new();
    let mut uvs = Vec::new();
    let mut colors = Vec::new();
    let mut joints = Vec::new();
    let mut weights = Vec::new();
    let mut indices = Vec::new();
    let mut material_indices = Vec::new();

    let mut dma = 0x1A0usize;
    let mut material_index = 0usize;
    let mat_assign = mat_list.cloned().unwrap_or_default();

    while dma + 16 <= data.len() {
        let tag = u32_at(data, dma)?;
        if (tag >> 28) != 6 {
            break; // not RET
        }
        let qwc = (tag & 0xFFFF) as usize;
        let end = dma + 16 + qwc * 16;
        if end > data.len() {
            break;
        }
        let assigned_mat = mat_assign
            .get(material_index)
            .copied()
            .unwrap_or(-1);
        material_index += 1;

        let mut at = dma + 16;
        let mut strip: Vec<usize> = Vec::new(); // vertex indices in this packet

        while at + 4 <= end {
            let word = u32_at(data, at)?;
            at += 4;
            let command = (word >> 24) & 0x7F;
            if command == 0 || command == 1 || command == 0x17 {
                continue; // NOP / STCYCL / MSCNT
            }
            if command != 0x6C {
                // unsupported VIF — stop this packet
                break;
            }
            let count = {
                let c = (word >> 16) & 0xFF;
                if c == 0 {
                    256
                } else {
                    c as usize
                }
            };
            let payload_end = at + count * 16;
            if payload_end > end || count < 2 {
                break;
            }
            // GIF tag at at+16, low 15 bits = vertex count
            let n = (u32_at(data, at + 16)? & 0x7FFF) as usize;
            if n == 0 || count != 2 + n * stride_vecs as usize {
                break;
            }
            let base_vert = positions.len();
            for i in 0..n {
                let voff = at + 32 + i * stride_vecs as usize * 16;
                let need = stride_vecs as usize * 16;
                if voff + need > data.len() {
                    break;
                }
                // Layout matches Python mesh_geometry values[]:
                //   [0]=pos [1]=normal [2]=color? [2 or 3]=uv ... skin/morph
                let pos = read_vec4(data, voff)?;
                let nrm = read_vec4(data, voff + 16)?;
                let mut slot = 2usize; // next vec index after pos+nrm
                let mut col = [1.0f32, 1.0, 1.0, 1.0];
                if colored {
                    let c = read_vec4(data, voff + slot * 16)?;
                    col = [
                        (c[0] / 128.0).clamp(0.0, 1.0),
                        (c[1] / 128.0).clamp(0.0, 1.0),
                        (c[2] / 128.0).clamp(0.0, 1.0),
                        (c[3] / 128.0).clamp(0.0, 1.0),
                    ];
                    slot += 1;
                }
                let stq = read_vec4(data, voff + slot * 16)?;
                slot += 1;
                let uv = [stq[0], stq[1]];

                // ADC bit in position W
                let pos_w_bits = u32_at(data, voff + 12)?;
                let suppress = (pos_w_bits & (1 << 15)) != 0;

                positions.push([pos[0], pos[1], pos[2]]);
                let normal = [nrm[0], nrm[1], nrm[2]];
                let flip = nrm[3] < 0.0;
                normals.push(normal);
                uvs.push(uv);

                let mut jnts = [0u16; 4];
                let mut wts = [0.0f32; 4];
                let mut next = voff + slot * 16;

                if skinned {
                    if next + 32 <= data.len() {
                        // palette addresses (u32 / 4) then weights
                        let a0 = u32_at(data, next)? / 4;
                        let a1 = u32_at(data, next + 4)? / 4;
                        let a2 = u32_at(data, next + 8)? / 4;
                        let a3 = u32_at(data, next + 12)? / 4;
                        let w = read_vec4(data, next + 16)?;
                        // map through palette row if available
                        let map_joint = |addr: u32| -> u16 {
                            if let Some(pal) = palette {
                                let slot = addr as usize;
                                if slot < pal.len() && pal[slot] >= 0 {
                                    return pal[slot] as u16;
                                }
                            }
                            addr as u16
                        };
                        jnts = [
                            map_joint(a0),
                            map_joint(a1),
                            map_joint(a2),
                            map_joint(a3),
                        ];
                        wts = [w[0], w[1], w[2], w[3]];
                    }
                }
                colors.push(col);
                joints.push(jnts);
                weights.push(wts);

                let vi = base_vert + i;
                if !suppress && strip.len() >= 2 {
                    let a = strip[strip.len() - 2] as u32;
                    let b = strip[strip.len() - 1] as u32;
                    let c = vi as u32;
                    if flip {
                        indices.extend_from_slice(&[a, c, b]);
                    } else {
                        indices.extend_from_slice(&[a, b, c]);
                    }
                    material_indices.push(assigned_mat);
                }
                strip.push(vi);
            }
            at = payload_end;
        }
        dma = end;
    }

    Ok(Mesh {
        name: if name.is_empty() {
            format!("mesh_{}", positions.len())
        } else {
            name.to_string()
        },
        flags,
        positions,
        normals,
        uvs,
        colors,
        joints,
        weights,
        indices,
        material_indices,
        skinned,
        morph,
    })
}

/// Export model geometry summary as JSON.
pub fn model_to_json(model: &Model) -> Result<String> {
    Ok(serde_json::to_string_pretty(model)?)
}

/// Very simple OBJ exporter (bind-pose positions only).
pub fn write_obj(model: &Model, path: impl AsRef<std::path::Path>) -> Result<()> {
    use std::io::Write;
    let mut f = std::fs::File::create(path)?;
    writeln!(f, "# Arika FMDL export")?;
    let mut vbase = 1u32;
    for mesh in &model.meshes {
        writeln!(f, "o {}", mesh.name)?;
        for p in &mesh.positions {
            writeln!(f, "v {} {} {}", p[0], p[1], p[2])?;
        }
        for n in &mesh.normals {
            writeln!(f, "vn {} {} {}", n[0], n[1], n[2])?;
        }
        for uv in &mesh.uvs {
            writeln!(f, "vt {} {}", uv[0], 1.0 - uv[1])?;
        }
        for tri in mesh.indices.chunks_exact(3) {
            let a = tri[0] + vbase;
            let b = tri[1] + vbase;
            let c = tri[2] + vbase;
            writeln!(f, "f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")?;
        }
        vbase += mesh.positions.len() as u32;
    }
    Ok(())
}
