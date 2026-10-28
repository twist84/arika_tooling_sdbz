use crate::models::Model;
use crate::stages::{Hit, Stage};
use serde_json::{json, Value};
use std::collections::HashMap;

fn pad4(blob: &mut Vec<u8>) {
    while blob.len() % 4 != 0 {
        blob.push(0);
    }
}

fn add_vec3_accessor(doc: &mut Value, blob: &mut Vec<u8>, data: &[[f32; 3]], bounds: bool) -> usize {
    pad4(blob);
    let offset = blob.len();
    for v in data {
        for c in v {
            blob.extend_from_slice(&c.to_le_bytes());
        }
    }
    pad4(blob);
    let bv_idx = doc["bufferViews"].as_array().unwrap().len();
    doc["bufferViews"].as_array_mut().unwrap().push(json!({
        "buffer": 0,
        "byteOffset": offset,
        "byteLength": data.len() * 12,
        "target": 34962
    }));
    let mut acc = json!({
        "bufferView": bv_idx,
        "byteOffset": 0,
        "componentType": 5126,
        "count": data.len(),
        "type": "VEC3"
    });
    if bounds && !data.is_empty() {
        let mut mn = [f32::MAX; 3];
        let mut mx = [f32::MIN; 3];
        for v in data {
            for i in 0..3 {
                mn[i] = mn[i].min(v[i]);
                mx[i] = mx[i].max(v[i]);
            }
        }
        acc["min"] = json!(mn);
        acc["max"] = json!(mx);
    }
    let acc_idx = doc["accessors"].as_array().unwrap().len();
    doc["accessors"].as_array_mut().unwrap().push(acc);
    acc_idx
}

fn add_vec2_accessor(doc: &mut Value, blob: &mut Vec<u8>, data: &[[f32; 2]]) -> usize {
    pad4(blob);
    let offset = blob.len();
    for v in data {
        for c in v {
            blob.extend_from_slice(&c.to_le_bytes());
        }
    }
    pad4(blob);
    let bv_idx = doc["bufferViews"].as_array().unwrap().len();
    doc["bufferViews"].as_array_mut().unwrap().push(json!({
        "buffer": 0,
        "byteOffset": offset,
        "byteLength": data.len() * 8,
        "target": 34962
    }));
    let acc_idx = doc["accessors"].as_array().unwrap().len();
    doc["accessors"].as_array_mut().unwrap().push(json!({
        "bufferView": bv_idx,
        "byteOffset": 0,
        "componentType": 5126,
        "count": data.len(),
        "type": "VEC2"
    }));
    acc_idx
}

fn add_vec4_accessor(doc: &mut Value, blob: &mut Vec<u8>, data: &[[f32; 4]]) -> usize {
    pad4(blob);
    let offset = blob.len();
    for v in data {
        for c in v {
            blob.extend_from_slice(&c.to_le_bytes());
        }
    }
    pad4(blob);
    let bv_idx = doc["bufferViews"].as_array().unwrap().len();
    doc["bufferViews"].as_array_mut().unwrap().push(json!({
        "buffer": 0,
        "byteOffset": offset,
        "byteLength": data.len() * 16,
        "target": 34962
    }));
    let acc_idx = doc["accessors"].as_array().unwrap().len();
    doc["accessors"].as_array_mut().unwrap().push(json!({
        "bufferView": bv_idx,
        "byteOffset": 0,
        "componentType": 5126,
        "count": data.len(),
        "type": "VEC4"
    }));
    acc_idx
}

fn add_scalar_u32_accessor(doc: &mut Value, blob: &mut Vec<u8>, data: &[u32]) -> usize {
    pad4(blob);
    let offset = blob.len();
    for v in data {
        blob.extend_from_slice(&v.to_le_bytes());
    }
    pad4(blob);
    let bv_idx = doc["bufferViews"].as_array().unwrap().len();
    doc["bufferViews"].as_array_mut().unwrap().push(json!({
        "buffer": 0,
        "byteOffset": offset,
        "byteLength": data.len() * 4,
        "target": 34963
    }));
    let acc_idx = doc["accessors"].as_array().unwrap().len();
    doc["accessors"].as_array_mut().unwrap().push(json!({
        "bufferView": bv_idx,
        "byteOffset": 0,
        "componentType": 5125,
        "count": data.len(),
        "type": "SCALAR"
    }));
    acc_idx
}

pub fn build_gltf(model: &Model, motions: &[crate::motion::Motion], mesh_filter: Option<&[String]>) -> Result<Value, crate::error::ArikaError> {
    let mut doc = json!({
        "asset": {"version": "2.0", "generator": "arika-rs"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "materials": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": []
    });
    let mut blob: Vec<u8> = Vec::new();

    // materials
    {
        let mats = doc["materials"].as_array_mut().unwrap();
        if model.materials.is_empty() {
            mats.push(json!({
                "name": "default",
                "pbrMetallicRoughness": {"baseColorFactor": [1.0,1.0,1.0,1.0], "metallicFactor": 0.0, "roughnessFactor": 0.8},
                "doubleSided": true,
                "alphaMode": "MASK",
                "alphaCutoff": 0.1
            }));
        } else {
            for (i, m) in model.materials.iter().enumerate() {
                let _ca = m.color_a;
                let mut mat = json!({
                    "name": format!("mat_{}", i),
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.8
                    },
                    "doubleSided": true,
                    "alphaMode": "MASK",
                    "alphaCutoff": 0.1
                });
                mat["extras"] = json!({"texture_index": m.texture_index});
                mats.push(mat);
            }
        }
    }

    // textures
    let mut tex_index_map: Vec<Option<usize>> = Vec::new();
    {
        let mut images = Vec::new();
        let mut textures = Vec::new();
        let mut samplers = Vec::new();
        samplers.push(json!({"magFilter":9728,"minFilter":9728,"wrapS":10497,"wrapT":10497}));
        for (ti, tex) in model.textures.iter().enumerate() {
            if tex.rgba.is_empty() || tex.width == 0 || tex.height == 0 {
                tex_index_map.push(None);
                continue;
            }
            match crate::tim2::encode_png(tex.width, tex.height, &tex.rgba) {
                Ok(png_bytes) => {
                    use base64::Engine;
                    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_bytes);
                    let img_idx = images.len();
                    images.push(json!({"name": format!("tex_{}", ti), "mimeType": "image/png", "uri": format!("data:image/png;base64,{}", b64)}));
                    let tex_idx = textures.len();
                    textures.push(json!({"name": format!("texture_{}", ti), "sampler": 0, "source": img_idx}));
                    tex_index_map.push(Some(tex_idx));
                }
                Err(_) => tex_index_map.push(None),
            }
        }
        if !images.is_empty() {
            doc["samplers"] = json!(samplers);
            doc["images"] = json!(images);
            doc["textures"] = json!(textures);
        }
    }
    // wire materials
    if let Some(mats) = doc["materials"].as_array_mut() {
        for (mi, m) in model.materials.iter().enumerate() {
            if mi >= mats.len() { break; }
            let tidx = m.texture_index;
            if tidx >= 0 {
                let tidx = tidx as usize;
                if let Some(Some(gltf_tex)) = tex_index_map.get(tidx) {
                    if let Some(pbr) = mats[mi].get_mut("pbrMetallicRoughness") {
                        pbr.as_object_mut().unwrap().insert("baseColorTexture".into(), json!({"index": gltf_tex}));
                    }
                }
            }
            if let Some(o) = mats[mi].as_object_mut() { o.remove("extras"); }
        }
    }

    let mesh_filter_set: Option<std::collections::HashSet<String>> = mesh_filter.map(|f| f.iter().cloned().collect());

    for mesh in &model.meshes {
        if mesh.positions.is_empty() || mesh.indices.is_empty() { continue; }
        if let Some(set) = &mesh_filter_set {
            if !set.contains(&mesh.name) { continue; }
        }
        // split by material
        let mut map: std::collections::BTreeMap<i32, Vec<u32>> = std::collections::BTreeMap::new();
        let ntri = mesh.indices.len() / 3;
        for ti in 0..ntri {
            let mat = mesh.material_indices.get(ti).copied().unwrap_or(-1);
            let tri = &mesh.indices[ti*3..ti*3+3];
            map.entry(mat).or_default().extend_from_slice(tri);
        }
        if map.is_empty() { map.insert(-1, mesh.indices.clone()); }
        let parts: Vec<(i32, Vec<u32>)> = map.into_iter().collect();

        let colors = if mesh.colors.len() == mesh.positions.len() {
            mesh.colors.clone()
        } else {
            vec![[1.0, 1.0, 1.0, 1.0]; mesh.positions.len()]
        };
        let color_acc = add_vec4_accessor(&mut doc, &mut blob, &colors);
        let arika: Vec<u32> = (0..mesh.positions.len() as u32).collect();
        let arika_acc = add_scalar_u32_accessor(&mut doc, &mut blob, &arika);
        let pos_acc = add_vec3_accessor(&mut doc, &mut blob, &mesh.positions, true);
        let normals = if mesh.normals.len() == mesh.positions.len() { mesh.normals.clone() } else { vec![[0.0,1.0,0.0]; mesh.positions.len()] };
        let norm_acc = add_vec3_accessor(&mut doc, &mut blob, &normals, false);
        let uvs = if mesh.uvs.len() == mesh.positions.len() { mesh.uvs.clone() } else { vec![[0.0,0.0]; mesh.positions.len()] };
        let uv_acc = add_vec2_accessor(&mut doc, &mut blob, &uvs);

        let mut primitives = Vec::new();
        for (mat_i, part_indices) in &parts {
            let idx_acc = add_scalar_u32_accessor(&mut doc, &mut blob, part_indices);
            let mat = if *mat_i >= 0 { *mat_i as usize } else { 0usize };
            let mat = if mat < model.materials.len() || model.materials.is_empty() { mat } else { 0 };
            primitives.push(json!({
                "attributes": {
                    "POSITION": pos_acc,
                    "NORMAL": norm_acc,
                    "TEXCOORD_0": uv_acc,
                    "COLOR_0": color_acc,
                    "_ARIKA_VERTEX": arika_acc
                },
                "indices": idx_acc,
                "material": mat,
                "mode": 4
            }));
        }
        if primitives.is_empty() {
            let colors = if mesh.colors.len() == mesh.positions.len() {
                mesh.colors.clone()
            } else {
                vec![[1.0, 1.0, 1.0, 1.0]; mesh.positions.len()]
            };
            let color_acc = add_vec4_accessor(&mut doc, &mut blob, &colors);
            let arika: Vec<u32> = (0..mesh.positions.len() as u32).collect();
            let arika_acc = add_scalar_u32_accessor(&mut doc, &mut blob, &arika);
            let pos_acc = add_vec3_accessor(&mut doc, &mut blob, &mesh.positions, true);
            let normals = if mesh.normals.len() == mesh.positions.len() { mesh.normals.clone() } else { vec![[0.0,1.0,0.0]; mesh.positions.len()] };
            let norm_acc = add_vec3_accessor(&mut doc, &mut blob, &normals, false);
            let uvs = if mesh.uvs.len() == mesh.positions.len() { mesh.uvs.clone() } else { vec![[0.0,0.0]; mesh.positions.len()] };
            let uv_acc = add_vec2_accessor(&mut doc, &mut blob, &uvs);
            let idx_acc = add_scalar_u32_accessor(&mut doc, &mut blob, &mesh.indices);
            primitives.push(json!({
                "attributes": {"POSITION": pos_acc, "NORMAL": norm_acc, "TEXCOORD_0": uv_acc, "COLOR_0": color_acc, "_ARIKA_VERTEX": arika_acc},
                "indices": idx_acc,
                "material": 0,
                "mode": 4
            }));
        }
        doc["meshes"].as_array_mut().unwrap().push(json!({"name": mesh.name, "primitives": primitives}));
    }

    // nodes: one per mesh, plus a model_root wrapping them
    let mesh_count = doc["meshes"].as_array().unwrap().len();
    let mut scene_nodes = Vec::new();
    if mesh_count > 0 {
        // create mesh nodes first
        let mut mesh_node_indices = Vec::new();
        for i in 0..mesh_count {
            let ni = doc["nodes"].as_array().unwrap().len();
            doc["nodes"].as_array_mut().unwrap().push(json!({"name": format!("mesh_{}", i), "mesh": i}));
            mesh_node_indices.push(ni);
        }
        let root_idx = doc["nodes"].as_array().unwrap().len();
        doc["nodes"].as_array_mut().unwrap().push(json!({"name": "model_root", "children": mesh_node_indices}));
        scene_nodes.push(root_idx);
    }
    doc["scenes"][0]["nodes"] = json!(scene_nodes);

    // finalize buffer
    use base64::Engine;
    pad4(&mut blob);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&blob);
    doc["buffers"].as_array_mut().unwrap().push(json!({
        "byteLength": blob.len(),
        "uri": format!("data:application/octet-stream;base64,{}", b64)
    }));

    let _ = motions;
    Ok(doc)
}

pub fn write_gltf(model: &Model, motions: &[crate::motion::Motion], path: impl AsRef<std::path::Path>, mesh_filter: Option<&[String]>) -> Result<(), crate::error::ArikaError> {
    let doc = build_gltf(model, motions, mesh_filter)?;
    let text = serde_json::to_string(&doc)?;
    std::fs::write(path, text)?;
    Ok(())
}

pub fn build_stage_gltf(model: &Model, stage: &Stage, hit: Option<&Hit>) -> Result<Value, crate::error::ArikaError> {
    let mut doc = build_gltf(model, &[], None)?;

    let mut by_mesh: HashMap<String, usize> = HashMap::new();
    if let Some(meshes) = doc.get("meshes").and_then(|v| v.as_array()) {
        for (i, m) in meshes.iter().enumerate() {
            if let Some(name) = m.get("name").and_then(|v| v.as_str()) {
                by_mesh.insert(name.to_string(), i);
            }
        }
    }

    doc.as_object_mut().unwrap().insert("nodes".into(), Value::Array(vec![]));
    doc.as_object_mut().unwrap().insert("scenes".into(), Value::Array(vec![]));
    doc.as_object_mut().unwrap().insert("scene".into(), json!(0));

    fn quat_xyz(r: [f32; 3]) -> [f64; 4] {
        let (x, y, z) = (r[0] * 0.5, r[1] * 0.5, r[2] * 0.5);
        let (sx, sy, sz) = (x.sin(), y.sin(), z.sin());
        let (cx, cy, cz) = (x.cos(), y.cos(), z.cos());
        [
            (sx * cy * cz - cx * sy * sz) as f64,
            (cx * sy * cz + sx * cy * sz) as f64,
            (cx * cy * sz - sx * sy * cz) as f64,
            (cx * cy * cz + sx * sy * sz) as f64,
        ]
    }

    let n = stage.nodes.len();
    let mut placeholder: Vec<Value> = vec![json!({}); n];
    let mut instances = 0usize;
    for node in &stage.nodes {
        let mut out = serde_json::Map::new();
        let name = if node.name.is_empty() { format!("node {}", node.index) } else { node.name.clone() };
        out.insert("name".into(), json!(name));
        out.insert("translation".into(), json!(node.translation));
        out.insert("rotation".into(), json!(quat_xyz(node.rotation)));
        out.insert("scale".into(), json!(node.scale));
        if !node.children.is_empty() {
            out.insert("children".into(), json!(node.children));
        }
        if node.kind == 2 {
            if let Some(&mi) = by_mesh.get(&node.name) {
                out.insert("mesh".into(), json!(mi));
                instances += 1;
            }
        }
        let mut extras = serde_json::Map::new();
        extras.insert("stg_offset".into(), json!(node.offset));
        extras.insert("kind".into(), json!(node.kind));
        extras.insert("flags".into(), json!(node.flags));
        out.insert("extras".into(), Value::Object(extras));
        placeholder[node.index] = Value::Object(out);
    }
    let nodes_arr = doc.get_mut("nodes").unwrap().as_array_mut().unwrap();
    nodes_arr.clear();
    nodes_arr.extend(placeholder);

    let effect_root = if stage.roots.len() >= 2 { stage.roots[stage.roots.len()-2] } else { 0 };
    let stage_root = if !stage.roots.is_empty() { *stage.roots.last().unwrap() } else { 0 };
    let scenes = doc.get_mut("scenes").unwrap().as_array_mut().unwrap();
    scenes.push(json!({"name": "Stage", "nodes": [stage_root]}));
    scenes.push(json!({"name": "Effects", "nodes": [effect_root]}));
    if stage.template_count > 0 && stage.roots.len() >= 2 {
        let tmpl: Vec<usize> = stage.roots[..stage.roots.len()-2].to_vec();
        scenes.push(json!({"name": "Templates", "nodes": tmpl}));
    }

    if let Some(hit) = hit {
        let mats = doc.get_mut("materials").unwrap().as_array_mut().unwrap();
        let mat_idx = mats.len();
        mats.push(json!({
            "name": "Collision wireframe",
            "emissiveFactor": [0.1,1.0,0.2],
            "pbrMetallicRoughness": {"baseColorFactor":[0.1,1.0,0.2,1.0],"metallicFactor":0.0,"roughnessFactor":1.0}
        }));

        let mut pos_bytes: Vec<u8> = Vec::new();
        for v in &hit.vertices {
            for c in v { pos_bytes.extend_from_slice(&c.to_le_bytes()); }
        }
        use base64::Engine;
        pad4(&mut pos_bytes);
        let buffers = doc.get_mut("buffers").unwrap().as_array_mut().unwrap();
        let buf_idx = buffers.len();
        let b64 = base64::engine::general_purpose::STANDARD.encode(&pos_bytes);
        buffers.push(json!({"byteLength": pos_bytes.len(), "uri": format!("data:application/octet-stream;base64,{}", b64)}));
        let bvs = doc.get_mut("bufferViews").unwrap().as_array_mut().unwrap();
        let bv_idx = bvs.len();
        bvs.push(json!({"buffer": buf_idx, "byteOffset": 0, "byteLength": hit.vertices.len()*12, "target": 34962}));
        let accs = doc.get_mut("accessors").unwrap().as_array_mut().unwrap();
        let pos_acc = accs.len();
        let mut mn = [f32::MAX;3]; let mut mx = [f32::MIN;3];
        for v in &hit.vertices { for i in 0..3 { mn[i]=mn[i].min(v[i]); mx[i]=mx[i].max(v[i]); } }
        accs.push(json!({"bufferView": bv_idx, "componentType": 5126, "count": hit.vertices.len(), "type": "VEC3", "min": mn, "max": mx}));

        let mut hit_mesh: HashMap<String, usize> = HashMap::new();
        for obj in &hit.objects {
            let mut edges: Vec<u32> = Vec::new();
            for poly in &hit.polygons[obj.first_polygon as usize..(obj.first_polygon+obj.polygon_count) as usize] {
                let a = poly.first_vertex;
                let n = poly.vertex_count;
                for j in 0..n {
                    edges.push(a+j);
                    edges.push(a + (j+1)%n);
                }
            }
            if edges.is_empty() { continue; }
            let mut idx_bytes: Vec<u8> = Vec::new();
            for e in &edges { idx_bytes.extend_from_slice(&e.to_le_bytes()); }
            pad4(&mut idx_bytes);
            let buffers = doc.get_mut("buffers").unwrap().as_array_mut().unwrap();
            let ibuf = buffers.len();
            let ib64 = base64::engine::general_purpose::STANDARD.encode(&idx_bytes);
            buffers.push(json!({"byteLength": idx_bytes.len(), "uri": format!("data:application/octet-stream;base64,{}", ib64)}));
            let bvs = doc.get_mut("bufferViews").unwrap().as_array_mut().unwrap();
            let ibv = bvs.len();
            bvs.push(json!({"buffer": ibuf, "byteOffset": 0, "byteLength": edges.len()*4, "target": 34963}));
            let accs = doc.get_mut("accessors").unwrap().as_array_mut().unwrap();
            let iacc = accs.len();
            accs.push(json!({"bufferView": ibv, "componentType": 5125, "count": edges.len(), "type": "SCALAR"}));
            let meshes = doc.get_mut("meshes").unwrap().as_array_mut().unwrap();
            let mi = meshes.len();
            meshes.push(json!({
                "name": obj.name,
                "primitives": [{"attributes": {"POSITION": pos_acc}, "indices": iacc, "mode": 1, "material": mat_idx}]
            }));
            hit_mesh.insert(obj.name.clone(), mi);
        }

        let offset = n;
        let base_nodes: Vec<Value> = doc.get("nodes").unwrap().as_array().unwrap().clone();
        for node in &stage.nodes {
            let mut out = base_nodes[node.index].clone();
            if let Some(obj) = out.as_object_mut() {
                obj.remove("mesh");
                let nm = obj.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
                obj.insert("name".into(), json!(format!("collision:{}", nm)));
                if let Some(ch) = obj.get_mut("children") {
                    if let Some(arr) = ch.as_array_mut() {
                        for v in arr.iter_mut() {
                            if let Some(i) = v.as_u64() { *v = json!(i as usize + offset); }
                        }
                    }
                }
            }
            doc.get_mut("nodes").unwrap().as_array_mut().unwrap().push(out);
        }
        let mut coll_children: Vec<Vec<usize>> = vec![Vec::new(); n];
        let mut next_idx = n * 2;
        for node in &stage.nodes {
            for r in &node.references {
                if hit_mesh.contains_key(&r.name) {
                    coll_children[node.index].push(next_idx);
                    next_idx += 1;
                }
            }
        }
        for i in 0..n {
            if !coll_children[i].is_empty() {
                let ci = offset + i;
                let nodes_arr = doc.get_mut("nodes").unwrap().as_array_mut().unwrap();
                if let Some(obj) = nodes_arr[ci].as_object_mut() {
                    let mut ch = obj.get("children").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                    for c in &coll_children[i] { ch.push(json!(c)); }
                    obj.insert("children".into(), Value::Array(ch));
                }
            }
        }
        let mut appended_names: Vec<String> = Vec::new();
        for node in &stage.nodes {
            for r in &node.references {
                if hit_mesh.contains_key(&r.name) {
                    appended_names.push(r.name.clone());
                }
            }
        }
        for name in &appended_names {
            let mi = hit_mesh[name];
            doc.get_mut("nodes").unwrap().as_array_mut().unwrap().push(json!({"name": name, "mesh": mi}));
        }

        let scenes = doc.get_mut("scenes").unwrap().as_array_mut().unwrap();
        scenes.push(json!({"name": "Collision", "nodes": [stage_root + offset]}));
        scenes.push(json!({"name": "Stage + collision", "nodes": [stage_root, stage_root + offset]}));
    }

    let report = json!({"format": "ARIKA_STAGE_PREVIEW", "mesh_instances": instances});
    doc.as_object_mut().unwrap().insert("extras".into(), report);

    Ok(doc)
}

pub fn write_stage_gltf(model: &Model, stage: &Stage, hit: Option<&Hit>, path: impl AsRef<std::path::Path>) -> Result<(), crate::error::ArikaError> {
    let doc = build_stage_gltf(model, stage, hit)?;
    let text = serde_json::to_string(&doc)?;
    std::fs::write(path, text)?;
    Ok(())
}
