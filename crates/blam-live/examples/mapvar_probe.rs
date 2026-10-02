//! Read, without writing anything, the two things that decide whether the
//! running Megalo game creates its map variant's grenades and power-ups:
//!
//! - the map options byte of the game options the creation check reads
//!   (`[TLS+0x60] + 0x18f0`: the variant at `+0x15f4`, its options at `+0x2fc`;
//!   check `0x5ee0d0`), whose bits 0/2/3 allow grenade, equipment and powerup
//!   multiplayer types;
//! - the map variant's object entries (`[TLS+0x250] + 0x308`, entries from
//!   `+0x14fc`, 0x4c bytes each, 651 of them; bit 0 of the first byte = in
//!   use, `+0x43` = multiplayer object type).
//!
//!   cargo run -p blam-live --example mapvar_probe
//!
//! RVAs and offsets are CU4 (HaloSimulation_tag_release.dll).
use blam_live::gamestate::GameState;
use blam_live::tagtable::Memory;
use blam_live::Process;
use std::collections::BTreeMap;

const ENTRIES: u64 = 0x14fc;
const ENTRY: u64 = 0x4c;
const COUNT: u64 = 0x28b;

fn main() {
    let process = Process::attach().expect("the game is not running");
    let gs = GameState::attach(&process).expect("no simulation game state");
    println!("simulation thread {} block {:#x}", gs.tid, gs.block);

    let options = process.u64(gs.block + 0x60).expect("TLS+0x60");
    let flags = process.read(options + 0x18f0, 1).expect("options+0x18f0")[0];
    println!("game options {options:#x}: map options byte {flags:#04x}");
    for (bit, what) in [
        (0, "grenades"),
        (1, "shortcuts"),
        (2, "equipment"),
        (3, "powerups"),
        (4, "turrets"),
        (5, "indestructible vehicles"),
    ] {
        println!("  bit {bit} {what:24} {}", flags >> bit & 1);
    }

    let globals = process.u64(gs.block + 0x250).expect("TLS+0x250");
    let variant = globals + 0x308;
    let raw = process
        .read(variant + ENTRIES, (ENTRY * COUNT) as usize)
        .expect("map variant entries");
    let mut by_type: BTreeMap<u8, usize> = BTreeMap::new();
    for e in raw.chunks(ENTRY as usize) {
        if e[0] & 1 != 0 {
            *by_type.entry(e[0x43]).or_default() += 1;
        }
    }
    println!("map variant {variant:#x}: entries in use by multiplayer type");
    for (t, n) in by_type {
        println!("  type {t:3}: {n:3}");
    }
}
