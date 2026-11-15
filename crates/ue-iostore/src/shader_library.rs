//! The shader library a container carries, and the chunk number that names it.
//!
//! UE opens a mounted pak's shader library by the number in the pak's file
//! name: `pakchunk<N>…` opens the library `<Project>_Chunk<N>`
//! (ShaderCodeLibrary.cpp, `OnPakFileMounted`). In IoStore the library is one
//! `ShaderCodeLibrary` chunk whose ID is CityHash64 of the lower-cased UTF-16
//! `<Project>_Chunk<N>-<format>` (ShaderCodeArchive.cpp,
//! `GetShaderCodeArchiveChunkId`). The shader code itself sits in
//! `ShaderCode` chunks keyed by content hash, which no number touches.
//!
//! So the number is a name, and a container can take any other: rewrite the
//! library chunk's ID for the new number and mount the container under a file
//! name carrying it. That is what lets an installer hand out numbers locally
//! instead of every author agreeing on them up front.

use crate::toc::{ChunkId, Toc};

/// Chunk type of a shader library (`EIoChunkType::ShaderCodeLibrary`).
pub const LIBRARY: u8 = 8;

/// The shader formats a library is cooked for, as UE writes them into the
/// name: shader format, a dash, shader platform.
pub const FORMATS: &[&str] = &["PCD3D_SM6-PCD3D_SM6", "PCD3D_SM5-PCD3D_SM5"];

/// The ID of `project`'s library for chunk `number` in `format`.
pub fn library_id(project: &str, number: u32, format: &str) -> ChunkId {
    ChunkId {
        id: crate::city::package_id(&format!("{project}_Chunk{number}-{format}")),
        index: 0,
        pad: 0,
        kind: LIBRARY,
    }
}

/// Whether the container carries a shader library at all.
pub fn has_library(toc: &Toc) -> bool {
    toc.chunk_ids.iter().any(|c| c.kind == LIBRARY)
}

/// Rename every shader library in `toc` from chunk `from` to chunk `to`.
///
/// Returns how many libraries were renamed (one per shader format). Fails,
/// leaving `toc` untouched, when a library chunk is not `project`'s library
/// for `from` in a known format: renaming only some would mount the container
/// with part of its shaders.
pub fn renumber(toc: &mut Toc, project: &str, from: u32, to: u32) -> Result<usize, String> {
    let mut changes = Vec::new();
    for id in toc.chunk_ids.iter().filter(|c| c.kind == LIBRARY) {
        let format = FORMATS
            .iter()
            .find(|f| library_id(project, from, f) == *id)
            .ok_or_else(|| {
                format!(
                    "shader library {:016x} is not {project}_Chunk{from} in a known format",
                    id.id
                )
            })?;
        changes.push((*id, library_id(project, to, format)));
    }
    if from != to && !changes.is_empty() {
        crate::pack::rekey(toc, &changes)?;
    }
    Ok(changes.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_id_matches_a_cooked_library() {
        // pakchunk978 (Blood Gulch's remaster), read from its .utoc.
        assert_eq!(
            library_id("Meteorite", 978, "PCD3D_SM6-PCD3D_SM6").id,
            0xba65a6ffa6712a50
        );
    }
}
