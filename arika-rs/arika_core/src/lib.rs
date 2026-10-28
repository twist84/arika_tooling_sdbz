//! Arika DAT tools core — Super Dragon Ball Z INFO.DAT / GAME.DAT and related formats.

pub mod container;
pub mod dat;
pub mod error;
pub mod faces;
pub mod gltf;
pub mod info;
pub mod models;
pub mod motion;
pub mod stages;
pub mod tim2;
pub mod audio;
pub mod cht;
pub mod clock;
pub mod rng;
pub mod project;

pub use dat::{Archive, Entry};
pub use error::{ArikaError, Result};
pub use info::{decode_info, encode_info, HEADER, MAGIC, RECORD, SECTOR};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
