use anyhow::{Context, Result};
use arika_core::audio::{
    ase_samples, ams_channels, decode_adpcm, encode_adpcm, pitch_for_rate, read_wav, sample_rate,
    write_wav, HEADER, INTERLEAVE,
};
use arika_core::dat::Archive;
use arika_core::info::InfoRegion;
use arika_core::faces::{faces_to_json, parse_face};
use arika_core::gltf::write_gltf;
use arika_core::models::{attach_textures, model_to_json, parse_fmdl, write_obj};
use arika_core::motion::{motion_to_json, parse_mot2, parse_rfsm, Motion};
use arika_core::stages::{
    hit_to_json, parse_hit, parse_stg, stage_instances, stage_to_json, write_hit_obj,
};
use arika_core::tim2::{decode_tim2, decode_xpix, write_ppm};
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "arika",
    about = "Super Dragon Ball Z INFO.DAT / GAME.DAT tools (Rust)",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// List assets in INFO.DAT
    List { info: PathBuf },
    /// Extract assets from GAME.DAT
    Extract {
        info: PathBuf,
        game: PathBuf,
        #[arg(short, long, default_value = "extracted")]
        out: PathBuf,
        #[arg(short, long)]
        pattern: Option<String>,
        #[arg(long)]
        overwrite: bool,
    },
    /// Show archive summary
    Info {
        info: PathBuf,
        #[arg(long)]
        game: Option<PathBuf>,
    },
    /// Rebuild INFO (and optional GAME) from a directory of modified assets.
    /// Without a seed INFO.DAT, pass --version (or --key) to build from scratch.
    Rebuild {
        /// Input INFO.DAT (omit with --version/--key to build without a seed)
        info: Option<PathBuf>,
        /// Directory of extracted (possibly edited) assets
        #[arg(long)]
        assets: PathBuf,
        /// Input GAME.DAT (required when rebuilding from a seed)
        #[arg(long)]
        game: Option<PathBuf>,
        /// Region name (eu-beta, eu, usa, jpn, db1) to build INFO.DAT without a seed
        #[arg(long)]
        version: Option<String>,
        /// Raw 16-byte codec key as hex (overrides --version)
        #[arg(long)]
        key: Option<String>,
        #[arg(long, default_value = "INFO.DAT.new")]
        out_info: PathBuf,
        #[arg(long)]
        out_game: Option<PathBuf>,
    },
    /// Parse FMDL and write JSON geometry summary
    ModelJson {
        mdl: PathBuf,
        out: PathBuf,
        #[arg(long)]
        pix: Option<PathBuf>,
    },
    /// Export FMDL bind-pose as Wavefront OBJ
    ModelObj { mdl: PathBuf, out: PathBuf },
    /// Export FMDL (+ optional motions) as self-contained glTF
    ModelGltf {
        mdl: PathBuf,
        out: PathBuf,
        #[arg(long)]
        pix: Option<PathBuf>,
        /// RFSM .pmt or MOT2 (repeatable)
        #[arg(long)]
        motion: Vec<PathBuf>,
        /// Mesh name or glob filter (repeatable)
        #[arg(long)]
        mesh: Vec<String>,
    },
    /// Parse RFSM (.pmt) or MOT2 and write JSON
    MotionJson { path: PathBuf, out: PathBuf },
    /// Parse STG and write JSON
    StgJson { stg: PathBuf, out: PathBuf },
    /// Parse HIT collision and write JSON
    HitJson { hit: PathBuf, out: PathBuf },
    /// Export HIT polygons as OBJ
    HitObj { hit: PathBuf, out: PathBuf },
    /// Decode TIM2 / XPIX texture to PPM
    TexturePpm { path: PathBuf, out: PathBuf },
    /// Parse facial ANI and write JSON
    FaceJson { path: PathBuf, out: PathBuf },
    /// Export stage: STG instances + sibling MDL as glTF
    StageGltf {
        stg: PathBuf,
        out: PathBuf,
        #[arg(long)]
        model: Option<PathBuf>,
        #[arg(long)]
        pix: Option<PathBuf>,
    },
    /// Export .ase/.ams audio to WAV
    AudioExport {
        source: PathBuf,
        output: PathBuf,
    },
    /// Rebuild .ase/.ams audio from edited WAVs
    AudioImport {
        originals: PathBuf,
        wavs: PathBuf,
        output: PathBuf,
        #[arg(long)]
        allow_duration_change: bool,
    },
    /// Parse CHT logical motion / collision mappings and write JSON
    ChtJson { cht: PathBuf, out: PathBuf },
    /// Run native clock trace and write JSON
    ClockTrace {
        #[arg(long, default_value_t = 60.0)]
        fps: f32,
        #[arg(long, default_value_t = 10)]
        frames: u16,
        #[arg(long, default_value_t = 10)]
        ticks: u32,
        out: PathBuf,
    },
    /// Inspect .arika-scene.json scene project
    ProjectInfo { project: PathBuf },
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    match cli.command {
        Commands::List { info } => {
            let arch = Archive::open(&info, None::<PathBuf>)?;
            println!("Entries: {}", arch.entries.len());
            println!("{:<6} {:>10} {:>10}  {}", "Index", "Size", "Sector", "Name");
            for e in &arch.entries {
                println!(
                    "{:<6} {:>10} {:>10}  {}",
                    e.index, e.size, e.sector, e.name
                );
            }
        }
        Commands::Extract {
            info,
            game,
            out,
            pattern,
            overwrite,
        } => {
            let arch = Archive::open(&info, Some(&game))?;
            let n = arch.extract_all(&out, pattern.as_deref(), overwrite)?;
            println!("Extracted {n} asset(s) into {}", out.display());
        }
        Commands::Info { info, game } => {
            let arch = Archive::open(&info, game.as_ref())?;
            println!("INFO: {}", arch.info_path.display());
            if let Some(g) = &arch.game_path {
                println!("GAME: {}", g.display());
            }
            println!("Entries: {}", arch.entries.len());
            println!("Used bytes: {}", arch.used_bytes);
            println!("Decoded size: {}", arch.decoded.len());
        }
        Commands::Rebuild {
            info,
            game,
            assets,
            out_info,
            out_game,
            version,
            key,
        } => {
            if let Some(info_path) = info {
                // Existing seed-based rebuild path.
                let arch = Archive::open(&info_path, game.as_ref())?;
                arch.rebuild_from_dir(&assets, &out_info, out_game.as_ref())?;
                println!("Wrote {}", out_info.display());
                if let Some(og) = out_game {
                    println!("Wrote {}", og.display());
                }
            } else {
                // Build INFO.DAT from scratch without a seed.
                let key_bytes = match key {
                    Some(hex) => {
                        let bytes = hex::decode(hex.trim())
                            .map_err(|e| anyhow::anyhow!("invalid --key hex: {e}"))?;
                        if bytes.len() != 16 {
                            anyhow::bail!("--key must be exactly 16 bytes (32 hex chars)");
                        }
                        let mut arr = [0u8; 16];
                        arr.copy_from_slice(&bytes);
                        Some(arr)
                    }
                    None => None,
                };
                let region = match key_bytes {
                    Some(_) => InfoRegion::EuBeta,
                    None => {
                        let region_str = version.ok_or_else(|| {
                            anyhow::anyhow!("--version is required when no seed INFO.DAT is provided")
                        })?;
                        InfoRegion::from_str(&region_str).ok_or_else(|| {
                            anyhow::anyhow!(
                                "unknown region '{}' (expected: eu-beta, eu, usa, jpn, db1)",
                                region_str
                            )
                        })?
                    }
                };
                Archive::create_from_dir(region, key_bytes, &assets, &out_info, out_game.as_ref())?;
                println!("Wrote {}", out_info.display());
                if let Some(og) = out_game {
                    println!("Wrote {}", og.display());
                }
            }
        }
        Commands::ModelJson { mdl, out, pix } => {
            let data = std::fs::read(&mdl).context("read MDL")?;
            let name = mdl.file_stem().and_then(|s| s.to_str()).unwrap_or("model");
            let mut model = parse_fmdl(&data, name)?;
            if let Some(p) = pix {
                let pix_data = std::fs::read(p)?;
                let _ = attach_textures(&mut model, &pix_data);
            } else {
                let sibling = mdl.with_extension("pix");
                if sibling.exists() {
                    let pix_data = std::fs::read(sibling)?;
                    let _ = attach_textures(&mut model, &pix_data);
                }
            }
            let json = model_to_json(&model)?;
            std::fs::write(&out, json)?;
            println!(
                "Wrote {} nodes, {} meshes, {} materials, {} textures → {}",
                model.nodes.len(),
                model.meshes.len(),
                model.materials.len(),
                model.textures.len(),
                out.display()
            );
        }
        Commands::ModelObj { mdl, out } => {
            let data = std::fs::read(&mdl)?;
            let name = mdl.file_stem().and_then(|s| s.to_str()).unwrap_or("model");
            let model = parse_fmdl(&data, name)?;
            write_obj(&model, &out)?;
            println!(
                "Wrote OBJ with {} meshes → {}",
                model.meshes.len(),
                out.display()
            );
        }
        Commands::ModelGltf {
            mdl,
            out,
            pix,
            motion,
            mesh,
        } => {
            let data = std::fs::read(&mdl)?;
            let name = mdl.file_stem().and_then(|s| s.to_str()).unwrap_or("model");
            let mut model = parse_fmdl(&data, name)?;
            if let Some(p) = pix {
                let pix_data = std::fs::read(p)?;
                let _ = attach_textures(&mut model, &pix_data);
            } else {
                let sibling = mdl.with_extension("pix");
                if sibling.exists() {
                    let pix_data = std::fs::read(sibling)?;
                    let _ = attach_textures(&mut model, &pix_data);
                }
            }
            let mut motions: Vec<Motion> = Vec::new();
            for mp in &motion {
                let md = std::fs::read(mp)?;
                if md.len() >= 4 && &md[0..4] == b"RFSM" {
                    let pkg = parse_rfsm(&md)?;
                    motions.extend(pkg.motions);
                } else if md.len() >= 4 && &md[0..4] == b"MOT2" {
                    motions.push(parse_mot2(&md)?);
                }
            }
            let filter = if mesh.is_empty() {
                None
            } else {
                Some(mesh.as_slice())
            };
            write_gltf(&model, &motions, &out, filter)?;
            println!(
                "Wrote glTF ({} meshes, {} motions) → {}",
                model.meshes.len(),
                motions.len(),
                out.display()
            );
        }
        Commands::MotionJson { path, out } => {
            let data = std::fs::read(&path)?;
            let json = if data.len() >= 4 && &data[0..4] == b"RFSM" {
                let pkg = parse_rfsm(&data)?;
                println!(
                    "RFSM: {} bones, {} motions",
                    pkg.bones.len(),
                    pkg.motions.len()
                );
                motion_to_json(&pkg)?
            } else if data.len() >= 4 && &data[0..4] == b"MOT2" {
                let m = parse_mot2(&data)?;
                println!(
                    "MOT2: {} frames @ {} fps, {} nodes",
                    m.frame_count, m.fps, m.nodes.len()
                );
                serde_json::to_string_pretty(&m)?
            } else {
                anyhow::bail!("not RFSM or MOT2");
            };
            std::fs::write(&out, json)?;
            println!("Wrote {}", out.display());
        }
        Commands::StgJson { stg, out } => {
            let data = std::fs::read(&stg)?;
            let stage = parse_stg(&data)?;
            let json = stage_to_json(&stage)?;
            std::fs::write(&out, json)?;
            println!(
                "STG: {} names, {} nodes, {} templates → {}",
                stage.names.len(),
                stage.nodes.len(),
                stage.template_count,
                out.display()
            );
        }
        Commands::HitJson { hit, out } => {
            let data = std::fs::read(&hit)?;
            let h = parse_hit(&data)?;
            let json = hit_to_json(&h)?;
            std::fs::write(&out, json)?;
            println!(
                "HIT: {} objects, {} polygons, {} vertices → {}",
                h.objects.len(),
                h.polygons.len(),
                h.vertices.len(),
                out.display()
            );
        }
        Commands::HitObj { hit, out } => {
            let data = std::fs::read(&hit)?;
            let h = parse_hit(&data)?;
            write_hit_obj(&h, &out)?;
            println!("Wrote HIT OBJ → {}", out.display());
        }
        Commands::TexturePpm { path, out } => {
            let data = std::fs::read(&path)?;
            let img = if data.len() >= 4 && &data[0..4] == b"XPIX" {
                decode_xpix(&data)?
            } else {
                decode_tim2(&data)?
            };
            write_ppm(&img, &out)?;
            println!(
                "{}x{} {:?} → {}",
                img.width,
                img.height,
                img.format,
                out.display()
            );
        }

        Commands::StageGltf { stg, out, model, pix } => {
            let stg_data = std::fs::read(&stg)?;
            let stage = parse_stg(&stg_data)?;
            let instances = stage_instances(&stage);
            let mdl_path = model.unwrap_or_else(|| stg.with_extension("mdl"));
            let data = std::fs::read(&mdl_path).with_context(|| format!("MDL {}", mdl_path.display()))?;
            let name = mdl_path.file_stem().and_then(|s| s.to_str()).unwrap_or("stage");
            let mut m = parse_fmdl(&data, name)?;
            let pix_path = pix.unwrap_or_else(|| mdl_path.with_extension("pix"));
            if pix_path.exists() {
                if let Ok(pd) = std::fs::read(&pix_path) {
                    let _ = attach_textures(&mut m, &pd);
                }
            }
            // Export full model glTF; instance placement is recorded in extras
            write_gltf(&m, &[], &out, None)?;
            let extras = serde_json::json!({
                "stage": stage.name,
                "instances": instances,
            });
            // annotate by rewriting JSON
            let mut doc: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&out)?)?;
            doc.as_object_mut().unwrap().insert("extras".into(), extras);
            std::fs::write(&out, serde_json::to_string(&doc)?)?;
            println!(
                "Stage glTF: {} mesh defs, {} instances → {}",
                m.meshes.len(),
                instances.len(),
                out.display()
            );
        }

        Commands::AudioExport { source, output } => {
            let sources: Vec<PathBuf> = if source.is_dir() {
                walkdir::WalkDir::new(&source)
                    .into_iter()
                    .filter_map(|e| e.ok())
                    .filter(|e| {
                        e.path().is_file()
                            && matches!(
                                e.path().extension().and_then(|s| s.to_str()),
                                Some("ase") | Some("ams")
                            )
                    })
                    .map(|e| e.into_path())
                    .collect()
            } else {
                vec![source.clone()]
            };
            let mut records = Vec::new();
            let mut errors = Vec::new();
            for src in &sources {
                let rel = if source.is_dir() {
                    src.strip_prefix(&source).unwrap_or(src).to_path_buf()
                } else {
                    PathBuf::from(src.file_name().unwrap_or_default())
                };
                let data = match std::fs::read(src) {
                    Ok(d) => d,
                    Err(e) => {
                        errors.push(format!("{}: {}", src.display(), e));
                        continue;
                    }
                };
                let _out_path = output.join(&rel);
                match src.extension().and_then(|s| s.to_str()) {
                    Some("ase") => {
                        match ase_samples(&data) {
                            Ok(samples) => {
                                for (index, rate, payload) in samples {
                                    match decode_adpcm(&payload) {
                                        Ok((pcm, _)) => {
                                            let wav = write_wav(&[pcm.clone()], rate).unwrap();
                                            let p = output.join(format!("{:03}.wav", index));
                                            if let Some(parent) = p.parent() {
                                                let _ = std::fs::create_dir_all(parent);
                                            }
                                            let _ = std::fs::write(&p, &wav);
                                            records.push(format!(
                                                "{:03}.wav rate={} frames={}",
                                                index,
                                                rate,
                                                pcm.len()
                                            ));
                                        }
                                        Err(e) => errors.push(format!("{}: ADPCM decode: {e}", src.display())),
                                    }
                                }
                            }
                            Err(e) => errors.push(format!("{}: {e}", src.display())),
                        }
                    }
                    Some("ams") => {
                        match ams_channels(&data) {
                            Ok((rate, left, right)) => {
                                let lpcm = decode_adpcm(&left).map(|(p, _)| p).unwrap_or_default();
                                let rpcm = decode_adpcm(&right).map(|(p, _)| p).unwrap_or_default();
                                let wav = write_wav(&[lpcm.clone(), rpcm], rate).unwrap();
                                let _ = std::fs::create_dir_all(output.parent().unwrap_or(std::path::Path::new("")));
                                let _ = std::fs::write(&output, &wav);
                                records.push(format!(
                                    "stereo rate={} frames={}",
                                    rate,
                                    lpcm.len()
                                ));
                            }
                            Err(e) => errors.push(format!("{}: {e}", src.display())),
                        }
                    }
                    _ => {}
                }
            }
            if let Some(parent) = output.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let manifest = serde_json::json!({
                "files": records,
                "errors": errors,
            });
            if let Some(parent) = output.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let _ = std::fs::write(output.join("audio_manifest.json"), serde_json::to_string_pretty(&manifest).unwrap());
            println!(
                "Exported {} WAV file(s); {} error(s)",
                records.len(),
                errors.len()
            );
        }

        Commands::AudioImport {
            originals,
            wavs,
            output,
            allow_duration_change,
        } => {
            let originals = originals.canonicalize().unwrap_or(originals.clone());
            let wavs = wavs.canonicalize().unwrap_or(wavs.clone());
            let output = output.canonicalize().unwrap_or(output.clone());

            let mut wav_files: Vec<PathBuf> = Vec::new();
            if wavs.is_dir() {
                for entry in walkdir::WalkDir::new(&wavs)
                    .into_iter()
                    .filter_map(|e| e.ok())
                    .filter(|e| e.path().is_file() && e.path().extension().and_then(|s| s.to_str()) == Some("wav"))
                {
                    wav_files.push(entry.into_path());
                }
            }

            let mut plan: Vec<String> = Vec::new();
            let mut errors: Vec<String> = Vec::new();

            for wav_path in &wav_files {
                let rel = wav_path.strip_prefix(&wavs).unwrap_or(wav_path);
                let asset_rel = if rel.file_name().and_then(|s| s.to_str()) == Some("audio.wav") {
                    // ams case: file is X.ams.wav
                    rel.with_extension("")
                } else if rel.parent().and_then(|p| p.extension().and_then(|s| s.to_str())) == Some("ase") {
                    // ase case: directory is X.ase/
                    rel.parent().unwrap_or(std::path::Path::new("")).to_path_buf()
                } else {
                    errors.push(format!("expected asset.ams.wav or asset.ase/000.wav: {}", rel.display()));
                    continue;
                };
                let asset_str = asset_rel.to_string_lossy().to_string();
                if !plan.contains(&asset_str) {
                    plan.push(asset_str);
                }
            }

            if !errors.is_empty() || plan.is_empty() {
                for e in &errors {
                    eprintln!("ERROR: {e}");
                }
                if plan.is_empty() {
                    eprintln!("ERROR: no matching audio WAVs found");
                }
                std::process::exit(1);
            }

            let mut records: Vec<serde_json::Value> = Vec::new();
            for asset in &plan {
                let source_path = originals.join(asset);
                let dest_path = output.join(asset);
                let original = match std::fs::read(&source_path) {
                    Ok(d) => d,
                    Err(e) => {
                        errors.push(format!("{}: {}", asset, e));
                        continue;
                    }
                };
                let wav_source = wavs.join(asset);
                let asset_path_buf = PathBuf::from(asset);
                let ext = asset_path_buf.extension().and_then(|s| s.to_str()).unwrap_or("");
                let rebuilt = if ext == "ase" {
                    let wav_dir = if wav_source.is_dir() { wav_source.clone() } else { wav_source.parent().unwrap_or(std::path::Path::new("")).to_path_buf() };
                    // For ASE: look for %03d.wav files
                    let mut samples = match ase_samples(&original) {
                        Ok(s) => s,
                        Err(e) => { errors.push(format!("{asset}: {e}")); continue; }
                    };
                    let mut header = original[..HEADER].to_vec();
                    let mut payload = Vec::new();
                    let mut edits = Vec::new();
                    for (index, _, compressed) in &mut samples {
                        let (orig_pitch, _orig_offset) = {
                            let at = 12 + (*index as usize) * 8;
                            (u32::from_le_bytes(original[at..at+4].try_into().unwrap()), u32::from_le_bytes(original[at+4..at+8].try_into().unwrap()))
                        };
                        let wav_file = wav_dir.join(format!("{:03}.wav", index));
                        let mut pitch = orig_pitch;
                        if wav_file.is_file() {
                            let wav_data = match std::fs::read(&wav_file) {
                                Ok(d) => d,
                                Err(e) => { errors.push(format!("{}: {}", wav_file.display(), e)); continue; }
                            };
                            match read_wav(&wav_data) {
                                Ok((rate, channels)) => {
                                    let pcm = channels[0].clone();
                                    let validate = rate == sample_rate(orig_pitch)
                                        && pcm.len() == compressed.len() / 16 * 28;
                                    if !validate && !allow_duration_change {
                                        errors.push(format!("{asset}: WAV rate/frame count differs from original; use --allow-duration-change"));
                                        continue;
                                    }
                                    let decoded = decode_adpcm(compressed).map(|(p, _)| p).unwrap_or_default();
                                    let changed = pcm != decoded;
                                    if changed {
                                        match encode_adpcm(&pcm, 4, 3, 2) {
                                            Ok(enc) => {
                                                *compressed = enc;
                                            }
                                            Err(e) => { errors.push(format!("{asset}: ADPCM encode: {e}")); continue; }
                                        }
                                    }
                                    match pitch_for_rate(rate, orig_pitch) {
                                        Ok(p) => pitch = p,
                                        Err(e) => { errors.push(format!("{asset}: {e}")); continue; }
                                    }
                                    edits.push(serde_json::json!({
                                        "sample_index": index,
                                        "reencoded": changed,
                                        "pitch": pitch,
                                        "source_frames": pcm.len(),
                                        "encoded_frames": compressed.len() / 16 * 28,
                                    }));
                                }
                                Err(e) => { errors.push(format!("{}: {}", wav_file.display(), e)); continue; }
                            }
                        }
                        let at = 12 + (*index as usize) * 8;
                        header[at..at + 4].copy_from_slice(&pitch.to_le_bytes());
                        header[at + 4..at + 8].copy_from_slice(&(payload.len() as u32).to_le_bytes());
                        payload.append(compressed);
                    }
                    header[8..12].copy_from_slice(&(payload.len() as u32).to_le_bytes());
                    let result = [header.as_slice(), payload.as_slice()].concat();
                    // Validate
                    let _ = ase_samples(&result);
                    records.push(serde_json::json!({
                        "asset": asset,
                        "byte_identical": original == result,
                        "original_bytes": original.len(),
                        "rebuilt_bytes": result.len(),
                        "edits": edits,
                    }));
                    result
                } else {
                    // AMS
                    let wav_file = wav_source.with_extension("ams.wav");
                    let (_orig_rate, orig_left, orig_right) = match ams_channels(&original) {
                        Ok(r) => r,
                        Err(e) => { errors.push(format!("{asset}: {e}")); continue; }
                    };
                    let orig_pitch = u32::from_le_bytes(original[4..8].try_into().unwrap());
                    let wav_data = match std::fs::read(&wav_file) {
                        Ok(d) => d,
                        Err(e) => { errors.push(format!("{}: {}", wav_file.display(), e)); continue; }
                    };
                    let (rate, channels) = match read_wav(&wav_data) {
                        Ok(r) => r,
                        Err(e) => { errors.push(format!("{}: {}", wav_file.display(), e)); continue; }
                    };
                    if rate != sample_rate(orig_pitch) || channels[0].len() != orig_left.len() {
                        if !allow_duration_change {
                            errors.push(format!("{asset}: WAV rate/frame count differs from original; use --allow-duration-change"));
                            continue;
                        }
                    }
                    let mut changed = vec![false; 2];
                    let mut encoded = vec![orig_left.clone(), orig_right.clone()];
                    for ch in 0..2 {
                        let decoded = decode_adpcm(&encoded[ch]).map(|(p, _)| p).unwrap_or_default();
                        changed[ch] = channels[ch] != decoded;
                        if changed[ch] {
                            match encode_adpcm(&channels[ch], 0, 0, 1) {
                                Ok(enc) => encoded[ch] = enc,
                                Err(e) => { errors.push(format!("{asset}: ADPCM encode: {e}")); continue; }
                            }
                        }
                    }
                    let pitch = match pitch_for_rate(rate, orig_pitch) {
                        Ok(p) => p,
                        Err(e) => { errors.push(format!("{asset}: {e}")); continue; }
                    };
                    if !changed.iter().any(|&c| c) && pitch == orig_pitch {
                        records.push(serde_json::json!({
                            "asset": asset,
                            "byte_identical": true,
                            "original_bytes": original.len(),
                            "rebuilt_bytes": original.len(),
                            "edits": serde_json::json!([{"reencoded_channels": changed, "pitch": pitch, "source_frames": orig_left.len()}]),
                        }));
                        continue;
                    }
                    let pairs = (encoded[0].len() + 0xFFFF) / 0x10000;
                    let mut body = vec![0u8; pairs * 0x20000];
                    let order: Vec<usize> = (0..pairs * 2).step_by(2).chain((1..pairs * 2).rev().step_by(2)).collect();
                    for (logical, physical) in order.into_iter().enumerate() {
                        for (ch_idx, ch_data) in encoded.iter().enumerate() {
                            let start = logical * INTERLEAVE;
                            let chunk = &ch_data[start..start.min(ch_data.len())];
                            let at = physical * 0x10000 + ch_idx * INTERLEAVE;
                            body[at..at + chunk.len()].copy_from_slice(chunk);
                        }
                    }
                    let mut header = original[..HEADER].to_vec();
                    header[0..4].copy_from_slice(&120u32.to_le_bytes());
                    header[4..8].copy_from_slice(&pitch.to_le_bytes());
                    header[8..12].copy_from_slice(&(encoded[0].len() as u32).to_le_bytes());
                    header[12..16].copy_from_slice(&(pairs as u32).to_le_bytes());
                    let result = [header.as_slice(), body.as_slice()].concat();
                    let _ = ams_channels(&result);
                    records.push(serde_json::json!({
                        "asset": asset,
                        "byte_identical": original == result,
                        "original_bytes": original.len(),
                        "rebuilt_bytes": result.len(),
                        "edits": serde_json::json!([{"reencoded_channels": changed, "pitch": pitch, "source_frames": encoded[0].len()}]),
                    }));
                    result
                };
                if let Some(parent) = dest_path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                let _ = std::fs::write(&dest_path, &rebuilt);
                println!("Rebuilt {asset}");
            }

            let report = serde_json::json!({
                "assets": records,
                "errors": errors,
                "allow_duration_change": allow_duration_change,
            });
            let _ = std::fs::write(output.join("audio_import_manifest.json"), serde_json::to_string_pretty(&report).unwrap());
            println!("Rebuilt {} asset(s); {} error(s)", records.len(), errors.len());
            if !errors.is_empty() {
                std::process::exit(1);
            }
        }

        Commands::FaceJson { path, out } => {
            let data = std::fs::read(&path)?;
            let catalog = parse_face(&data)?;
            let json = faces_to_json(&catalog)?;
            std::fs::write(&out, json)?;
            println!(
                "Face catalog: {} programs → {}",
                catalog.programs.len(),
                out.display()
            );
        }

        Commands::ChtJson { cht, out } => {
            let data = std::fs::read(&cht)?;
            let doc = arika_core::cht::parse_cht(&data)?;
            let json = serde_json::to_string_pretty(&doc)?;
            std::fs::write(&out, json)?;
            println!("Wrote CHT with {} actions → {}", doc.actions.len(), out.display());
        }

        Commands::ClockTrace { fps, frames, ticks, out } => {
            let mut clock = arika_core::clock::NativeClock::new(fps, frames, 0.0, -1.0, 1.0, 0.0, false, false, -1.0, 0, None)?;
            let mut samples = vec![serde_json::to_value(&clock.snapshot(0.0, None, false))?];
            for _ in 0..ticks {
                let snap = clock.step(1.0 / fps);
                samples.push(serde_json::to_value(&snap)?);
            }
            std::fs::write(&out, serde_json::to_string_pretty(&samples)?)?;
            println!("Wrote {} clock samples → {}", samples.len(), out.display());
        }

        Commands::ProjectInfo { project } => {
            let proj = arika_core::project::SceneProject::load(&project)?;
            let orig = proj.decode_original_stage()?;
            let edited = proj.decode_edited_stage()?;
            println!("Project format: {}", proj.format);
            println!("Source stage: {}", proj.source_stage);
            println!("Original stage: {} bytes", orig.len());
            println!("Edited stage: {} bytes", edited.len());
        }
    }
    Ok(())
}
