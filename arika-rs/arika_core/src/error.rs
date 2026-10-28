use thiserror::Error;

#[derive(Error, Debug)]
pub enum ArikaError {
    #[error("not this game's Arika INFO.DAT")]
    InvalidInfoMagic,

    #[error("decoded INFO data has an invalid header")]
    InvalidDecodedHeader,

    #[error("invalid INFO entry count")]
    InvalidEntryCount,

    #[error("duplicate/case-colliding asset name: {0}")]
    DuplicateName(String),

    #[error("asset is larger than its allocated sectors: {0}")]
    AssetTooLarge(String),

    #[error("overlapping asset extents")]
    OverlappingExtents,

    #[error("GAME.DAT is too small for this INFO.DAT")]
    GameTooSmall,

    #[error("unsafe asset path: {0}")]
    UnsafePath(String),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("{0}")]
    Other(String),
}

pub type Result<T> = std::result::Result<T, ArikaError>;
