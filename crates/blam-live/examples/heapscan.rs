//! Find resident block fields in the running game by their element counts.
//! A block field is 12 bytes `{count, data ref, struct ref}`; on disk the refs
//! are zero and the loader fills them. Given the counts of consecutive blocks
//! in one struct (e.g. a definition's collision tables), this scans every
//! writable region for the first count and reports each place where the rest
//! follow within a short distance, printing the two ref words of every match.
//! Repeats until the game process is gone, so a crashing load still leaves its
//! last scan on disk.
//!
//!   cargo run -p blam-live --example heapscan -- <out file> <label:c0,c1,c2,...> ...
use blam_live::Process;
use std::io::Write;
use std::time::{Duration, Instant};

fn main() {
    let mut a = std::env::args().skip(1);
    let out = a.next().expect("out file");
    let groups: Vec<(String, Vec<u32>)> = a
        .map(|s| {
            let (l, c) = s.split_once(':').expect("label:counts");
            (l.to_string(), c.split(',').map(|x| x.parse().unwrap()).collect())
        })
        .collect();
    let process = loop {
        if let Ok(p) = Process::attach() {
            break p;
        }
        std::thread::sleep(Duration::from_millis(500));
    };
    println!("attached pid {}", process.pid);
    let t0 = Instant::now();
    let mut pass = 0;
    loop {
        let regions = match process.writable_regions() {
            Ok(r) => r,
            Err(_) => break,
        };
        let mut report = String::new();
        let mut hits = 0;
        let mut scanned = 0u64;
        for r in &regions {
            if r.size < 0x10000 || r.size > 0x2_0000_0000 {
                continue;
            }
            // Read in 16 MB chunks with a 4 KB overlap.
            let mut off = 0u64;
            while off < r.size {
                let len = (r.size - off).min(16 << 20) as usize;
                let Ok(buf) = process.read(r.base + off, len) else { break };
                scanned += len as u64;
                for (label, counts) in &groups {
                    let c0 = counts[0].to_le_bytes();
                    let mut i = 0usize;
                    while i + 12 <= buf.len() {
                        if buf[i..i + 4] == c0 {
                            // The next counts must follow, each within 64 bytes of the previous field.
                            let mut pos = i;
                            let mut fields = vec![pos];
                            let mut ok = true;
                            for c in &counts[1..] {
                                let cb = c.to_le_bytes();
                                let mut found = None;
                                let mut p = pos + 12;
                                while p + 12 <= buf.len() && p <= pos + 64 {
                                    if buf[p..p + 4] == cb {
                                        found = Some(p);
                                        break;
                                    }
                                    p += 4;
                                }
                                match found {
                                    Some(p) => {
                                        fields.push(p);
                                        pos = p;
                                    }
                                    None => {
                                        ok = false;
                                        break;
                                    }
                                }
                            }
                            if ok {
                                hits += 1;
                                let addr = r.base + off + i as u64;
                                let words: Vec<String> = fields
                                    .iter()
                                    .map(|&p| {
                                        let w1 = u32::from_le_bytes(buf[p + 4..p + 8].try_into().unwrap());
                                        let w2 = u32::from_le_bytes(buf[p + 8..p + 12].try_into().unwrap());
                                        format!("{{{},{w1:#x},{w2:#x}}}", u32::from_le_bytes(buf[p..p + 4].try_into().unwrap()))
                                    })
                                    .collect();
                                report.push_str(&format!("{label} @{addr:#x}: {}\n", words.join(" ")));
                            }
                        }
                        i += 4;
                    }
                }
                off += len as u64 - 4096;
                if len < 16 << 20 {
                    break;
                }
            }
        }
        pass += 1;
        let line = format!("[{:>6.1}s] pass {pass}: {} regions, {:.0} MB scanned, {hits} hits", t0.elapsed().as_secs_f32(), regions.len(), scanned as f64 / 1e6);
        println!("{line}");
        let mut f = std::fs::File::create(&out).unwrap();
        writeln!(f, "{line}\n{report}").unwrap();
        if Process::attach().is_err() {
            println!("process gone");
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}
