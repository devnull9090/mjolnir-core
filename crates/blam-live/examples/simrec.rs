//! Poll the simulation DLL's resident structure-BSP table and arena base table
//! while the game runs, and write a snapshot every time either changes. Keeps
//! going until the game process is gone, so the last snapshot of a crashing
//! load is the state just before the crash.
//!
//!   cargo run -p blam-live --example simrec -- <out dir> [records=24] [poll ms=100]
//!
//! Layout (HaloSimulation_tag_release.dll, CU4): arena bases at RVA 0x2c2ccc0
//! (16 x u64), resident BSP records at RVA 0x13d45a8 (0x490 bytes each). See
//! docs/re/collision_bsp/README.md.
use blam_live::{module_base, Process};
use std::io::Write;
use std::time::{Duration, Instant};

const DLL: &str = "HaloSimulation_tag_release.dll";
const ARENA_RVA: u64 = 0x2c2ccc0;
const ARENA_LEN: usize = 16 * 8;
const REC_RVA: u64 = 0x13d45a8;
const REC_LEN: usize = 0x490;

fn main() {
    let mut a = std::env::args().skip(1);
    let out = a.next().expect("out dir");
    let nrec: usize = a.next().map(|s| s.parse().unwrap()).unwrap_or(24);
    let poll = Duration::from_millis(a.next().map(|s| s.parse().unwrap()).unwrap_or(100));
    std::fs::create_dir_all(&out).unwrap();
    let mut log = std::fs::File::create(format!("{out}/simrec.log")).unwrap();
    macro_rules! say { ($($t:tt)*) => {{ let s = format!($($t)*); println!("{s}"); writeln!(log, "{s}").ok(); }} }

    // Wait for the game, then for the DLL.
    let process = loop {
        match Process::attach() {
            Ok(p) => break p,
            Err(_) => std::thread::sleep(Duration::from_millis(500)),
        }
    };
    say!("attached pid {}", process.pid);
    let (base, size) = loop {
        if let Some(b) = module_base(process.pid, DLL) {
            break b;
        }
        std::thread::sleep(Duration::from_millis(250));
    };
    say!("{DLL} base {base:#x} size {size:#x}");
    let t0 = Instant::now();
    let mut last: Option<(Vec<u8>, Vec<u8>)> = None;
    let mut seq = 0u32;
    let mut misses = 0;
    loop {
        let arena = process.read(base + ARENA_RVA, ARENA_LEN);
        let recs = process.read(base + REC_RVA, nrec * REC_LEN);
        let (arena, recs) = match (arena, recs) {
            (Ok(a), Ok(r)) => (a, r),
            _ => {
                misses += 1;
                if misses > 10 || Process::attach().is_err() {
                    say!("process gone after {:.1}s; {} snapshots", t0.elapsed().as_secs_f32(), seq);
                    return;
                }
                std::thread::sleep(poll);
                continue;
            }
        };
        misses = 0;
        let changed = match &last {
            None => true,
            Some((a, r)) => *a != arena || *r != recs,
        };
        if changed {
            let ms = t0.elapsed().as_millis();
            let mut f = std::fs::File::create(format!("{out}/snap_{seq:04}_{ms}.bin")).unwrap();
            f.write_all(&arena).unwrap();
            f.write_all(&recs).unwrap();
            let mut what = Vec::new();
            if let Some((a, r)) = &last {
                if *a != arena {
                    what.push("arena".to_string());
                }
                for i in 0..nrec {
                    let (x, y) = (&r[i * REC_LEN..(i + 1) * REC_LEN], &recs[i * REC_LEN..(i + 1) * REC_LEN]);
                    if x != y {
                        let lo = x.iter().zip(y).position(|(p, q)| p != q).unwrap();
                        let hi = REC_LEN - x.iter().rev().zip(y.iter().rev()).position(|(p, q)| p != q).unwrap();
                        what.push(format!("rec{i}[{lo:#x}..{hi:#x}]"));
                    }
                }
            } else {
                what.push("first".into());
            }
            let live: Vec<String> = (0..16)
                .filter_map(|i| {
                    let v = u64::from_le_bytes(arena[i * 8..i * 8 + 8].try_into().unwrap());
                    (v != 0).then(|| format!("{i}:{v:#x}"))
                })
                .collect();
            say!("[{ms:>7} ms] snap {seq:04}: {}  arenas {{{}}}", what.join(" "), live.join(" "));
            seq += 1;
            last = Some((arena, recs));
        }
        std::thread::sleep(poll);
    }
}
