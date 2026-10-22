//! Classic and MCC Halo cache files (`.map`).
//!
//! The conversion pipeline (tools/level/convert_ce_map.sh) turns another
//! Halo game's multiplayer map into a Campaign Evolved one through a staging
//! directory: collision, render geometry, materials, textures and placements
//! in one game-neutral layout (docs/ce_map_conversion.md, "What the command
//! does"). Which program writes the staging depends on the game:
//!
//! - Halo 1 (PC and Custom Edition builds): HalcyonRing's halo2ue exporter.
//! - Halo 2 (MCC): this crate's [`h2::stage`].
//!
//! [`detect`] tells the games apart from the header, so `mjolnir cache info`
//! can route a map before anything else reads it.

pub mod detect;
pub mod h2;

use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{0}: {1}")]
    Io(PathBuf, std::io::Error),
    #[error("{0}")]
    Format(String),
    #[error("{0}")]
    Unsupported(String),
}
