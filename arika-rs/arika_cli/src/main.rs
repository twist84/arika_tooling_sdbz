use std::path::PathBuf;

use anyhow::{Context, Result};
use arika_core::dat::Archive;
use arika_core::faces::{faces_to_json, parse_face_ani};
use arika_core::gltf::write_gltf;
use arika_core::models::{attach_textures, model_to_json, parse_fmdl, write_obj};
use arika_core::motion::{motion_to_json, parse_mot2, parse_rfsm, Motion};
use arika_core::stages::{hit_to_json, parse_hit, parse_stg, stage_instances, stage_to_json, write_hit_obj};
use arika_core::tim2::{decode_tim2, decode_xpix, write_ppm};
use clap::{Parser, Subcommand};

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
    /// Rebuild INFO (and optional GAME) from a directory of modified assets
    Rebuild {
        info: PathBuf,
        #[arg(long)]
        game: Option<PathBuf>,
        /// Directory of extracted (possibly edited) assets
        assets: PathBuf,
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
        } => {
            let arch = Archive::open(&info, game.as_ref())?;
            arch.rebuild_from_dir(&assets, &out_info, out_game.as_ref())?;
            println!("Wrote {}", out_info.display());
            if let Some(og) = out_game {
                println!("Wrote {}", og.display());
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

        Commands::FaceJson { path, out } => {
            let data = std::fs::read(&path)?;
            let catalog = parse_face_ani(&data)?;
            let json = faces_to_json(&catalog)?;
            std::fs::write(&out, json)?;
            println!(
                "Face catalog: {} programs → {}",
                catalog.programs.len(),
                out.display()
            );
        }
    }
    Ok(())
}
