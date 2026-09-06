//! Phase 0 spike: pointer-chase the simulation's tag table instead of sweeping.
//!
//! Addresses are the CU4 (`2026.08.11.1121610.2`) RVAs into
//! `HaloSimulation_tag_release.dll`. Nothing here is product code; it exists to
//! measure whether the table walk finds what the census finds.
//!
//! Run with the game in a mission:
//!   cargo run -p blam-live --example tagtable_probe -- [--dump out.tsv] [--peek <substring>]

use blam_live::Process;
use std::fmt::Write as _;

const TAG_DLL: &str = "HaloSimulation_tag_release.dll";
const TAG_TABLE_PTR_RVA: u64 = 0x0182_D1E8;
const SEGMENT_TABLE_RVA: u64 = 0x02C2_CCC0;
const SID_STORAGE_RVA: u64 = 0x0135_7490;
const SID_USED_RVA: u64 = 0x0135_7498;
const SID_STRINGS_RVA: u64 = 0x0135_74A0;
const SID_COUNT_RVA: u64 = 0x0135_74A8;
const SID_MAP_RVA: u64 = 0x0135_74C0;
const SID_BUILTIN_RVA: u64 = 0x0082_F0A0;

fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes(b[o..o + 2].try_into().unwrap())
}
fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn u64_at(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}

fn read_u64(p: &Process, addr: u64) -> u64 {
    p.read(addr, 8).map(|b| u64_at(&b, 0)).unwrap_or(0)
}

fn read_cstr(p: &Process, addr: u64) -> String {
    match p.read(addr, 256) {
        Ok(b) => {
            let end = b.iter().position(|c| *c == 0).unwrap_or(b.len());
            String::from_utf8_lossy(&b[..end]).into_owned()
        }
        Err(_) => "<unreadable>".into(),
    }
}

fn fourcc(v: u32) -> String {
    v.to_be_bytes()
        .iter()
        .map(|c| {
            if c.is_ascii_graphic() {
                *c as char
            } else {
                '?'
            }
        })
        .collect()
}

fn hex(b: &[u8]) -> String {
    let mut s = String::new();
    for (i, x) in b.iter().enumerate() {
        if i > 0 && i % 4 == 0 {
            s.push(' ');
        }
        let _ = write!(s, "{x:02x}");
    }
    s
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let dump = args
        .iter()
        .position(|a| a == "--dump")
        .map(|i| args[i + 1].clone());
    let peek = args
        .iter()
        .position(|a| a == "--peek")
        .map(|i| args[i + 1].to_lowercase());

    let p = Process::attach()?;
    let (base, size) = p.module(TAG_DLL)?;
    println!("{TAG_DLL} base 0x{base:X} size 0x{size:X}");

    // --- segment table -------------------------------------------------------
    let seg = p.read(base + SEGMENT_TABLE_RVA, 16 * 8)?;
    let segs: Vec<u64> = (0..16).map(|i| u64_at(&seg, i * 8)).collect();
    for (i, s) in segs.iter().enumerate() {
        if *s != 0 {
            println!("segment[{i:2}] base 0x{s:X}");
        }
    }
    let resolve = |enc: u32| -> Option<(usize, u64)> {
        if enc == u32::MAX {
            return None;
        }
        let s = (enc >> 28) as usize;
        let b = segs[s];
        if b == 0 {
            return None;
        }
        Some((s, b + (enc as u64) * 4))
    };

    // --- tag table -----------------------------------------------------------
    let table = read_u64(&p, base + TAG_TABLE_PTR_RVA);
    println!("tag table object 0x{table:X}");
    if table == 0 {
        println!("tag table pointer is null (no mission loaded?)");
        return Ok(());
    }
    let hdr = p.read(table, 0x60)?;
    let elem = u32_at(&hdr, 0x20);
    let max = u32_at(&hdr, 0x2c);
    let high = u32_at(&hdr, 0x44);
    let used = u32_at(&hdr, 0x48);
    let entries = u64_at(&hdr, 0x50);
    let bits = u64_at(&hdr, 0x58);
    println!("elem 0x{elem:X} max {max} high_water {high} used {used} entries 0x{entries:X} bitset 0x{bits:X}");
    println!("header hex:\n  {}", hex(&hdr));
    if elem != 0x30 || max > 0x1_0000 || high > max {
        println!("!! layout invariants FAILED (measured layout is elem 0x30, max<=0x10000)");
        return Ok(());
    }
    let bitset = p.read(bits, (high as usize).div_ceil(8))?;
    let blob = p.read(entries, high as usize * 0x30)?;

    let mut out = String::new();
    let mut by_group: std::collections::BTreeMap<String, usize> = Default::default();
    let mut found = 0usize;
    let mut resolved = 0usize;
    let mut peeked = 0usize;
    for i in 0..high as usize {
        if bitset[i / 8] & (1 << (i % 8)) == 0 {
            continue;
        }
        let e = &blob[i * 0x30..(i + 1) * 0x30];
        let generation = u16_at(e, 0);
        let group = fourcc(u32_at(e, 4));
        let name_ptr = u64_at(e, 0x10);
        let count = u32_at(e, 0x18);
        let enc_data = u32_at(e, 0x1c);
        let enc_def = u32_at(e, 0x20);
        let name = read_cstr(&p, name_ptr);
        let handle = (generation as u32) << 16 | i as u32;
        let data = resolve(enc_data);
        let def = resolve(enc_def);
        found += 1;
        if data.is_some() {
            resolved += 1;
        }
        *by_group.entry(group.clone()).or_default() += 1;
        let _ = writeln!(
            out,
            "{i}\t0x{handle:08X}\t{group}\t{name}\t{count}\t{}\t{}\t{}",
            data.map(|(s, a)| format!("seg{s}:0x{a:X}"))
                .unwrap_or("-".into()),
            def.map(|(s, a)| format!("seg{s}:0x{a:X}"))
                .unwrap_or("-".into()),
            hex(&e[0x24..0x30]),
        );
        if let Some(pk) = &peek {
            if name.to_lowercase().contains(pk) && peeked < 4 {
                peeked += 1;
                println!("\n== {group} {name} handle 0x{handle:08X} root count {count}");
                if let Some((s, a)) = data {
                    let n = args
                        .iter()
                        .position(|a| a == "--peek-len")
                        .map(|i| args[i + 1].parse().unwrap())
                        .unwrap_or(96);
                    let b = p.read(a, n)?;
                    for (off, want) in [
                        (492usize, "flags"),
                        (496, "secondary flags"),
                        (584, "heat warning threshold"),
                    ] {
                        if b.len() >= off + 4 {
                            println!("   +{off:<4} {:<24} {}", want, hex(&b[off..off + 4]));
                        }
                    }
                    println!("   data  seg{s} 0x{a:X}:\n   {}", hex(&b));
                }
                if let Some((s, a)) = def {
                    let b = p.read(a, 64)?;
                    println!("   def   seg{s} 0x{a:X}:\n   {}", hex(&b));
                }
            }
        }
    }
    println!(
        "\n{found} live entries ({used} used per header), {resolved} with resolvable root data"
    );
    for (g, n) in &by_group {
        println!("  {g:4} {n}");
    }
    if let Some(path) = dump {
        std::fs::write(&path, out)?;
        println!("wrote {path}");
    }

    // --- string-id registry: raw globals first --------------------------------
    println!("\nstring-id globals:");
    for (n, rva) in [
        ("storage", SID_STORAGE_RVA),
        ("used", SID_USED_RVA),
        ("strings", SID_STRINGS_RVA),
        ("count", SID_COUNT_RVA),
        ("map", SID_MAP_RVA),
    ] {
        let b = p.read(base + rva, 8)?;
        println!(
            "  {n:8} @0x{rva:X}: u64 0x{:X}  u32 {}",
            u64_at(&b, 0),
            u32_at(&b, 0)
        );
    }
    let map = read_u64(&p, base + SID_MAP_RVA);
    if map != 0 {
        let h = p.read(map, 0x38)?;
        println!(
            "  map header: buckets {} max {} value_size {}  hex {}",
            u32_at(&h, 0),
            u32_at(&h, 4),
            u64_at(&h, 8),
            hex(&h)
        );
    }
    // --- string-id registry: walk every bucket chain -----------------------------
    if let Some(i) = args.iter().position(|a| a == "--sids") {
        let path = &args[i + 1];
        let strings = read_u64(&p, base + SID_STORAGE_RVA);
        let used = read_u64(&p, base + SID_USED_RVA) as usize;
        let ptrs = read_u64(&p, base + SID_STRINGS_RVA);
        println!(
            "  strings-table probe: first 4 pointers {:?}",
            (0..4)
                .map(|i| read_u64(&p, ptrs + i * 8))
                .map(|a| read_cstr(&p, a))
                .collect::<Vec<_>>()
        );
        let count = read_u64(&p, base + SID_COUNT_RVA) as usize;
        let blob = p.read(strings, used)?;
        let h = p.read(map, 0x38)?;
        let buckets = u32_at(&h, 0) as usize;
        let bucket_ptrs = p.read(map + 0x38, buckets * 8)?;
        let mut ids: Vec<(u64, String)> = Vec::new();
        let mut chains = 0usize;
        let mut longest = 0usize;
        for b in 0..buckets {
            let mut node = u64_at(&bucket_ptrs, b * 8);
            let mut len = 0usize;
            while node != 0 {
                let n = p.read(node, 0x1c)?;
                let key = u64_at(&n, 0);
                let next = u64_at(&n, 0x10);
                let off = u32_at(&n, 0x18) as usize;
                let name = if off < blob.len() {
                    let end = blob[off..]
                        .iter()
                        .position(|c| *c == 0)
                        .map(|e| off + e)
                        .unwrap_or(blob.len());
                    String::from_utf8_lossy(&blob[off..end]).into_owned()
                } else {
                    format!("<off 0x{off:X} beyond storage>")
                };
                ids.push((key, name));
                node = next;
                len += 1;
                if len > 100_000 {
                    println!("!! chain too long at bucket {b}");
                    break;
                }
            }
            if len > 0 {
                chains += 1;
                longest = longest.max(len);
            }
        }
        ids.sort();
        let mut out = String::new();
        for (k, n) in &ids {
            let _ = writeln!(out, "0x{k:08X}	{n}");
        }
        std::fs::write(path, out)?;
        println!("  registry: {} names in {chains} chains (longest {longest}); header count {count}; storage used {used} bytes; wrote {path}", ids.len());
        // Cross-check: entry i < 2678 has id builtin[i]; i >= 2678 has id 1068 + (i - 2678).
        let bt = p.read(base + SID_BUILTIN_RVA, 16 * 2678)?;
        let mut builtin_ok = 0usize;
        let mut builtin_bad = 0usize;
        let idset: std::collections::HashSet<u64> = ids.iter().map(|(k, _)| *k).collect();
        for i in 0..2678 {
            let id = u32_at(&bt, i * 16) as u64;
            if idset.contains(&id) {
                builtin_ok += 1
            } else {
                builtin_bad += 1
            }
        }
        println!("  builtin ids present in registry: {builtin_ok}, absent: {builtin_bad}");
        let max_seq = ids
            .iter()
            .map(|(k, _)| *k)
            .filter(|k| *k >= 1068)
            .max()
            .unwrap_or(0);
        println!(
            "  highest sequential id 0x{max_seq:X} = {max_seq}; expected 1068 + ({} - 2678) = {}",
            ids.len(),
            1068 + ids.len().saturating_sub(2678)
        );
    }
    let bt = p.read(base + SID_BUILTIN_RVA, 16 * 6)?;
    println!("  builtin table first 6 entries:");
    for i in 0..6 {
        let e = &bt[i * 16..(i + 1) * 16];
        let maybe_ptr = u64_at(e, 8);
        println!(
            "    id 0x{:08X} {} -> {}",
            u32_at(e, 0),
            hex(e),
            if maybe_ptr > 0x10000 {
                read_cstr(&p, maybe_ptr)
            } else {
                String::new()
            }
        );
    }
    Ok(())
}
