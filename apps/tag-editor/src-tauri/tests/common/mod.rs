//! Shared helpers for the live reverse-engineering probes: memory scans and
//! the ground-truth tables they all start from.
#![allow(dead_code)]

use std::collections::HashMap;

use tag_editor_lib::{catalog::Catalog, present};

pub fn u64_at(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}
pub fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// Every aligned 8-byte slot in writable memory whose value falls in one of
/// `ranges` (`[lo, hi)`, sorted, non-overlapping), as `(holder, value)`.
pub fn range_scan(p: &blam_live::Process, ranges: &[(u64, u64)]) -> Vec<(u64, u64)> {
    let (min, max) = (ranges[0].0, ranges[ranges.len() - 1].1);
    let starts: Vec<u64> = ranges.iter().map(|r| r.0).collect();
    let mut out = Vec::new();
    let mut window = vec![0u8; 64 * 1024 * 1024];
    for region in p.writable_regions().expect("regions") {
        let mut at = 0u64;
        while at < region.size {
            let want = (window.len() as u64).min(region.size - at) as usize;
            if let Ok(got) = p.read_into(region.base + at, &mut window[..want]) {
                for off in (0..got.saturating_sub(7)).step_by(8) {
                    let v = u64_at(&window, off);
                    if v < min || v >= max {
                        continue;
                    }
                    let i = match starts.binary_search(&v) {
                        Ok(i) => i,
                        Err(0) => continue,
                        Err(i) => i - 1,
                    };
                    if v < ranges[i].1 {
                        out.push((region.base + at + off as u64, v));
                    }
                }
            }
            at += window.len() as u64;
        }
    }
    out.sort_unstable();
    out
}

pub fn exact_ranges(addrs: &[u64]) -> Vec<(u64, u64)> {
    let mut v: Vec<(u64, u64)> = addrs.iter().map(|a| (*a, *a + 8)).collect();
    v.sort_unstable();
    v.dedup();
    v
}

/// The census's verdict: buffer base -> catalog index, plus `(r0, r1)`.
pub fn load_resident() -> HashMap<u64, (usize, usize, usize)> {
    let path = std::env::var("MJOLNIR_RESIDENT").expect("set MJOLNIR_RESIDENT");
    let rows: Vec<serde_json::Value> =
        serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    rows.iter()
        .map(|r| {
            (
                u64::from_str_radix(r["base"].as_str().unwrap().trim_start_matches("0x"), 16)
                    .unwrap(),
                (
                    r["index"].as_u64().unwrap() as usize,
                    r["r0"].as_u64().unwrap() as usize,
                    r["r1"].as_u64().unwrap() as usize,
                ),
            )
        })
        .collect()
}

/// A tag's identity as the engine holds it: its `UObject`, the object's and
/// its package's `FName` ids, and its class pointer.
#[derive(Clone, Copy, Debug)]
pub struct TagObject {
    pub uobject: u64,
    pub name_id: u32,
    pub package_name_id: u32,
    pub class: u64,
}

/// Every tag asset with a live object, by catalog index.
pub fn tag_objects(
    p: &blam_live::Process,
    catalog: &Catalog,
) -> HashMap<usize, TagObject> {
    let (reader, _) = present::attach(p, catalog.paks(), None).expect("reader");
    let objects = reader.table.walk(p).expect("walk");
    let mut class_is_tag: HashMap<u64, bool> = HashMap::new();
    let mut out = HashMap::new();
    for o in &objects {
        let is_tag = *class_is_tag.entry(o.class).or_insert_with(|| {
            reader
                .name_at(p, o.class)
                .map(|n| n.ends_with("TagDataAsset"))
                .unwrap_or(false)
        });
        if !is_tag {
            continue;
        }
        let Ok((name, pkg)) = reader.identity(p, o) else { continue };
        if name.starts_with("Default__") || !pkg.starts_with("/Game/Tags/") {
            continue;
        }
        let Some(idx) = catalog.tag_by_package(&pkg) else { continue };
        let package_name_id = if o.outer != 0 {
            p.read(o.outer + 0x18, 4).map(|b| u32_at(&b, 0)).unwrap_or(0)
        } else {
            0
        };
        out.insert(
            idx,
            TagObject {
                uobject: o.object,
                name_id: o.name_id,
                package_name_id,
                class: o.class,
            },
        );
    }
    out
}

/// The 32-byte buffer descriptors `{ptr; u32; u32=1; u64=0; ...}` that hold a
/// resident buffer base, as `(descriptor addr, catalog index)`.
pub fn descriptors(
    p: &blam_live::Process,
    resident: &HashMap<u64, (usize, usize, usize)>,
) -> Vec<(u64, usize)> {
    let bases: Vec<u64> = resident.keys().copied().collect();
    let mut out = Vec::new();
    for (a, v) in range_scan(p, &exact_ranges(&bases)) {
        if a % 32 != 0 {
            continue;
        }
        let Ok(r) = p.read(a, 32) else { continue };
        if u32_at(&r, 12) == 1 && u64_at(&r, 16) == 0 {
            out.push((a, resident[&v].0));
        }
    }
    out
}

/// Pages (1 MB) holding at least `min` of the given addresses.
pub fn dense_pages(addrs: &[u64], min: usize) -> std::collections::HashSet<u64> {
    let mut by_page: HashMap<u64, usize> = HashMap::new();
    for a in addrs {
        *by_page.entry(a >> 20).or_default() += 1;
    }
    by_page
        .into_iter()
        .filter(|(_, n)| *n >= min)
        .map(|(pg, _)| pg)
        .collect()
}

/// The scan-derived targets every top-down probe needs, cached per game
/// session so later probes skip two full memory scans (~3 minutes).
#[derive(serde::Serialize, serde::Deserialize, Clone)]
pub struct Targets {
    pub pid: u32,
    /// (descriptor address, catalog index)
    pub descriptors: Vec<(u64, usize)>,
    /// slots holding a descriptor pointer
    pub slots: Vec<u64>,
    /// buffer bases (payload byte 0)
    pub bases: Vec<u64>,
}

/// Load the cached targets for this pid, or compute and cache them. The
/// cache lives beside the census dump as `<dump>.targets.json`.
pub fn targets(p: &blam_live::Process) -> Targets {
    let dump = std::env::var("MJOLNIR_RESIDENT").expect("set MJOLNIR_RESIDENT");
    let cache = format!("{dump}.targets.json");
    if let Ok(text) = std::fs::read_to_string(&cache) {
        if let Ok(t) = serde_json::from_str::<Targets>(&text) {
            if t.pid == p.pid {
                eprintln!("targets: cached ({} descriptors, {} slots)", t.descriptors.len(), t.slots.len());
                return t;
            }
        }
    }
    let resident = load_resident();
    let descriptors = self::descriptors(p, &resident);
    let desc_addrs: Vec<u64> = descriptors.iter().map(|(a, _)| *a).collect();
    let slots: Vec<u64> = range_scan(p, &exact_ranges(&desc_addrs))
        .into_iter()
        .map(|(h, _)| h)
        .collect();
    let t = Targets {
        pid: p.pid,
        descriptors,
        slots,
        bases: resident.keys().copied().collect(),
    };
    let _ = std::fs::write(&cache, serde_json::to_string(&t).unwrap());
    eprintln!("targets: computed and cached ({} descriptors, {} slots)", t.descriptors.len(), t.slots.len());
    t
}

// --- CityHash64, as Unreal vendors it (city.cc). `FPackageId` is CityHash64
// over the lowercase UTF-16LE bytes of the package name — the key the tag
// cache's nodes carry. Port checked against the live cache: 35 node hashes
// matched their tags' computed ids bit for bit.

const K0: u64 = 0xc3a5c85c97cb3127;
const K1: u64 = 0xb492b66fbe98f273;
const K2: u64 = 0x9ae16a3b2f90404f;

fn fetch64(b: &[u8], i: usize) -> u64 {
    u64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn fetch32(b: &[u8], i: usize) -> u64 {
    u32::from_le_bytes(b[i..i + 4].try_into().unwrap()) as u64
}
fn rotate(v: u64, s: u32) -> u64 {
    if s == 0 { v } else { v.rotate_right(s) }
}
fn shift_mix(v: u64) -> u64 {
    v ^ (v >> 47)
}
fn hash128to64(u: u64, v: u64) -> u64 {
    hash_len16_mul(u, v, 0x9ddfea08eb382d69)
}
fn hash_len16_mul(u: u64, v: u64, mul: u64) -> u64 {
    let mut a = (u ^ v).wrapping_mul(mul);
    a ^= a >> 47;
    let mut b = (v ^ a).wrapping_mul(mul);
    b ^= b >> 47;
    b.wrapping_mul(mul)
}
fn hash_len0to16(s: &[u8]) -> u64 {
    let len = s.len();
    if len >= 8 {
        let mul = K2.wrapping_add((len as u64) * 2);
        let a = fetch64(s, 0).wrapping_add(K2);
        let b = fetch64(s, len - 8);
        let c = rotate(b, 37).wrapping_mul(mul).wrapping_add(a);
        let d = rotate(a, 25).wrapping_add(b).wrapping_mul(mul);
        return hash_len16_mul(c, d, mul);
    }
    if len >= 4 {
        let mul = K2.wrapping_add((len as u64) * 2);
        let a = fetch32(s, 0);
        return hash_len16_mul((len as u64).wrapping_add(a << 3), fetch32(s, len - 4), mul);
    }
    if len > 0 {
        let a = s[0] as u64;
        let b = s[len >> 1] as u64;
        let c = s[len - 1] as u64;
        let y = (a.wrapping_add(b << 8)) as u32 as u64;
        let z = ((len as u64).wrapping_add(c << 2)) as u32 as u64;
        return shift_mix(y.wrapping_mul(K2) ^ z.wrapping_mul(K0)).wrapping_mul(K2);
    }
    K2
}
fn hash_len17to32(s: &[u8]) -> u64 {
    let len = s.len();
    let mul = K2.wrapping_add((len as u64) * 2);
    let a = fetch64(s, 0).wrapping_mul(K1);
    let b = fetch64(s, 8);
    let c = fetch64(s, len - 8).wrapping_mul(mul);
    let d = fetch64(s, len - 16).wrapping_mul(K2);
    hash_len16_mul(
        rotate(a.wrapping_add(b), 43).wrapping_add(rotate(c, 30)).wrapping_add(d),
        a.wrapping_add(rotate(b.wrapping_add(K2), 18)).wrapping_add(c),
        mul,
    )
}
fn hash_len33to64(s: &[u8]) -> u64 {
    let len = s.len();
    let mul = K2.wrapping_add((len as u64) * 2);
    let a = fetch64(s, 0).wrapping_mul(K2);
    let b = fetch64(s, 8);
    let c = fetch64(s, len - 8).wrapping_mul(mul);
    let d = fetch64(s, len - 16).wrapping_mul(K2);
    let y = rotate(a.wrapping_add(b), 43).wrapping_add(rotate(c, 30)).wrapping_add(d);
    let z = hash_len16_mul(y, a.wrapping_add(rotate(b.wrapping_add(K2), 18)).wrapping_add(c), mul);
    let e = fetch64(s, 16).wrapping_mul(mul);
    let f = fetch64(s, 24);
    let g = y.wrapping_add(fetch64(s, len - 32)).wrapping_mul(mul);
    let h = z.wrapping_add(fetch64(s, len - 24)).wrapping_mul(mul);
    hash_len16_mul(
        rotate(e.wrapping_add(f), 43).wrapping_add(rotate(g, 30)).wrapping_add(h),
        e.wrapping_add(rotate(f.wrapping_add(a), 18)).wrapping_add(g),
        mul,
    )
}
fn weak_hash_len32_with_seeds_words(w: u64, x: u64, y: u64, z: u64, a: u64, b: u64) -> (u64, u64) {
    let a = a.wrapping_add(w);
    let b = rotate(b.wrapping_add(a).wrapping_add(z), 21);
    let c = a;
    let a = a.wrapping_add(x).wrapping_add(y);
    let b = b.wrapping_add(rotate(a, 44));
    (a.wrapping_add(z), b.wrapping_add(c))
}
fn weak_hash_len32_with_seeds(s: &[u8], i: usize, a: u64, b: u64) -> (u64, u64) {
    weak_hash_len32_with_seeds_words(
        fetch64(s, i), fetch64(s, i + 8), fetch64(s, i + 16), fetch64(s, i + 24), a, b,
    )
}

/// CityHash64 of a byte string.
pub fn cityhash64(s: &[u8]) -> u64 {
    let len = s.len();
    if len <= 16 {
        return hash_len0to16(s);
    }
    if len <= 32 {
        return hash_len17to32(s);
    }
    if len <= 64 {
        return hash_len33to64(s);
    }
    let mut x = fetch64(s, len - 40);
    let mut y = fetch64(s, len - 16).wrapping_add(fetch64(s, len - 56));
    let mut z = hash128to64(fetch64(s, len - 48).wrapping_add(len as u64), fetch64(s, len - 24));
    let mut v = weak_hash_len32_with_seeds(s, len - 64, len as u64, z);
    let mut w = weak_hash_len32_with_seeds(s, len - 32, y.wrapping_add(K1), x);
    x = x.wrapping_mul(K1).wrapping_add(fetch64(s, 0));
    let mut n = (len - 1) & !63;
    let mut i = 0usize;
    loop {
        x = rotate(x.wrapping_add(y).wrapping_add(v.0).wrapping_add(fetch64(s, i + 8)), 37).wrapping_mul(K1);
        y = rotate(y.wrapping_add(v.1).wrapping_add(fetch64(s, i + 48)), 42).wrapping_mul(K1);
        x ^= w.1;
        y = y.wrapping_add(v.0).wrapping_add(fetch64(s, i + 40));
        z = rotate(z.wrapping_add(w.0), 33).wrapping_mul(K1);
        v = weak_hash_len32_with_seeds(s, i, v.1.wrapping_mul(K1), x.wrapping_add(w.0));
        w = weak_hash_len32_with_seeds(s, i + 32, z.wrapping_add(w.1), y.wrapping_add(fetch64(s, i + 16)));
        std::mem::swap(&mut z, &mut x);
        i += 64;
        n -= 64;
        if n == 0 {
            break;
        }
    }
    hash128to64(
        hash128to64(v.0, w.0).wrapping_add(shift_mix(y).wrapping_mul(K1)).wrapping_add(z),
        hash128to64(v.1, w.1).wrapping_add(x),
    )
}

/// A cooked tag's `FPackageId`: CityHash64 of the lowercase UTF-16LE package
/// name `/Game/Tags/<short>-<group>`.
pub fn package_id(short: &str, group: &str) -> u64 {
    let pkg = format!("/Game/Tags/{short}-{group}").to_lowercase();
    let bytes: Vec<u8> = pkg.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
    cityhash64(&bytes)
}
