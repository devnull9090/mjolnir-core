//! Classic Halo CE structure BSP → Meteorite `scenario_structure_bsp`.
//!
//! The new engine's structure BSP carries collision only (render geometry is
//! Unreal's problem), and its world-shell collision BSP has the same eight
//! winged-edge tables classic CE's has, in narrower encodings. This crate
//! reads the classic tables as the halo2ue exporter stages them ([`ce`]),
//! packs them into the 16-bit Meteorite layout ([`pack16`]), and writes them
//! into a shipped donor `sbsp` payload through `blam_tag::blockedit`
//! ([`transplant`]), so the result is a shipped tag with a foreign shell rather
//! than a tag assembled from nothing.

pub mod ce;
pub mod pack16;
pub mod transplant;
pub mod validate;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("staging: {0}")]
    Staging(String),
    #[error("tag: {0}")]
    Tag(#[from] blam_tag::patch::Error),
    #[error("{0}")]
    Other(String),
}
