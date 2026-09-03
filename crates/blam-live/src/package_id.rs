//! `FPackageId`: how the engine names a cooked package, and therefore the key
//! its tag cache is indexed by.
//!
//! Unreal identifies a cooked package by CityHash64 over the lowercase
//! UTF-16LE bytes of its name. The live tag cache's nodes carry exactly that
//! value: 35 node hashes matched their tags' computed ids bit for bit, and
//! the port below resolved 8,591 catalog tags to a node
//! (`docs/live_tag_locating.md`). With it, a tag's runtime buffer is a pointer
//! chase from a static root — no memory sweep.
//!
//! The hash is a straight port of Google's `city.cc` as Unreal vendors it.

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input_is_the_k2_constant() {
        assert_eq!(cityhash64(b""), 0x9ae16a3b2f90404f);
    }

    #[test]
    fn package_id_matches_the_live_cache() {
        // Value computed by the Python implementation that identified the
        // key against the running game (35 live nodes matched).
        assert_eq!(package_id("ai/normal", "style"), 0x2fc1a2f8efc6ef72);
        // Case-insensitive by construction.
        assert_eq!(package_id("AI/Normal", "STYLE"), package_id("ai/normal", "style"));
    }
}
