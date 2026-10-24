//! BLF files: the chunked container MCC keeps Halo Reach game variants in
//! (`haloreach/game_variants/*.bin`, `hopper_game_variants/*.bin`).
//!
//! A chunk is a 12-byte big-endian header (4-byte signature, u32 size
//! including the header, u16 major and u16 minor version) and its body:
//! `_blf` (start), `chdr` (content header), `mpvr` (the variant), `_eof`.
//! The `mpvr` body holds a 20-byte hash, 4 more bytes, a big-endian u32
//! payload length and the payload: a bitstream whose first 4 bits are the
//! game engine type ([`ENGINE_MEGALO`] for a Megalo variant, which then
//! follows from bit 4 exactly as a `.mglo` file holds it from bit 0).
//! One MCC file (`hopper_game_variants/tu1_team_gun_game_054.bin`) has
//! `_blf`, `athr` (author: "untracked version"), `gvar` and `_eof` instead,
//! its `gvar` body being the payload alone. Layouts read from the files
//! themselves (every MCC Reach variant parses one of these ways); names
//! after ReachVariantTool.

use crate::Error;

/// Engine type 1: Forge (sandbox).
pub const ENGINE_FORGE: u8 = 1;
/// Engine type 2: Megalo, the multiplayer rules engine.
pub const ENGINE_MEGALO: u8 = 2;
/// Engine type 3: campaign.
pub const ENGINE_CAMPAIGN: u8 = 3;
/// Engine type 4: Firefight (survival).
pub const ENGINE_FIREFIGHT: u8 = 4;

/// The name of an engine type.
pub fn engine_name(engine: u8) -> &'static str {
    match engine {
        0 => "none",
        ENGINE_FORGE => "forge",
        ENGINE_MEGALO => "megalo",
        ENGINE_CAMPAIGN => "campaign",
        ENGINE_FIREFIGHT => "firefight",
        _ => "unknown",
    }
}

/// One chunk.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Chunk<'a> {
    pub signature: [u8; 4],
    pub major: u16,
    pub minor: u16,
    /// The bytes after the 12-byte header.
    pub body: &'a [u8],
}

/// The file starts with a `_blf` chunk.
pub fn is_blf(bytes: &[u8]) -> bool {
    bytes.starts_with(b"_blf")
}

/// The chunks up to and including `_eof` (bytes after it are padding).
pub fn chunks(bytes: &[u8]) -> Result<Vec<Chunk<'_>>, Error> {
    let mut out = Vec::new();
    let mut at = 0usize;
    while at < bytes.len() {
        let head = bytes
            .get(at..at + 12)
            .ok_or_else(|| Error::Blf(format!("a chunk header at byte {at} runs past the end")))?;
        let signature = [head[0], head[1], head[2], head[3]];
        let size = u32::from_be_bytes([head[4], head[5], head[6], head[7]]) as usize;
        let major = u16::from_be_bytes([head[8], head[9]]);
        let minor = u16::from_be_bytes([head[10], head[11]]);
        if size < 12 {
            return Err(Error::Blf(format!(
                "chunk {} at byte {at}: size {size}",
                String::from_utf8_lossy(&signature)
            )));
        }
        let body = bytes.get(at + 12..at + size).ok_or_else(|| {
            Error::Blf(format!(
                "chunk {} at byte {at}: {size} bytes run past the end",
                String::from_utf8_lossy(&signature)
            ))
        })?;
        out.push(Chunk {
            signature,
            major,
            minor,
            body,
        });
        at += size;
        if &signature == b"_eof" {
            break;
        }
    }
    if out.first().map(|c| &c.signature) != Some(b"_blf") {
        return Err(Error::Blf("no `_blf` chunk first".into()));
    }
    Ok(out)
}

/// A game variant from an `mpvr` or `gvar` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GameVariant<'a> {
    /// The chunk it came from: `mpvr` or `gvar`.
    pub chunk: [u8; 4],
    /// The chunk's version.
    pub major: u16,
    pub minor: u16,
    /// `mpvr`: the 20-byte hash at the start of the body (zero for `gvar`).
    pub hash: [u8; 20],
    /// `mpvr`: the 4 bytes after the hash (zero for `gvar`).
    pub unknown: [u8; 4],
    /// The engine type (the payload's first 4 bits).
    pub engine: u8,
    /// The payload (`length` bytes): the engine type, then the variant
    /// from bit 4.
    pub payload: &'a [u8],
}

/// A map variant from an `mvar` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MapVariant<'a> {
    /// The chunk's version (31.1 in every MCC Reach file).
    pub major: u16,
    pub minor: u16,
    /// The 20-byte hash at the start of the body.
    pub hash: [u8; 20],
    /// The payload (`length` bytes): the map variant's bitstream from bit 0,
    /// as the simulation's map-variant decoder (`0x32d810`) reads it.
    pub payload: &'a [u8],
}

/// The map variant of a BLF file (`haloreach/map_variants/*.mvar`): a body
/// of a 20-byte hash, a big-endian u32 payload length and the payload.
pub fn map_variant(bytes: &[u8]) -> Result<MapVariant<'_>, Error> {
    let chunks = chunks(bytes)?;
    let c = chunks
        .iter()
        .find(|c| &c.signature == b"mvar")
        .ok_or_else(|| Error::Blf("no `mvar` chunk".into()))?;
    let hash: [u8; 20] = c
        .body
        .get(..20)
        .and_then(|h| h.try_into().ok())
        .ok_or_else(|| Error::Blf("`mvar` shorter than its hash".into()))?;
    let len = c
        .body
        .get(20..24)
        .map(|b| u32::from_be_bytes([b[0], b[1], b[2], b[3]]) as usize)
        .ok_or_else(|| Error::Blf("`mvar` without a payload length".into()))?;
    let payload = c
        .body
        .get(24..24 + len)
        .ok_or_else(|| Error::Blf(format!("`mvar` payload of {len} bytes runs past the chunk")))?;
    Ok(MapVariant {
        major: c.major,
        minor: c.minor,
        hash,
        payload,
    })
}

/// The game variant of a BLF file.
pub fn game_variant(bytes: &[u8]) -> Result<GameVariant<'_>, Error> {
    let chunks = chunks(bytes)?;
    if let Some(c) = chunks.iter().find(|c| &c.signature == b"gvar") {
        return Ok(GameVariant {
            chunk: c.signature,
            major: c.major,
            minor: c.minor,
            hash: [0; 20],
            unknown: [0; 4],
            engine: c.body.first().map_or(0, |x| x >> 4),
            payload: c.body,
        });
    }
    let c = chunks
        .iter()
        .find(|c| &c.signature == b"mpvr")
        .ok_or_else(|| Error::Blf("no `mpvr` or `gvar` chunk".into()))?;
    let b = c.body;
    if b.len() < 28 {
        return Err(Error::Blf(format!("`mpvr` body of {} bytes", b.len())));
    }
    let mut hash = [0u8; 20];
    hash.copy_from_slice(&b[..20]);
    let unknown = [b[20], b[21], b[22], b[23]];
    let length = u32::from_be_bytes([b[24], b[25], b[26], b[27]]) as usize;
    let payload = b.get(28..28 + length).ok_or_else(|| {
        Error::Blf(format!(
            "`mpvr` payload of {length} bytes runs past its {}-byte body",
            b.len()
        ))
    })?;
    let engine = payload.first().map_or(0, |x| x >> 4);
    Ok(GameVariant {
        chunk: c.signature,
        major: c.major,
        minor: c.minor,
        hash,
        unknown,
        engine,
        payload,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(sig: &[u8; 4], body: &[u8]) -> Vec<u8> {
        let mut v = sig.to_vec();
        v.extend_from_slice(&((body.len() + 12) as u32).to_be_bytes());
        v.extend_from_slice(&[0, 1, 0, 2]);
        v.extend_from_slice(body);
        v
    }

    #[test]
    fn an_mpvr_payload_is_found() {
        let mut body = vec![7u8; 20];
        body.extend_from_slice(&[0, 0, 0, 0]);
        body.extend_from_slice(&3u32.to_be_bytes());
        body.extend_from_slice(&[0x20, 0x00, 0x06, 0xff, 0xff]);
        let mut file = chunk(b"_blf", &[0; 36]);
        file.extend(chunk(b"mpvr", &body));
        file.extend(chunk(b"_eof", &[0; 5]));
        file.extend_from_slice(&[0; 9]);
        let v = game_variant(&file).unwrap();
        assert_eq!(v.engine, ENGINE_MEGALO);
        assert_eq!(v.payload, &[0x20, 0x00, 0x06]);
        assert_eq!(v.hash, [7; 20]);
    }

    #[test]
    fn a_short_chunk_is_an_error() {
        let mut file = chunk(b"_blf", &[0; 4]);
        file.extend_from_slice(b"mpvr\0\0\x10\0");
        assert!(game_variant(&file).is_err());
    }
}
