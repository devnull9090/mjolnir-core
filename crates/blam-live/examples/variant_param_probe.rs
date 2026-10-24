//! Read-only reachability probe: does *this* machine's simulation ever run the
//! networked-variant decode path (`0x51d1b0` reassemble -> `0x392a40` decode)?
//!
//! Run it on the **joiner** during an **unmodified retail** campaign co-op
//! session (MJOLNIR's `mjolnir_map_registry.dll` NOT loaded; if the Megalo
//! switch is on you are testing MJOLNIR, not retail). It writes nothing to the
//! game — only `ReadProcessMemory` on a handful of addresses — and polls once a
//! second, printing a line whenever something changes plus a heartbeat.
//!
//! It answers the question three ways, strongest first. See
//! `docs/re/variant_network_safety.md`, "Is this reachable in unmodified
//! retail?" and "The safe read-only reachability check".
//!
//!   1. ENGINE  game-engine index  [[TLS+0x38]]+0x846c  (current_game_engine,
//!      sim 0x180e70): 0 menu, 2 Megalo, 3 campaign, 4 firefight.
//!   2. MODE    game options mode byte  [[TLS+0x60]]+0x10: 1 campaign,
//!      2 multiplayer, 3 frontend.
//!   3. VARIANT live game variant  [[TLS+0x60]]+0x15f0: u16 type (2 = Megalo),
//!      object at +4; for a Megalo variant, +0x5dc0 is the decoder's encoding
//!      version (0x6a/0x6b) -- a value there is the smoking gun that the
//!      bitstream decoder produced the live variant.
//!   4. SESSION  sim session object  *(base+0xca3480), valid *(base+0xca3420),
//!      and (best effort) the game-variant session parameter's received-chunk
//!      state. The parameter's size/count/version fields are self-validating:
//!      if they read as a real variant (version 0x6a/0x6b, size 1..0x5000,
//!      chunk count 1..40) the offset is right AND a variant arrived over the
//!      wire; if they do not, no variant is parked there.
//!
//! Reading of it: if, across a whole retail co-op session (menu -> joining ->
//! in the mission), ENGINE stays 0/3, MODE stays 1/3, the live VARIANT stays
//! type 3 (campaign), and no valid SESSION parameter ever appears, then this
//! machine never fed the unbounded decoder over the network -- the exposure is
//! MJOLNIR-only. If a Megalo variant / mode 2 / a valid session parameter shows
//! up with no mod loaded, the retail path drives it and it is an MSRC matter.
//!
//!   cargo run -p blam-live --example variant_param_probe
//!   cargo run -p blam-live --example variant_param_probe -- 0x6340   # override member
//!
//! RVAs and offsets are CU4 (HaloSimulation_tag_release.dll).
use blam_live::gamestate::GameState;
use blam_live::tagtable::{Memory, TAG_DLL};
use blam_live::Process;
use std::thread::sleep;
use std::time::Duration;

/// Session object pointer and its valid flag (sim RVAs; `DAT_180ca34xx`).
const SESSION_PTR: u64 = 0xca3480;
const SESSION_VALID: u64 = 0xca3420;

/// Default session offset of the game-variant parameter (static-analysis hint;
/// override with argv[1]). Tried both as an embedded object and as a pointer.
const DEFAULT_MEMBER: u64 = 0x6340;

/// Offsets inside the game-variant parameter object, from `0x51d1b0`/`0x51d550`:
/// the received 0x5000 bitstream buffer, the reassembled size and chunk count,
/// the last received chunk index, and the decoded-variant copy.
const PARM_BUFFER: u64 = 0x1f8e8;
const PARM_SIZE: u64 = 0x248e8;
const PARM_COUNT: u64 = 0x248f0;
const PARM_LAST: u64 = 0x1f8e0;
const PARM_DECODED: u64 = 0x88;
/// Megalo variant object: the decoder stores the encoding version here.
const VARIANT_ENCVER: u64 = 0x5dc0;

fn u8_at(m: &Process, addr: u64) -> Option<u8> {
    m.read(addr, 1).ok().map(|b| b[0])
}

fn engine_name(i: u32) -> &'static str {
    match i {
        0 => "menu/none",
        1 => "sandbox",
        2 => "MEGALO",
        3 => "campaign",
        4 => "firefight",
        _ => "?",
    }
}

fn mode_name(m: u8) -> &'static str {
    match m {
        1 => "campaign",
        2 => "MULTIPLAYER",
        3 => "frontend",
        _ => "?",
    }
}

/// One attempt at reading the game-variant parameter at base `b`. `Some` only
/// when the fields validate as a real received variant.
struct Parm {
    base: u64,
    size: u32,
    count: u32,
    last: i32,
    raw_ver: u32,
    decoded_ver: u32,
}

fn try_parm(m: &Process, b: u64) -> Option<Parm> {
    let size = m.u32(b + PARM_SIZE).ok()?;
    let count = m.u32(b + PARM_COUNT).ok()?;
    let head = m.read(b + PARM_BUFFER, 4).ok()?;
    // The raw received bitstream is MSB-first, so the encoding version u32 reads
    // big-endian; the decoded copy stores it as a normal little-endian int.
    let raw_ver = u32::from_be_bytes(head[..4].try_into().ok()?);
    let decoded_ver = m.u32(b + PARM_DECODED + VARIANT_ENCVER).unwrap_or(0);
    let plausible = (1..=0x5000).contains(&size)
        && (1..=40).contains(&count)
        && (matches!(raw_ver, 0x6a | 0x6b) || matches!(decoded_ver, 0x6a | 0x6b));
    plausible.then(|| Parm {
        base: b,
        size,
        count,
        last: m.u32(b + PARM_LAST).map(|v| v as i32).unwrap_or(-1),
        raw_ver,
        decoded_ver,
    })
}

/// Look for the game-variant parameter: member as an embedded object, member as
/// a pointer, both for the two candidate members (current + pending).
fn find_parm(m: &Process, sess: u64, member: u64) -> Option<Parm> {
    let ptr = |o: u64| {
        m.u64(sess + o)
            .ok()
            .filter(|p| (0x1_0000..0x8000_0000_0000).contains(p))
    };
    [Some(sess + member), ptr(member), ptr(member + 8)]
        .into_iter()
        .flatten()
        .find_map(|b| try_parm(m, b))
}

/// Offset-independent fallback: read the session object and scan it for a
/// received-variant buffer. The raw bitstream begins with the encoding version
/// as an MSB-first u32, so the buffer's first four bytes read big-endian as
/// 0x6a/0x6b; the reassembled size and chunk count sit a fixed distance ahead.
/// Returns the first base whose fields validate, so a `None` after this means
/// no parameter is populated anywhere in the session (not just a wrong offset).
fn scan_session(m: &Process, sess: u64) -> (Option<Parm>, usize, usize) {
    let blob = match m.read(sess, 0x60000) {
        Ok(b) => b,
        Err(_) => return (None, 0, 0),
    };
    let le = |o: usize| u32::from_le_bytes(blob[o..o + 4].try_into().unwrap());
    let be = |o: usize| u32::from_be_bytes(blob[o..o + 4].try_into().unwrap());
    let (mut markers, mut strong) = (0usize, None);
    let mut p = 0usize;
    while p + 4 <= blob.len() {
        let v = be(p);
        if (v == 0x6a || v == 0x6b) && p >= PARM_BUFFER as usize {
            markers += 1;
            let b = p - PARM_BUFFER as usize;
            if strong.is_none() && b + PARM_COUNT as usize + 4 <= blob.len() {
                let size = le(b + PARM_SIZE as usize);
                let count = le(b + PARM_COUNT as usize);
                if (1..=0x5000).contains(&size) && (1..=40).contains(&count) {
                    strong = Some(Parm {
                        base: sess + b as u64,
                        size,
                        count,
                        last: le(b + PARM_LAST as usize) as i32,
                        raw_ver: v,
                        decoded_ver: le(b + PARM_DECODED as usize + VARIANT_ENCVER as usize),
                    });
                }
            }
        }
        p += 8;
    }
    (strong, markers, blob.len())
}

fn main() {
    // Args: `--once` samples a single snapshot and exits (for a one-shot run
    // through the two-PC agent's /input slot); a bare hex token overrides the
    // session member offset.
    let mut once = false;
    let mut member = DEFAULT_MEMBER;
    for a in std::env::args().skip(1) {
        if a == "--once" {
            once = true;
        } else if let Ok(m) = u64::from_str_radix(a.trim_start_matches("0x"), 16) {
            member = m;
        }
    }

    let process = Process::attach().expect("the game is not running");
    let base = process
        .module_info(TAG_DLL)
        .expect("simulation DLL not loaded")
        .base;
    let gs = GameState::attach(&process).expect("no simulation game state");
    println!(
        "read-only variant-reachability probe — sim thread {} block {:#x}, module {:#x}",
        gs.tid, gs.block, base
    );
    if !once {
        println!("watching ENGINE / MODE / VARIANT / SESSION once a second; Ctrl-C to stop.");
        println!("(run on the JOINER, unmodified retail co-op, MJOLNIR not loaded)\n");
    }

    let mut last_line = String::new();
    let mut ticks: u64 = 0;
    loop {
        // ENGINE
        let engine = process
            .u64(gs.block + 0x38)
            .ok()
            .filter(|p| *p != 0)
            .and_then(|gg| process.u32(gg + 0x846c).ok());
        // MODE + live VARIANT
        let opt = process.u64(gs.block + 0x60).ok().filter(|p| *p != 0);
        let mode = opt.and_then(|o| u8_at(&process, o + 0x10));
        let vtype = opt.and_then(|o| process.u16(o + 0x15f0).ok());
        let vencver = match (opt, vtype) {
            (Some(o), Some(2)) => process.u32(o + 0x15f4 + VARIANT_ENCVER).ok(),
            _ => None,
        };
        // SESSION + its game-variant parameter
        let sess = (u8_at(&process, base + SESSION_VALID) == Some(1))
            .then(|| process.u64(base + SESSION_PTR).ok())
            .flatten()
            .filter(|p| *p != 0);
        let (parm, scan_note) = match sess {
            Some(s) => match find_parm(&process, s, member) {
                Some(p) => (Some(p), String::new()),
                None => {
                    let (p, markers, scanned) = scan_session(&process, s);
                    (p, format!(" (scanned {scanned:#x}, {markers} markers)"))
                }
            },
            None => (None, String::new()),
        };

        let line = format!(
            "ENGINE {:<10} MODE {:<12} VARIANT {} SESSION {} PARAM {}",
            engine.map(|e| format!("{e} {}", engine_name(e))).unwrap_or_else(|| "–".into()),
            mode.map(|m| format!("{m} {}", mode_name(m))).unwrap_or_else(|| "–".into()),
            match (vtype, vencver) {
                (Some(2), Some(v)) => format!("type 2 MEGALO, encver {v:#x} (DECODED)"),
                (Some(t), _) => format!("type {t}"),
                (None, _) => "–".into(),
            },
            match sess {
                Some(s) => format!("{s:#x}"),
                None => "none".into(),
            },
            match &parm {
                Some(p) => format!(
                    "FOUND @ {:#x}: size {:#x} chunks {} last {} raw_ver {:#x} decoded_ver {:#x} <-- networked variant present",
                    p.base, p.size, p.count, p.last, p.raw_ver, p.decoded_ver
                ),
                None => format!("none{scan_note}"),
            },
        );

        if once {
            println!("{line}");
            return;
        }
        if line != last_line {
            println!("[{ticks:>5}s] CHANGED  {line}");
            last_line = line;
        } else if ticks % 15 == 0 {
            println!("[{ticks:>5}s]          {line}");
        }
        ticks += 1;
        sleep(Duration::from_secs(1));
    }
}
