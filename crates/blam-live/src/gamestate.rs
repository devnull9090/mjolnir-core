//! The simulation's game state, reached through its thread-local storage.
//!
//! `HaloSimulation_tag_release.dll` keeps its per-game tables — objects,
//! players, actors, script threads, some sixty in all — in Blam **data
//! arrays**: a fixed header naming the array and its element size, a slab of
//! elements, and a bitset of which slots are live. The pointers to those
//! headers do not sit in module globals. The module declares a static TLS
//! block (0x650 bytes on CU4), and each constructor stores its array's header
//! into that block on the simulation thread:
//!
//! ```text
//! gs:[0x58]                      ThreadLocalStoragePointer (TEB + 0x58)
//!   [tls_index]                  this module's block on this thread
//!     + 0x20  -> "object"   header      + 0x30  -> "players" header  ...
//! ```
//!
//! So nothing here is a signature. The TLS index is read from the module's own
//! PE TLS directory, the thread environment blocks come from the OS, and every
//! header names itself and carries the `d@t@` magic at `+0x28`. The block is
//! scanned for pointers to such headers, which also means a slot that moves in
//! a later build is simply found at its new offset.
//!
//! Measured 2026-09-29 on CU4 (`2026.08.11.1121610.2`) in mission A30: one
//! thread of ~170 holds a populated block, with 59 arrays in it. The header
//! layout was read off the constructors (`players` at RVA `0x181010`,
//! `object` inside `0x59c520`); see `docs/game_state_reader.md`.

use crate::tagtable::Memory;
use crate::{Error, Process, Result, ThreadInfo};

/// `'d@t@'` as the constructors store it at `+0x28`.
pub const DATA_ARRAY_MAGIC: u32 = 0x6440_7440;

/// `TEB::ThreadLocalStoragePointer` on x64.
const TEB_TLS_POINTER: u64 = 0x58;

// --- data array header ------------------------------------------------------

/// A 32-byte name, NUL-terminated (so at most 31 characters survive:
/// `collision hierarchy element hea…`).
const NAME_LEN: usize = 0x20;
const ELEMENT_SIZE: usize = 0x20;
const MAGIC: usize = 0x28;
const MAXIMUM: usize = 0x2c;
/// Set once the array has been reset for a game; zero at the menu.
const VALID: usize = 0x31;
const FLAGS: usize = 0x32;
/// Blam's `first_unallocated`: one past the highest slot ever used.
const HIGH_WATER: usize = 0x44;
/// Blam's `actual_count`.
const USED: usize = 0x48;
/// Blam's `next_identifier`: the salt the next allocation will carry.
const NEXT_IDENTIFIER: usize = 0x4c;
const DATA: usize = 0x50;
const BITSET: usize = 0x58;
pub(crate) const HEADER_LEN: usize = 0x70;

/// Bounds a header must fall inside before it is believed. The largest array
/// on CU4 is `simulation distributed view` at 0x14f38 bytes an element, the
/// longest `tag streams` at 65535.
const MAX_ELEMENT_SIZE: u32 = 0x10_0000;
const MAX_ELEMENTS: u32 = 0x1_0000;

/// One data array's header, read once.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DataArray {
    /// Where the header is.
    pub address: u64,
    pub name: String,
    pub element_size: u32,
    pub maximum: u32,
    /// Whether the array has been reset for a game in progress.
    pub valid: bool,
    pub flags: u16,
    pub high_water: u32,
    pub used: u32,
    pub next_identifier: u16,
    pub data: u64,
    pub bitset: u64,
}

/// One live element: its slot, its salt, and its bytes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Datum {
    pub index: u32,
    /// The salt at the element's first two bytes. With the index it makes the
    /// handle other structures store: `salt << 16 | index`.
    pub salt: u16,
    pub bytes: Vec<u8>,
}

impl Datum {
    pub fn handle(&self) -> u32 {
        u32::from(self.salt) << 16 | self.index
    }
}

impl DataArray {
    /// Decode a header from its bytes, or `None` when they are not one.
    pub fn decode(address: u64, h: &[u8]) -> Option<DataArray> {
        if h.len() < HEADER_LEN {
            return None;
        }
        let u16_at = |o: usize| u16::from_le_bytes(h[o..o + 2].try_into().unwrap());
        let u32_at = |o: usize| u32::from_le_bytes(h[o..o + 4].try_into().unwrap());
        let u64_at = |o: usize| u64::from_le_bytes(h[o..o + 8].try_into().unwrap());
        if u32_at(MAGIC) != DATA_ARRAY_MAGIC {
            return None;
        }
        let element_size = u32_at(ELEMENT_SIZE);
        let maximum = u32_at(MAXIMUM);
        let high_water = u32_at(HIGH_WATER);
        let used = u32_at(USED);
        if element_size == 0
            || element_size > MAX_ELEMENT_SIZE
            || maximum > MAX_ELEMENTS
            || high_water > maximum
            || used > high_water
        {
            return None;
        }
        let end = h[..NAME_LEN]
            .iter()
            .position(|c| *c == 0)
            .unwrap_or(NAME_LEN);
        Some(DataArray {
            address,
            name: String::from_utf8_lossy(&h[..end]).into_owned(),
            element_size,
            maximum,
            valid: h[VALID] != 0,
            flags: u16_at(FLAGS),
            high_water,
            used,
            next_identifier: u16_at(NEXT_IDENTIFIER),
            data: u64_at(DATA),
            bitset: u64_at(BITSET),
        })
    }

    /// Read the header at `address`, or `None` when it is not one.
    pub fn read(m: &impl Memory, address: u64) -> Option<DataArray> {
        let h = m.read(address, HEADER_LEN).ok()?;
        DataArray::decode(address, &h)
    }

    /// The salt an array's first allocation carries: its name's first two
    /// bytes, little-endian, with the top bit set. `"object"` gives `0xE26F`,
    /// `"players"` `0xEC70`, `"tag instance"` `0xE174` — the handles the live
    /// tables hold. Each allocation takes the next value, so a handle's high
    /// word says which array it came from as well as which generation.
    pub fn seed(name: &str) -> u16 {
        let b = name.as_bytes();
        let lo = u16::from(*b.first().unwrap_or(&0));
        let hi = u16::from(*b.get(1).unwrap_or(&0));
        (hi << 8 | lo) | 0x8000
    }

    /// Every live element, in slot order.
    pub fn walk(&self, m: &impl Memory) -> Result<Vec<Datum>> {
        let high = self.high_water as usize;
        if high == 0 || !self.valid {
            return Ok(Vec::new());
        }
        let size = self.element_size as usize;
        let bits = m.read(self.bitset, high.div_ceil(8))?;
        let blob = m.read(self.data, high * size)?;
        let mut out = Vec::with_capacity(self.used as usize);
        for i in 0..high {
            if bits[i / 8] & (1 << (i % 8)) == 0 {
                continue;
            }
            let bytes = blob[i * size..(i + 1) * size].to_vec();
            out.push(Datum {
                index: i as u32,
                salt: u16::from_le_bytes(bytes[0..2].try_into().unwrap()),
                bytes,
            });
        }
        Ok(out)
    }
}

// --- the module's TLS directory -----------------------------------------------

/// What the module's PE TLS directory says, read from its mapped image.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TlsDirectory {
    /// Where the loader wrote the module's TLS slot number.
    pub index_address: u64,
    /// Bytes in each thread's copy of the block: the template plus zero fill.
    pub block_size: u64,
}

impl TlsDirectory {
    /// Parse the directory out of the image mapped at `base`. The loader
    /// relocates its addresses along with the image, so they are live
    /// addresses as read, whatever the ASLR base.
    pub fn read(m: &impl Memory, base: u64) -> Result<TlsDirectory> {
        let bad = |detail: String| Error::Layout {
            what: "tag module TLS directory",
            detail,
        };
        let e_lfanew = u64::from(m.u32(base + 0x3c)?);
        if m.u32(base + e_lfanew)? != 0x0000_4550 {
            return Err(bad("no PE signature at e_lfanew".into()));
        }
        let optional = base + e_lfanew + 24;
        if m.u16(optional)? != 0x20b {
            return Err(bad("not a PE32+ image".into()));
        }
        // Data directory 9 of the PE32+ optional header.
        let rva = u64::from(m.u32(optional + 112 + 9 * 8)?);
        if rva == 0 {
            return Err(bad("the module declares no TLS".into()));
        }
        let d = m.read(base + rva, 0x28)?;
        let u64_at = |o: usize| u64::from_le_bytes(d[o..o + 8].try_into().unwrap());
        let (start, end, index_address) = (u64_at(0), u64_at(8), u64_at(16));
        let zero_fill = u64::from(u32::from_le_bytes(d[32..36].try_into().unwrap()));
        if end < start || end - start + zero_fill > 0x10_0000 {
            return Err(bad(format!(
                "template {start:#x}..{end:#x} plus {zero_fill:#x} zero fill"
            )));
        }
        Ok(TlsDirectory {
            index_address,
            block_size: end - start + zero_fill,
        })
    }
}

// --- locating the simulation thread's block ------------------------------------

/// The array whose presence marks the simulation thread.
pub const MARKER_ARRAY: &str = "object";

/// The simulation thread's TLS block and every data array it points at.
#[derive(Debug, Clone)]
pub struct GameState {
    pub tid: u32,
    /// This thread's copy of the module's TLS block.
    pub block: u64,
    pub tls_index: u32,
    /// `(offset in the block, header)`, in block order.
    pub arrays: Vec<(u64, DataArray)>,
}

impl GameState {
    /// Attach to a running game: the tag module's TLS slot, then every thread
    /// of the process, keeping the one whose block holds the `object` array.
    pub fn attach(process: &Process) -> Result<GameState> {
        let module = process.module_info(crate::tagtable::TAG_DLL)?;
        let tls = TlsDirectory::read(process, module.base)?;
        let tls_index = process.u32(tls.index_address)?;
        GameState::locate(process, &process.threads()?, tls_index, tls.block_size)
    }

    /// Find the simulation thread among `threads`.
    ///
    /// Every thread gets a copy of the block, but only the simulation thread's
    /// is populated. Should more than one hold the marker array, the one
    /// holding the most arrays wins.
    pub fn locate(
        m: &impl Memory,
        threads: &[ThreadInfo],
        tls_index: u32,
        block_size: u64,
    ) -> Result<GameState> {
        let mut best: Option<GameState> = None;
        for t in threads {
            let Ok(slots) = m.u64(t.teb + TEB_TLS_POINTER) else {
                continue;
            };
            if slots == 0 {
                continue;
            }
            let Ok(block) = m.u64(slots + 8 * u64::from(tls_index)) else {
                continue;
            };
            if block == 0 {
                continue;
            }
            let Ok(arrays) = scan_block(m, block, block_size) else {
                continue;
            };
            if !arrays.iter().any(|(_, a)| a.name == MARKER_ARRAY) {
                continue;
            }
            if best.as_ref().is_none_or(|b| arrays.len() > b.arrays.len()) {
                best = Some(GameState {
                    tid: t.tid,
                    block,
                    tls_index,
                    arrays,
                });
            }
        }
        best.ok_or_else(|| Error::Layout {
            what: "game state",
            detail: format!(
                "none of {} threads has a TLS block (slot {tls_index}) pointing at an `{MARKER_ARRAY}` data array",
                threads.len()
            ),
        })
    }

    /// The array with this name.
    pub fn array(&self, name: &str) -> Option<&DataArray> {
        self.arrays.iter().map(|(_, a)| a).find(|a| a.name == name)
    }

    /// The array with this name, re-read now. The header in `arrays` is a
    /// photograph; high water and the live count move as the game runs.
    pub fn fresh(&self, m: &impl Memory, name: &str) -> Result<DataArray> {
        let at = self
            .array(name)
            .map(|a| a.address)
            .ok_or_else(|| Error::Layout {
                what: "game state",
                detail: format!("no `{name}` data array in the simulation's TLS block"),
            })?;
        DataArray::read(m, at).ok_or_else(|| Error::Layout {
            what: "game state",
            detail: format!("the `{name}` header at {at:#x} no longer reads as a data array"),
        })
    }
}

/// Every pointer in a block that leads to a data array header.
fn scan_block(m: &impl Memory, block: u64, size: u64) -> Result<Vec<(u64, DataArray)>> {
    let raw = m.read(block, size as usize)?;
    let mut out = Vec::new();
    for off in (0..raw.len().saturating_sub(7)).step_by(8) {
        let p = u64::from_le_bytes(raw[off..off + 8].try_into().unwrap());
        // User-mode, and not a small integer that happens to sit in the block.
        if !(0x1_0000..0x8000_0000_0000).contains(&p) {
            continue;
        }
        if let Some(a) = DataArray::read(m, p) {
            out.push((off as u64, a));
        }
    }
    Ok(out)
}

#[cfg(test)]
pub(crate) mod testing {
    use super::*;

    /// A header's bytes, as a constructor leaves them.
    pub fn header(
        name: &str,
        element_size: u32,
        maximum: u32,
        high: u32,
        used: u32,
        data: u64,
        bitset: u64,
    ) -> Vec<u8> {
        let mut h = vec![0u8; HEADER_LEN];
        h[..name.len()].copy_from_slice(name.as_bytes());
        h[ELEMENT_SIZE..ELEMENT_SIZE + 4].copy_from_slice(&element_size.to_le_bytes());
        h[MAGIC..MAGIC + 4].copy_from_slice(&DATA_ARRAY_MAGIC.to_le_bytes());
        h[MAXIMUM..MAXIMUM + 4].copy_from_slice(&maximum.to_le_bytes());
        h[VALID] = 1;
        h[FLAGS..FLAGS + 2].copy_from_slice(&4u16.to_le_bytes());
        h[HIGH_WATER..HIGH_WATER + 4].copy_from_slice(&high.to_le_bytes());
        h[USED..USED + 4].copy_from_slice(&used.to_le_bytes());
        h[DATA..DATA + 8].copy_from_slice(&data.to_le_bytes());
        h[BITSET..BITSET + 8].copy_from_slice(&bitset.to_le_bytes());
        h[0x60..0x68].copy_from_slice(&(HEADER_LEN as u64).to_le_bytes());
        h
    }
}

#[cfg(test)]
mod tests {
    use super::testing::header;
    use super::*;
    use crate::tagtable::testing::Mock;

    const BLOCK: u64 = 0x0134_94d1_17f0;
    const SLOTS: u64 = 0x0134_9000_0000;
    const TEB_SIM: u64 = 0x7a_0000_0000;
    const TEB_OTHER: u64 = 0x7a_0000_2000;
    const OBJECT_AT: u64 = 0x0134_fdb9_528c;
    const PLAYERS_AT: u64 = 0x0134_fdb9_6000;

    fn game() -> Mock {
        let mut m = Mock::default();
        // Two threads: one with an empty block, one the simulation's.
        m.put_u64(TEB_OTHER + TEB_TLS_POINTER, SLOTS + 0x1000);
        m.put(SLOTS + 0x1000, &vec![0u8; 8 * 100]);
        m.put_u64(TEB_SIM + TEB_TLS_POINTER, SLOTS);
        let mut slots = vec![0u8; 8 * 100];
        slots[8 * 92..8 * 93].copy_from_slice(&BLOCK.to_le_bytes());
        m.put(SLOTS, &slots);
        let mut block = vec![0u8; 0x650];
        block[0x20..0x28].copy_from_slice(&OBJECT_AT.to_le_bytes());
        block[0x30..0x38].copy_from_slice(&PLAYERS_AT.to_le_bytes());
        // A pointer-looking value that leads nowhere readable, and one that
        // leads to bytes without the magic: neither is an array.
        block[0x40..0x48].copy_from_slice(&0x5555_0000_0000u64.to_le_bytes());
        block[0x48..0x50].copy_from_slice(&(SLOTS + 8).to_le_bytes());
        m.put(BLOCK, &block);
        m.put(
            OBJECT_AT,
            &header(
                "object",
                0x18,
                2048,
                3,
                2,
                OBJECT_AT + 0x70,
                OBJECT_AT + 0x1000,
            ),
        );
        m.put(
            PLAYERS_AT,
            &header(
                "players",
                0x4b0,
                16,
                1,
                1,
                PLAYERS_AT + 0x70,
                PLAYERS_AT + 0x5000,
            ),
        );
        m
    }

    fn threads() -> Vec<ThreadInfo> {
        vec![
            ThreadInfo {
                tid: 1,
                teb: TEB_OTHER,
            },
            ThreadInfo {
                tid: 2,
                teb: 0xdead_0000,
            },
            ThreadInfo {
                tid: 39024,
                teb: TEB_SIM,
            },
        ]
    }

    #[test]
    fn the_simulation_thread_is_the_one_whose_block_names_arrays() {
        let m = game();
        let gs = GameState::locate(&m, &threads(), 92, 0x650).unwrap();
        assert_eq!(gs.tid, 39024);
        assert_eq!(gs.block, BLOCK);
        let names: Vec<_> = gs
            .arrays
            .iter()
            .map(|(o, a)| (*o, a.name.as_str()))
            .collect();
        assert_eq!(names, [(0x20, "object"), (0x30, "players")]);
        let object = gs.array("object").unwrap();
        assert_eq!((object.element_size, object.maximum), (0x18, 2048));
        assert_eq!((object.high_water, object.used), (3, 2));
    }

    #[test]
    fn no_marker_array_is_an_error_not_a_guess() {
        let mut m = game();
        let mut block = vec![0u8; 0x650];
        block[0x30..0x38].copy_from_slice(&PLAYERS_AT.to_le_bytes());
        m.put(BLOCK, &block);
        assert!(matches!(
            GameState::locate(&m, &threads(), 92, 0x650),
            Err(Error::Layout {
                what: "game state",
                ..
            })
        ));
    }

    #[test]
    fn walk_returns_live_slots_with_their_salts() {
        let mut m = game();
        m.put(OBJECT_AT + 0x1000, &[0b101]);
        let mut data = vec![0u8; 3 * 0x18];
        data[0..2].copy_from_slice(&0xE26Fu16.to_le_bytes());
        data[0x30..0x32].copy_from_slice(&0xE271u16.to_le_bytes());
        m.put(OBJECT_AT + 0x70, &data);
        let a = DataArray::read(&m, OBJECT_AT).unwrap();
        let live = a.walk(&m).unwrap();
        assert_eq!(
            live.iter().map(|d| d.handle()).collect::<Vec<_>>(),
            [0xE26F_0000, 0xE271_0002]
        );
    }

    #[test]
    fn an_array_not_yet_reset_for_a_game_is_empty() {
        let mut m = game();
        let mut h = header(
            "object",
            0x18,
            2048,
            3,
            2,
            OBJECT_AT + 0x70,
            OBJECT_AT + 0x1000,
        );
        h[VALID] = 0;
        m.put(OBJECT_AT, &h);
        assert!(DataArray::read(&m, OBJECT_AT)
            .unwrap()
            .walk(&m)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn implausible_headers_are_refused() {
        let good = header("object", 0x18, 2048, 3, 2, 1, 1);
        assert!(DataArray::decode(0, &good).is_some());
        let mut h = good.clone();
        h[MAGIC] ^= 1;
        assert!(DataArray::decode(0, &h).is_none(), "magic");
        let mut h = good.clone();
        h[HIGH_WATER..HIGH_WATER + 4].copy_from_slice(&4096u32.to_le_bytes());
        assert!(
            DataArray::decode(0, &h).is_none(),
            "high water past the maximum"
        );
        let mut h = good;
        h[USED..USED + 4].copy_from_slice(&9u32.to_le_bytes());
        assert!(
            DataArray::decode(0, &h).is_none(),
            "more used than ever allocated"
        );
    }

    /// The seeds the live tables were measured holding on CU4.
    #[test]
    fn seeds_match_the_measured_handles() {
        assert_eq!(DataArray::seed("object"), 0xE26F);
        assert_eq!(DataArray::seed("players"), 0xEC70);
        assert_eq!(DataArray::seed("tag instance"), 0xE174);
    }

    #[test]
    fn the_tls_directory_is_read_from_the_mapped_image() {
        const BASE: u64 = 0x7fff_dd29_0000;
        let mut m = Mock::default();
        let mut image = vec![0u8; 0x400];
        image[0x3c..0x40].copy_from_slice(&0x100u32.to_le_bytes());
        image[0x100..0x104].copy_from_slice(b"PE\0\0");
        image[0x118..0x11a].copy_from_slice(&0x20bu16.to_le_bytes());
        let dir = 0x118 + 112 + 9 * 8;
        image[dir..dir + 4].copy_from_slice(&0x8f_4700u32.to_le_bytes());
        m.put(BASE, &image);
        let mut tls = vec![0u8; 0x28];
        tls[0..8].copy_from_slice(&(BASE + 0x8f_7740).to_le_bytes());
        tls[8..16].copy_from_slice(&(BASE + 0x8f_7d90).to_le_bytes());
        tls[16..24].copy_from_slice(&(BASE + 0xd7_2730).to_le_bytes());
        m.put(BASE + 0x8f_4700, &tls);
        let d = TlsDirectory::read(&m, BASE).unwrap();
        assert_eq!(d.index_address, BASE + 0xd7_2730);
        assert_eq!(d.block_size, 0x650);
    }
}
