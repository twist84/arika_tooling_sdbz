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
    assert_eq!(m.frame_count, 2);
    assert_eq!(m.nodes.len(), 1);
}
