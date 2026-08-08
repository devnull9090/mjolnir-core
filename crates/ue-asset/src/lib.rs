//! Cooked Unreal (zen) asset reading: usmap reflection schemas, package
//! structure, unversioned properties, and the mesh render data they guard.
//!
//! The tag data pipeline covers Blam; this crate covers the Unreal side the
//! game actually renders with. See `docs/tag_data_pipeline.md` for how the
//! two halves relate.

pub mod material;
pub mod mesh;
pub mod unversioned;
pub mod usmap;
pub mod zen;

pub use usmap::Usmap;
