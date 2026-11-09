//! Arika DAT tools core — Super Dragon Ball Z INFO.DAT / GAME.DAT and related formats.

pub mod ani;
pub mod container;
pub mod dat;
pub mod ebz;
pub mod error;
pub mod faces;
pub mod gltf;
pub mod info;
pub mod models;
pub mod motion;
pub mod pas;
pub mod stages;
pub mod spt;
pub mod tim2;
pub mod audio;
pub mod cht;
pub mod clock;
pub mod rng;
pub mod project;

pub use dat::{Archive, Entry};
pub use error::{ArikaError, Result};
pub use info::{
    decode_info, encode_info, encode_info_with_key, HEADER, INFO_MAGIC_TAIL, MAGIC, RECORD, SECTOR,
    InfoRegion, make_decoded_info, write_info_record,
};
pub use ani::parse_ani;
pub use ebz::parse_ebz;
pub use pas::parse_pas;
pub use spt::parse_spt;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
