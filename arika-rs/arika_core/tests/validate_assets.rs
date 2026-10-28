//! Validation against real INFO.decoded.bin / files.json and synthetic format fixtures.

use arika_core::info::{decode_info, encode_info, HEADER, RECORD};
use arika_core::motion::parse_mot2;
use arika_core::stages::{parse_hit, parse_stg, stage_instances};
use arika_core::tim2::{decode_tim2, decode_xpix, encode_png};
use std::path::PathBuf;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

#[test]
fn info_roundtrip_real_decoded() {
    let decoded = std::fs::read(fixtures().join("INFO.decoded.bin")).expect("fixture");
    assert_eq!(decoded.len(), 98304);
    assert_eq!(&decoded[1..16], b"www.arika.co.jp");

    let encoded = encode_info(&decoded).expect("encode");
    assert_eq!(encoded.len(), decoded.len());
    assert_eq!(&encoded[..16], &decoded[..16]); // key unchanged

    let again = decode_info(&encoded).expect("decode");
    assert_eq!(again, decoded, "full INFO buffer roundtrip");
}

#[test]
fn info_entries_match_files_json() {
    let decoded = std::fs::read(fixtures().join("INFO.decoded.bin")).unwrap();
    let count = u32::from_le_bytes(decoded[0x2C..0x30].try_into().unwrap()) as usize;
    assert_eq!(count, 1934);

    let files: serde_json::Value =
        serde_json::from_slice(&std::fs::read(fixtures().join("files.json")).unwrap()).unwrap();
    let list = files.as_array().unwrap();
    assert_eq!(list.len(), 1934);

    let mut last_end = 0u64;
    for i in 0..count {
        let at = HEADER + i * RECORD;
        let raw = &decoded[at..at + 32];
        let nul = raw.iter().position(|&b| b == 0).unwrap_or(32);
        let (name, _, _) = encoding_rs::SHIFT_JIS.decode(&raw[..nul]);
        let name = name.into_owned();
        let unknown = u32::from_le_bytes(decoded[at + 32..at + 36].try_into().unwrap());
        let sector = u32::from_le_bytes(decoded[at + 36..at + 40].try_into().unwrap());
        let sectors = u32::from_le_bytes(decoded[at + 40..at + 44].try_into().unwrap());
        let size = u32::from_le_bytes(decoded[at + 44..at + 48].try_into().unwrap());

        let exp = &list[i];
        assert_eq!(exp["index"], i, "index {i}");
        assert_eq!(exp["name"], name, "name at {i}");
        assert_eq!(exp["sector"], sector);
        assert_eq!(exp["sectors"], sectors);
        assert_eq!(exp["size"], size);
        assert_eq!(exp["unknown"], unknown);

        let needed = (size as u64 + 2047) / 2048;
        assert!(
            sectors as u64 >= needed,
            "asset larger than allocation: {name}"
        );
        let offset = sector as u64 * 2048;
        // extents must not overlap when sorted — check sequential in sector order later
        let _ = offset;
        last_end = last_end.max(offset + sectors as u64 * 2048);
    }
    assert!(last_end > 0);

    // magic stats from files.json
    let mut fpix = 0;
    let mut fmdl = 0;
    for e in list {
        match e["magic_ascii"].as_str() {
            Some("FPIX") => fpix += 1,
            Some("FMDL") => fmdl += 1,
            _ => {}
        }
    }
    assert!(fpix >= 700, "expected many FPIX, got {fpix}");
    assert!(fmdl >= 400, "expected many FMDL, got {fmdl}");
    eprintln!("OK: 1934 entries, FPIX={fpix} FMDL={fmdl}, used_bytes≈{last_end}");
}

#[test]
fn tim2_and_xpix_sample() {
    let tim2 = std::fs::read(fixtures().join("sample.tim2")).unwrap();
    let img = decode_tim2(&tim2).expect("tim2");
    assert_eq!((img.width, img.height), (2, 2));
    assert_eq!(img.rgba.len(), 2 * 2 * 4);
    // alpha expanded from 128
    assert_eq!(img.rgba[3], 255);

    let png = encode_png(img.width, img.height, &img.rgba).expect("png");
    assert!(png.starts_with(&[0x89, b'P', b'N', b'G']));

    let xpix = std::fs::read(fixtures().join("sample.xpix")).unwrap();
    let img2 = decode_xpix(&xpix).expect("xpix");
    assert_eq!(img2.width, 2);
}

#[test]
fn hit_sample() {
    let data = std::fs::read(fixtures().join("sample.hit")).unwrap();
    let hit = parse_hit(&data).expect("hit");
    assert_eq!(hit.objects.len(), 1);
    assert_eq!(hit.polygons.len(), 1);
    assert_eq!(hit.vertices.len(), 3);
    assert_eq!(hit.polygons[0].vertex_count, 3);
}

#[test]
fn stg_sample() {
    let data = std::fs::read(fixtures().join("sample.stg")).unwrap();
    let stage = parse_stg(&data).expect("stg");
    assert!(stage.names.len() >= 2);
    assert!(stage.nodes.len() >= 2);
    let inst = stage_instances(&stage);
    assert!(!inst.is_empty(), "kind-2 instances");
    assert_eq!(inst[0].mesh_name, "MeshBody");
    assert_eq!(inst[0].translation, [1.0, 2.0, 3.0]);
}

#[test]
fn mot2_sample() {
    let data = std::fs::read(fixtures().join("sample.mot2")).unwrap();
    let m = parse_mot2(&data).expect("mot2");
    assert_eq!(m.fps, 60.0);
    assert_eq!(m.frame_count, 7);
    assert_eq!(m.nodes.len(), 1);
}


#[test]
fn shared_python_rust_parity_manifest() {
    // This manifest is also consumed by arika-py/test_arika_rust_parity.py.
    let root = fixtures();
    let expected: serde_json::Value = serde_json::from_slice(
        &std::fs::read(root.join("parity_fixtures.json")).expect("parity manifest"),
    ).expect("valid parity manifest");

    let stg = parse_stg(&std::fs::read(root.join("sample.stg")).unwrap()).unwrap();
    let stg_expected = &expected["stg"];
    assert_eq!(serde_json::to_value(&stg.names).unwrap(), stg_expected["names"]);
    assert_eq!(stg.template_count, stg_expected["template_count"].as_u64().unwrap() as u32);
    assert_eq!(serde_json::to_value(&stg.roots).unwrap(), stg_expected["roots"]);
    assert_eq!(stg.nodes.len(), stg_expected["node_count"].as_u64().unwrap() as usize);
    let stage_root = stg.roots[1];
    assert_eq!(stg.nodes[stage_root].name, stg_expected["stage_root"].as_str().unwrap());
    let instance = stage_instances(&stg).into_iter().find(|v| v.name == stg_expected["mesh_instance"]["name"].as_str().unwrap()).unwrap();
    let expected_translation: Vec<f64> = stg_expected["mesh_instance"]["translation"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
    for (actual, expected) in instance.translation.iter().zip(expected_translation) {
        assert!((*actual as f64 - expected).abs() < 1e-6);
    }

    let hit = parse_hit(&std::fs::read(root.join("sample.hit")).unwrap()).unwrap();
    let hit_expected = &expected["hit"];
    assert_eq!(hit.objects.len(), hit_expected["object_count"].as_u64().unwrap() as usize);
    assert_eq!(hit.polygons.len(), hit_expected["polygon_count"].as_u64().unwrap() as usize);
    assert_eq!(hit.vertices.len(), hit_expected["vertex_count"].as_u64().unwrap() as usize);
    assert_eq!(hit.objects[0].name, hit_expected["object_name"].as_str().unwrap());
    assert_eq!(hit.polygons[0].vertex_count, hit_expected["polygon_vertex_count"].as_u64().unwrap() as u32);

    let mot = parse_mot2(&std::fs::read(root.join("sample.mot2")).unwrap()).unwrap();
    let mot_expected = &expected["mot2"];
    assert_eq!(mot.fps as f64, mot_expected["fps"].as_f64().unwrap());
    assert_eq!(mot.frame_count as u64, mot_expected["frame_count"].as_u64().unwrap());
    assert_eq!(mot.nodes.len(), mot_expected["node_count"].as_u64().unwrap() as usize);
    assert_eq!(serde_json::to_value([1, 1, 0]).unwrap(), mot_expected["channel_counts"]);
    let expected_t = mot_expected["translation_values"].as_array().unwrap();
    for (actual, expected) in mot.nodes[0].translation.values.iter().zip(expected_t) {
        for (a, e) in actual.iter().zip(expected.as_array().unwrap()) {
            assert!((*a as f64 - e.as_f64().unwrap()).abs() < 1e-6);
        }
    }
    let expected_r = mot_expected["rotation_values"].as_array().unwrap();
    for (actual, expected) in mot.nodes[0].rotation.values.iter().zip(expected_r) {
        for (a, e) in actual.iter().zip(expected.as_array().unwrap()) {
            assert!((*a as f64 - e.as_f64().unwrap()).abs() < 1e-6);
        }
    }
    assert_eq!(mot.nodes[0].scale.animated, mot_expected["scale_animated"].as_bool().unwrap());

    let tim2_data = std::fs::read(root.join("sample.tim2")).unwrap();
    let image = decode_tim2(&tim2_data).unwrap();
    let tim_expected = &expected["tim2"];
    assert_eq!(image.width as u64, tim_expected["width"].as_u64().unwrap());
    assert_eq!(image.height as u64, tim_expected["height"].as_u64().unwrap());
    let rgba_hex: String = image.rgba.iter().map(|b| format!("{b:02x}")).collect();
    assert_eq!(rgba_hex, tim_expected["rgba_hex"].as_str().unwrap());

    let cht_data = std::fs::read(root.join("sample.cht")).unwrap();
    let cht = arika_core::cht::parse_cht(&cht_data).unwrap();
    let cht_expected = &expected["cht"];
    assert_eq!(cht.byte_size, cht_expected["byte_size"].as_u64().unwrap() as usize);
    assert_eq!(serde_json::to_value(&cht.name_table).unwrap(), cht_expected["name_table"]);
    assert_eq!(cht.actions.len(), cht_expected["action_count"].as_u64().unwrap() as usize);
    let action = &cht.actions[0];
    assert_eq!(action.motion_id, cht_expected["motion_id"].as_u64().unwrap() as u32);
    assert_eq!(action.variants.len(), cht_expected["variant_count"].as_u64().unwrap() as usize);
    assert_eq!(action.variants[0].motion_name, cht_expected["v0_motion_name"].as_str().unwrap());
    assert_eq!(action.variants[0].resource_bank, cht_expected["v0_resource_bank"].as_u64().unwrap() as u16);
    assert_eq!(serde_json::to_value(&action.variants[0].child_blocks).unwrap(), cht_expected["v0_child_blocks"]);
    assert_eq!(action.variants[1].motion_name, cht_expected["v1_motion_name"].as_str().unwrap());
    assert_eq!(action.variants[1].resource_bank, cht_expected["v1_resource_bank"].as_u64().unwrap() as u16);

    let rng_expected = &expected["rng"];
    let (s0, v0) = arika_core::rng::next_rng(0);
    assert_eq!(v0, rng_expected["seed_0_next"].as_u64().unwrap() as u32);
    assert_eq!(s0, rng_expected["seed_0_state_after"].as_u64().unwrap());
    let (s1, v1) = arika_core::rng::next_rng(1);
    assert_eq!(v1, rng_expected["seed_1_next"].as_u64().unwrap() as u32);
    assert_eq!(s1, rng_expected["seed_1_state_after"].as_u64().unwrap());
}
