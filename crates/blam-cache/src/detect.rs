//! Which game, and which build of it, a `.map` cache file comes from.
//!
//! Every Halo cache file opens with `head` (stored little-endian, so `daeh`
//! on disk) and an engine version, but the version alone no longer decides
//! the game: every title in The Master Chief Collection writes 13. MCC keeps
//! its own game index in the low byte of the u32 at 0x0C, and the header ends
//! with `foot` four bytes before its own size. Read off the installed maps of
//! every MCC title on 2026-10-21:
//!
//! | game | 0x0C | header | name | scenario path |
//! |---|---|---|---|---|
//! | Halo 1 | 0 | 0x800 | 0x20 | (none) |
//! | Halo 2 | 0x201 | 0x380 | 0xB0 | 0xD0 |
//! | Halo 3 | 0x202 | 0x4000 | 0xC0 | 0xE0 |
//! | Halo 4 | 0x203 | 0x1E000 | 0xB8 | 0xD8 |
//! | Halo 2 Anniversary MP | 0x204 | 0x1E000 | 0xB8 | 0xD8 |
//! | Halo: Reach | 0x206 | 0xA000 | 0xC0 | 0xE0 |
//!
//! Index 5 is taken to be Halo 3: ODST by elimination (not installed here).
//! The classic builds are told apart by version: Halo 1 Xbox 5, Halo 1 PC 7,
//! Custom Edition 609, Halo 2 Xbox and Vista 8.
//!
//! The conversion pipeline branches on [`Identity::stager`]: every Halo 1
//! build goes through halo2ue (HalcyonRing), Halo 2 MCC through this crate's
//! [`crate::h2`], and the other games are refused by name.

use std::fmt;

/// How much of a file [`identify`] wants to see: the largest MCC header
/// (Halo 4's) is 0x1E000 bytes.
pub const HEADER_PROBE: usize = 0x20000;

/// The game a cache file belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Game {
    Halo1,
    Halo2,
    Halo3,
    Halo3Odst,
    HaloReach,
    Halo4,
    /// Halo 2 Anniversary's multiplayer maps (MCC's `groundhog` folder):
    /// built on the Halo 4 engine, not Halo 2's.
    Halo2Anniversary,
}

impl Game {
    /// The short name scripts compare against (`mjolnir cache info --field game`).
    pub fn slug(self) -> &'static str {
        match self {
            Game::Halo1 => "halo1",
            Game::Halo2 => "halo2",
            Game::Halo3 => "halo3",
            Game::Halo3Odst => "halo3odst",
            Game::HaloReach => "haloreach",
            Game::Halo4 => "halo4",
            Game::Halo2Anniversary => "halo2a",
        }
    }

    pub fn title(self) -> &'static str {
        match self {
            Game::Halo1 => "Halo: Combat Evolved",
            Game::Halo2 => "Halo 2",
            Game::Halo3 => "Halo 3",
            Game::Halo3Odst => "Halo 3: ODST",
            Game::HaloReach => "Halo: Reach",
            Game::Halo4 => "Halo 4",
            Game::Halo2Anniversary => "Halo 2: Anniversary (multiplayer)",
        }
    }
}

impl fmt::Display for Game {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.title())
    }
}

/// The build a cache file was written by.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Build {
    Xbox,
    /// Halo 1 PC retail (version 7).
    Pc,
    /// Halo 1 Custom Edition (version 609), what the stock-map conversions read.
    CustomEdition,
    /// Halo 2 on Xbox or Vista (version 8; not told apart here).
    Classic,
    /// The Master Chief Collection on PC (version 13).
    Mcc,
}

impl Build {
    pub fn slug(self) -> &'static str {
        match self {
            Build::Xbox => "xbox",
            Build::Pc => "pc",
            Build::CustomEdition => "ce",
            Build::Classic => "classic",
            Build::Mcc => "mcc",
        }
    }
}

/// What the header says.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Identity {
    pub game: Game,
    pub build: Build,
    /// The engine version at 0x04.
    pub version: u32,
    /// Where the header ends (and the body, or its compressed chunks,
    /// begins): four bytes past `foot`, or 0x800 when `foot` was not seen.
    pub header_size: usize,
    /// The map's name as the header gives it (`lockout`, `bloodgulch`).
    pub name: String,
    /// The scenario's tag path, where the header carries it (MCC Halo 2 on).
    pub scenario: Option<String>,
    /// The body is stored compressed (MCC Halo 2's zlib chunks): the file is
    /// smaller than the size the header records.
    pub compressed: bool,
}

impl Identity {
    /// The tool that stages the map for conversion, if any does yet.
    pub fn stager(&self) -> Option<&'static str> {
        match (self.game, self.build) {
            // Every Halo 1 build goes to halo2ue, as every map did before
            // the games were told apart: it reads the PC and Custom Edition
            // builds, and the HEK-built version-13 maps padded to its tag
            // memory base (tools/level, proto_rad); a retail MCC or Xbox map
            // still fails inside it, as it always has.
            (Game::Halo1, _) => Some("halo2ue"),
            (Game::Halo2, Build::Mcc) => Some("blam-cache"),
            _ => None,
        }
    }
}

/// Why a file is not a cache file this module knows.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum NotCache {
    #[error("too short for a cache file header")]
    TooShort,
    #[error("no 'head' signature at offset 0")]
    NoHead,
    #[error("unknown cache version {0}")]
    UnknownVersion(u32),
    #[error("unknown MCC game index {0} at 0x0C")]
    UnknownMccGame(u8),
}

fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// A NUL-terminated string field, cut at `max` bytes.
fn cstr(b: &[u8], o: usize, max: usize) -> String {
    let end = (o + max).min(b.len());
    let s = &b[o.min(end)..end];
    let n = s.iter().position(|&c| c == 0).unwrap_or(s.len());
    String::from_utf8_lossy(&s[..n]).into_owned()
}

const HEAD: u32 = u32::from_le_bytes(*b"daeh");
const FOOT: u32 = u32::from_le_bytes(*b"toof");

/// The header's size from where `foot` sits: the first one at an offset
/// whose end is 0x80-aligned (every header seen ends on such a boundary,
/// and the body's bytes are compressed or tag data, so a stray match before
/// the real one would need to land on that alignment too).
fn footer_end(header: &[u8]) -> Option<usize> {
    (0x37C..header.len().saturating_sub(3))
        .step_by(4)
        .find(|&o| (o + 4) % 0x80 == 0 && u32_at(header, o) == FOOT)
        .map(|o| o + 4)
}

/// Identify a cache file from its first bytes (up to [`HEADER_PROBE`] of
/// them, or the whole file when shorter) and its length on disk.
pub fn identify(header: &[u8], file_len: u64) -> Result<Identity, NotCache> {
    if header.len() < 0x380 {
        return Err(NotCache::TooShort);
    }
    if u32_at(header, 0) != HEAD {
        return Err(NotCache::NoHead);
    }
    let version = u32_at(header, 4);
    let recorded = u32_at(header, 8) as u64;
    let (game, build) = match version {
        5 => (Game::Halo1, Build::Xbox),
        7 => (Game::Halo1, Build::Pc),
        609 => (Game::Halo1, Build::CustomEdition),
        8 => (Game::Halo2, Build::Classic),
        13 => {
            let game = match header[0x0C] {
                0 => Game::Halo1,
                1 => Game::Halo2,
                2 => Game::Halo3,
                3 => Game::Halo4,
                4 => Game::Halo2Anniversary,
                5 => Game::Halo3Odst,
                6 => Game::HaloReach,
                g => return Err(NotCache::UnknownMccGame(g)),
            };
            (game, Build::Mcc)
        }
        v => return Err(NotCache::UnknownVersion(v)),
    };
    let (name_at, path_at) = match (game, build) {
        (Game::Halo1, _) | (Game::Halo2, Build::Classic) => (0x20, None),
        (Game::Halo2, _) => (0xB0, Some(0xD0)),
        (Game::Halo4 | Game::Halo2Anniversary, _) => (0xB8, Some(0xD8)),
        _ => (0xC0, Some(0xE0)),
    };
    Ok(Identity {
        game,
        build,
        version,
        header_size: footer_end(header).unwrap_or(0x800),
        name: cstr(header, name_at, 32),
        scenario: path_at.map(|o| cstr(header, o, 256)).filter(|s| !s.is_empty()),
        compressed: recorded > file_len,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(version: u32, index: u8, size: usize) -> Vec<u8> {
        let mut b = vec![0u8; 0x2000];
        b[0..4].copy_from_slice(b"daeh");
        b[4..8].copy_from_slice(&version.to_le_bytes());
        b[8..12].copy_from_slice(&1000u32.to_le_bytes());
        b[0x0C] = index;
        if index != 0 {
            b[0x0D] = 2;
        }
        b[size - 4..size].copy_from_slice(b"toof");
        b
    }

    /// Every MCC title writes version 13; the game index at 0x0C is what
    /// tells them apart, and `foot` gives each header's size (values from the
    /// installed maps).
    #[test]
    fn mcc_titles_are_told_apart_by_the_game_index() {
        let h1 = identify(&header(13, 0, 0x800), 1000).unwrap();
        assert_eq!((h1.game, h1.build, h1.header_size), (Game::Halo1, Build::Mcc, 0x800));
        let mut b = header(13, 1, 0x380);
        b[0xB0..0xB7].copy_from_slice(b"lockout");
        b[0xD0..0xD5].copy_from_slice(b"a\\b\\c");
        let h2 = identify(&b, 500).unwrap();
        assert_eq!((h2.game, h2.build, h2.header_size), (Game::Halo2, Build::Mcc, 0x380));
        assert_eq!((h2.name.as_str(), h2.scenario.as_deref()), ("lockout", Some("a\\b\\c")));
        assert!(h2.compressed, "a file shorter than its recorded size is compressed");
        assert_eq!(identify(&header(13, 6, 0x1000), 1000).unwrap().game, Game::HaloReach);
        assert_eq!(identify(&header(13, 4, 0x1000), 1000).unwrap().game, Game::Halo2Anniversary);
        assert_eq!(identify(&header(13, 9, 0x1000), 1000), Err(NotCache::UnknownMccGame(9)));
    }

    /// The classic builds stay on their version numbers, so the stock-map
    /// conversions (Custom Edition, 609) keep going to halo2ue.
    #[test]
    fn classic_halo_1_builds_go_to_halo2ue() {
        let ce = identify(&header(609, 0, 0x800), 1000).unwrap();
        assert_eq!((ce.game, ce.build), (Game::Halo1, Build::CustomEdition));
        assert_eq!(ce.stager(), Some("halo2ue"));
        assert!(!ce.compressed);
        assert_eq!(identify(&header(7, 0, 0x800), 1000).unwrap().build, Build::Pc);
        // A version-13 Halo 1 map stays on halo2ue: the HEK-built ones,
        // padded to its tag base, stage there.
        let mcc = identify(&header(13, 0, 0x800), 1000).unwrap();
        assert_eq!(mcc.stager(), Some("halo2ue"));
        assert_eq!(identify(&header(5, 0, 0x800), 1000).unwrap().stager(), Some("halo2ue"));
    }

    #[test]
    fn a_file_without_head_is_refused() {
        let mut b = header(609, 0, 0x800);
        b[0] = b'x';
        assert_eq!(identify(&b, 1000), Err(NotCache::NoHead));
        assert_eq!(identify(&b[..16], 16), Err(NotCache::TooShort));
    }
}
