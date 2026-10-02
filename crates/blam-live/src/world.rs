//! The simulation's objects and players, read out of its data arrays.
//!
//! An object lives in two places. The `object` array holds a 0x18-byte header
//! entry per object — salt, flags, type, size and a pointer — and the pointer
//! leads to the object's datum in the object memory pool, which starts with
//! the tag handle of its definition and carries the transform, links to its
//! parent and children, and its damage state.
//!
//! The layout here is Campaign Evolved's, which descends from Reach rather
//! than from the original Xbox engine: the object type codes are Reach's, and
//! vitality lives in an array of per-section records at the tail of the datum
//! rather than in two floats. Every offset below was measured on CU4
//! (`2026.08.11.1121610.2`) in A30 and checked against the code that reads it
//! — `object_get_health` (RVA `0x5b7e60`), the shield-section lookup
//! (`0x5b83b0`) and `player_get` (`0x1b21e0`); see `docs/game_state_reader.md`.
//! They are build-specific in a way the data array headers are not, so each
//! walk checks what it can: an entry must name its own slot, and a datum must
//! start with a handle the tag table knows.

use crate::gamestate::{DataArray, GameState};
use crate::tagtable::{Memory, Segments, TagTable};
use crate::{Error, Result};

pub const OBJECT_ARRAY: &str = "object";
pub const PLAYER_ARRAY: &str = "players";

/// The engine's "no handle".
pub const NONE: u32 = u32::MAX;

// --- object header entry (0x18 bytes) ---------------------------------------

const ENTRY_LEN: usize = 0x18;
const ENTRY_FLAGS: usize = 0x02;
const ENTRY_KIND: usize = 0x04;
/// Bytes of the datum in the pool.
const ENTRY_DATUM_SIZE: usize = 0x06;
/// The entry's own slot, repeated: the check that the layout still holds.
const ENTRY_INDEX: usize = 0x0c;
const ENTRY_DATUM: usize = 0x10;

// --- object datum -------------------------------------------------------------

/// Handle of the object's definition in the tag table.
const DATUM_TAG: usize = 0x00;
const DATUM_NEXT: usize = 0x0c;
const DATUM_FIRST_CHILD: usize = 0x10;
const DATUM_PARENT: usize = 0x14;
const DATUM_POSITION: usize = 0x44;
const DATUM_FORWARD: usize = 0x50;
const DATUM_UP: usize = 0x5c;
const DATUM_VELOCITY: usize = 0x68;
const DATUM_SCALE: usize = 0x80;
const DATUM_MAX_BODY: usize = 0x108;
const DATUM_MAX_SHIELD: usize = 0x10c;
/// Byte size, then offset from the datum, of the damage section records.
const DATUM_SECTIONS_SIZE: usize = 0x174;
const DATUM_SECTIONS_OFFSET: usize = 0x176;
/// Enough of the datum to reach every field above.
const DATUM_HEAD: usize = 0x178;

const SECTION_LEN: usize = 0x18;
/// `-1` when the section is not in play (a shield that was never built).
const SECTION_PRESENT: usize = 0x0e;
/// Current vitality as a fraction of the maximum.
const SECTION_VITALITY: usize = 0x10;

// --- definition tags ----------------------------------------------------------

/// In an object definition's root: the last word of its model reference, the
/// model tag's handle.
const OBJECT_TAG_MODEL: u64 = 0x60;
/// In a model definition's root: which damage section is the shield.
const MODEL_SHIELD_SECTION: u64 = 0xf0;

// --- player datum (0x4b0 bytes) -------------------------------------------------

/// The unit the player controls: what `player_get` returns.
const PLAYER_UNIT: usize = 0x28;
const PLAYER_TEAM: usize = 0xad;

/// What an object is, from its header entry. The codes are Reach's; the ones
/// marked were seen on CU4 with a tag of the matching group, the rest follow
/// the enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObjectKind {
    /// Seen (`bipd`).
    Biped,
    Vehicle,
    /// Seen (`weap`).
    Weapon,
    /// Seen (`eqip`).
    Equipment,
    /// Seen (`term`).
    Terminal,
    Projectile,
    Scenery,
    /// Seen (`mach`).
    Machine,
    Control,
    SoundScenery,
    Crate,
    Creature,
    Giant,
    /// Seen (`efsc`).
    EffectScenery,
    Other(u16),
}

impl ObjectKind {
    pub fn from_code(code: u16) -> ObjectKind {
        use ObjectKind::*;
        match code {
            0 => Biped,
            1 => Vehicle,
            2 => Weapon,
            3 => Equipment,
            4 => Terminal,
            5 => Projectile,
            6 => Scenery,
            7 => Machine,
            8 => Control,
            9 => SoundScenery,
            10 => Crate,
            11 => Creature,
            12 => Giant,
            13 => EffectScenery,
            n => Other(n),
        }
    }

    pub fn name(&self) -> String {
        use ObjectKind::*;
        match self {
            Biped => "biped".into(),
            Vehicle => "vehicle".into(),
            Weapon => "weapon".into(),
            Equipment => "equipment".into(),
            Terminal => "terminal".into(),
            Projectile => "projectile".into(),
            Scenery => "scenery".into(),
            Machine => "machine".into(),
            Control => "control".into(),
            SoundScenery => "sound scenery".into(),
            Crate => "crate".into(),
            Creature => "creature".into(),
            Giant => "giant".into(),
            EffectScenery => "effect scenery".into(),
            Other(n) => format!("type {n}"),
        }
    }
}

/// One damage section's state.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Section {
    pub present: bool,
    /// Fraction of the maximum, 0 to 1.
    pub vitality: f32,
}

/// One object in play.
#[derive(Debug, Clone, PartialEq)]
pub struct LiveObject {
    pub index: u32,
    pub handle: u32,
    pub kind: ObjectKind,
    /// The header entry's flag byte, raw.
    pub flags: u8,
    /// Where the datum is.
    pub datum: u64,
    pub datum_size: u16,
    /// Handle of the definition tag.
    pub tag: u32,
    pub parent: Option<u32>,
    pub first_child: Option<u32>,
    pub next: Option<u32>,
    /// World units, as the tags measure them. Relative to the parent for an
    /// attached object: a held rifle sits a few hundredths from zero.
    pub position: [f32; 3],
    pub forward: [f32; 3],
    pub up: [f32; 3],
    /// World units per tick.
    pub velocity: [f32; 3],
    pub scale: f32,
    pub max_body: f32,
    pub max_shield: f32,
    pub sections: Vec<Section>,
}

impl LiveObject {
    /// Current body vitality as a fraction: the first section, as
    /// `object_get_health` reads it. `None` for an object without sections.
    pub fn health(&self) -> Option<f32> {
        self.sections.first().map(|s| s.vitality)
    }

    /// Current shield vitality as a fraction, given the model's shield
    /// section ([`shield_section`]).
    pub fn shield(&self, section: Option<i16>) -> Option<f32> {
        let s = self.sections.get(usize::try_from(section?).ok()?)?;
        s.present.then_some(s.vitality)
    }
}

/// One player.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LivePlayer {
    pub index: u32,
    pub handle: u32,
    /// The unit this player controls, if any.
    pub unit: Option<u32>,
    /// The player's team (0 red, 1 blue, ... 8 neutral; -1 none). A player
    /// with no team never spawns (HaloSimulation CU4 `0x2ae6f0`).
    pub team: i8,
}

fn handle(v: u32) -> Option<u32> {
    (v != NONE).then_some(v)
}

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn vec3(b: &[u8], o: usize) -> [f32; 3] {
    [f32_at(b, o), f32_at(b, o + 4), f32_at(b, o + 8)]
}

fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes(b[o..o + 2].try_into().unwrap())
}

fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn layout(detail: String) -> Error {
    Error::Layout {
        what: "object table",
        detail,
    }
}

/// The `object` array, or `NoMission` while no game has reset it.
fn open(m: &impl Memory, gs: &GameState, name: &str) -> Result<DataArray> {
    let a = gs.fresh(m, name)?;
    if !a.valid {
        return Err(Error::NoMission);
    }
    Ok(a)
}

/// Every object in play, in slot order.
pub fn objects(m: &impl Memory, gs: &GameState) -> Result<Vec<LiveObject>> {
    let array = open(m, gs, OBJECT_ARRAY)?;
    if array.element_size as usize != ENTRY_LEN {
        return Err(layout(format!(
            "header entries are {:#x} bytes, not {ENTRY_LEN:#x}",
            array.element_size
        )));
    }
    let mut out = Vec::with_capacity(array.used as usize);
    for entry in array.walk(m)? {
        let e = &entry.bytes;
        let own = u32::from(u16_at(e, ENTRY_INDEX));
        if own != entry.index {
            return Err(layout(format!(
                "slot {} names itself {own}; the header entry has moved",
                entry.index
            )));
        }
        let datum = u64::from_le_bytes(e[ENTRY_DATUM..ENTRY_DATUM + 8].try_into().unwrap());
        let datum_size = u16_at(e, ENTRY_DATUM_SIZE);
        if datum == 0 || (datum_size as usize) < DATUM_HEAD {
            return Err(layout(format!(
                "slot {} has a {datum_size:#x}-byte datum at {datum:#x}",
                entry.index
            )));
        }
        let d = m.read(datum, DATUM_HEAD)?;
        let sections_size = u16_at(&d, DATUM_SECTIONS_SIZE) as usize;
        let sections_offset = u16_at(&d, DATUM_SECTIONS_OFFSET) as u64;
        let sections = if sections_size >= SECTION_LEN {
            let s = m.read(datum + sections_offset, sections_size)?;
            s.chunks_exact(SECTION_LEN)
                .map(|r| Section {
                    present: u16_at(r, SECTION_PRESENT) != 0xFFFF,
                    vitality: f32_at(r, SECTION_VITALITY),
                })
                .collect()
        } else {
            Vec::new()
        };
        out.push(LiveObject {
            index: entry.index,
            handle: entry.handle(),
            kind: ObjectKind::from_code(u16_at(e, ENTRY_KIND)),
            flags: e[ENTRY_FLAGS],
            datum,
            datum_size,
            tag: u32_at(&d, DATUM_TAG),
            parent: handle(u32_at(&d, DATUM_PARENT)),
            first_child: handle(u32_at(&d, DATUM_FIRST_CHILD)),
            next: handle(u32_at(&d, DATUM_NEXT)),
            position: vec3(&d, DATUM_POSITION),
            forward: vec3(&d, DATUM_FORWARD),
            up: vec3(&d, DATUM_UP),
            velocity: vec3(&d, DATUM_VELOCITY),
            scale: f32_at(&d, DATUM_SCALE),
            max_body: f32_at(&d, DATUM_MAX_BODY),
            max_shield: f32_at(&d, DATUM_MAX_SHIELD),
            sections,
        });
    }
    Ok(out)
}

/// Every player, in slot order.
pub fn players(m: &impl Memory, gs: &GameState) -> Result<Vec<LivePlayer>> {
    let array = open(m, gs, PLAYER_ARRAY)?;
    if (array.element_size as usize) < PLAYER_UNIT + 4 {
        return Err(layout(format!(
            "player datums are {:#x} bytes",
            array.element_size
        )));
    }
    Ok(array
        .walk(m)?
        .into_iter()
        .map(|p| LivePlayer {
            index: p.index,
            handle: p.handle(),
            unit: handle(u32_at(&p.bytes, PLAYER_UNIT)),
            team: p.bytes[PLAYER_TEAM] as i8,
        })
        .collect())
}

/// Which damage section is an object definition's shield: the definition's
/// model, then the model's shield index — the chain `unit_get_shield`
/// follows. `None` when the object has no model or the model no shield.
pub fn shield_section(
    m: &impl Memory,
    table: &TagTable,
    segments: &Segments,
    object_tag: u32,
) -> Result<Option<i16>> {
    let root = |h: u32| -> Result<Option<u64>> {
        let Some(tag) = table.entry(m, h & 0xFFFF)? else {
            return Ok(None);
        };
        if tag.handle() != h {
            return Ok(None);
        }
        Ok(tag.root_address(segments))
    };
    let Some(object_root) = root(object_tag)? else {
        return Ok(None);
    };
    let model = m.u32(object_root + OBJECT_TAG_MODEL)?;
    if model == NONE {
        return Ok(None);
    }
    let Some(model_root) = root(model)? else {
        return Ok(None);
    };
    let b = m.read(model_root + MODEL_SHIELD_SECTION, 2)?;
    let index = i16::from_le_bytes([b[0], b[1]]);
    Ok((index >= 0).then_some(index))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gamestate::testing::header;
    use crate::tagtable::testing::Mock;
    use crate::ThreadInfo;

    const TEB: u64 = 0x7a_0000_0000;
    const SLOTS: u64 = 0x0134_9000_0000;
    const BLOCK: u64 = 0x0134_94d1_17f0;
    const OBJECTS: u64 = 0x0134_fdb9_528c;
    const PLAYERS: u64 = 0x0134_fdb9_6000;
    const POOL: u64 = 0x0134_fdba_13fc;

    /// A datum shaped like the Spartan's in A30, measured values included.
    fn spartan() -> Vec<u8> {
        let mut d = vec![0u8; 0x200];
        let put = |d: &mut Vec<u8>, o: usize, v: &[u8]| d[o..o + v.len()].copy_from_slice(v);
        put(&mut d, DATUM_TAG, &0xE187_0013u32.to_le_bytes());
        put(&mut d, DATUM_NEXT, &NONE.to_le_bytes());
        put(&mut d, DATUM_FIRST_CHILD, &0xE298_0002u32.to_le_bytes());
        put(&mut d, DATUM_PARENT, &NONE.to_le_bytes());
        for (i, v) in [31.18f32, -99.65, 58.73, -0.1736, 0.9848, 0.0, 0.0, 0.0, 1.0]
            .iter()
            .enumerate()
        {
            put(&mut d, DATUM_POSITION + 4 * i, &v.to_le_bytes());
        }
        put(&mut d, DATUM_SCALE, &1.0f32.to_le_bytes());
        put(&mut d, DATUM_MAX_BODY, &45.0f32.to_le_bytes());
        put(&mut d, DATUM_MAX_SHIELD, &70.0f32.to_le_bytes());
        // Three sections at +0x180: body, an absent one, the shield.
        put(
            &mut d,
            DATUM_SECTIONS_SIZE,
            &(3 * SECTION_LEN as u16).to_le_bytes(),
        );
        put(&mut d, DATUM_SECTIONS_OFFSET, &0x180u16.to_le_bytes());
        for (i, (present, v)) in [(true, 0.5f32), (false, 1.0), (true, 0.25)]
            .iter()
            .enumerate()
        {
            let r = 0x180 + i * SECTION_LEN;
            put(
                &mut d,
                r + SECTION_PRESENT,
                &(if *present { 0u16 } else { 0xFFFF }).to_le_bytes(),
            );
            put(&mut d, r + SECTION_VITALITY, &v.to_le_bytes());
        }
        d
    }

    fn entry(generation: u16, index: u16, kind: u16, size: u16, datum: u64) -> Vec<u8> {
        let mut e = vec![0u8; ENTRY_LEN];
        e[0..2].copy_from_slice(&generation.to_le_bytes());
        e[ENTRY_FLAGS] = 0x87;
        e[ENTRY_KIND..ENTRY_KIND + 2].copy_from_slice(&kind.to_le_bytes());
        e[ENTRY_DATUM_SIZE..ENTRY_DATUM_SIZE + 2].copy_from_slice(&size.to_le_bytes());
        e[ENTRY_INDEX..ENTRY_INDEX + 2].copy_from_slice(&index.to_le_bytes());
        e[ENTRY_DATUM..ENTRY_DATUM + 8].copy_from_slice(&datum.to_le_bytes());
        e
    }

    fn game() -> (Mock, GameState) {
        let mut m = Mock::default();
        m.put_u64(TEB + 0x58, SLOTS);
        let mut slots = vec![0u8; 8 * 93];
        slots[8 * 92..].copy_from_slice(&BLOCK.to_le_bytes());
        m.put(SLOTS, &slots);
        let mut block = vec![0u8; 0x650];
        block[0x20..0x28].copy_from_slice(&OBJECTS.to_le_bytes());
        block[0x30..0x38].copy_from_slice(&PLAYERS.to_le_bytes());
        m.put(BLOCK, &block);

        m.put(
            OBJECTS,
            &header("object", 0x18, 2048, 2, 1, OBJECTS + 0x70, OBJECTS + 0x1000),
        );
        m.put(OBJECTS + 0x1000, &[0b10]);
        let mut entries = vec![0u8; ENTRY_LEN];
        entries.extend(entry(0xE295, 1, 0, 0x6138, POOL + 0x74));
        m.put(OBJECTS + 0x70, &entries);
        m.put(POOL + 0x74, &spartan());

        m.put(
            PLAYERS,
            &header("players", 0x4b0, 16, 1, 1, PLAYERS + 0x70, PLAYERS + 0x5000),
        );
        m.put(PLAYERS + 0x5000, &[1]);
        let mut p = vec![0u8; 0x4b0];
        p[0..2].copy_from_slice(&0xEC70u16.to_le_bytes());
        p[PLAYER_UNIT..PLAYER_UNIT + 4].copy_from_slice(&0xE295_0001u32.to_le_bytes());
        p[PLAYER_TEAM] = 1;
        m.put(PLAYERS + 0x70, &p);

        let gs = GameState::locate(&m, &[ThreadInfo { tid: 7, teb: TEB }], 92, 0x650).unwrap();
        (m, gs)
    }

    #[test]
    fn an_object_reads_its_transform_links_and_vitality() {
        let (m, gs) = game();
        let objects = objects(&m, &gs).unwrap();
        assert_eq!(objects.len(), 1);
        let o = &objects[0];
        assert_eq!((o.index, o.handle), (1, 0xE295_0001));
        assert_eq!(o.kind, ObjectKind::Biped);
        assert_eq!(o.tag, 0xE187_0013);
        assert_eq!((o.parent, o.first_child), (None, Some(0xE298_0002)));
        assert_eq!(o.position, [31.18, -99.65, 58.73]);
        assert_eq!(o.up, [0.0, 0.0, 1.0]);
        assert_eq!((o.max_body, o.max_shield), (45.0, 70.0));
        assert_eq!(o.health(), Some(0.5));
        assert_eq!(o.shield(Some(2)), Some(0.25));
        assert_eq!(o.shield(Some(1)), None, "an absent section is no shield");
        assert_eq!(o.shield(None), None);
    }

    #[test]
    fn a_player_names_the_unit_it_controls() {
        let (m, gs) = game();
        let players = players(&m, &gs).unwrap();
        assert_eq!(
            players,
            [LivePlayer {
                index: 0,
                handle: 0xEC70_0000,
                unit: Some(0xE295_0001),
                team: 1,
            }]
        );
    }

    #[test]
    fn an_entry_that_does_not_name_its_own_slot_is_refused() {
        let (mut m, gs) = game();
        let mut entries = vec![0u8; ENTRY_LEN];
        entries.extend(entry(0xE295, 7, 0, 0x6138, POOL + 0x74));
        m.put(OBJECTS + 0x70, &entries);
        assert!(matches!(
            objects(&m, &gs),
            Err(Error::Layout {
                what: "object table",
                ..
            })
        ));
    }

    #[test]
    fn no_game_in_progress_is_no_mission() {
        let (mut m, gs) = game();
        let mut h = header("object", 0x18, 2048, 2, 1, OBJECTS + 0x70, OBJECTS + 0x1000);
        h[0x31] = 0;
        m.put(OBJECTS, &h);
        assert!(matches!(objects(&m, &gs), Err(Error::NoMission)));
    }

    #[test]
    fn kinds_follow_the_reach_enum() {
        assert_eq!(ObjectKind::from_code(13), ObjectKind::EffectScenery);
        assert_eq!(ObjectKind::from_code(2).name(), "weapon");
        assert_eq!(ObjectKind::from_code(40).name(), "type 40");
    }
}
