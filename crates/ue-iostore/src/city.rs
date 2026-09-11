//! CityHash64 and the `FPackageId` derivation built on it.
//!
//! UE5 names a package's chunks by `FPackageId::FromName`: CityHash64 over the
//! package name lower-cased and widened to UTF-16LE. This is the piece that
//! turns "/Game/Levels/.../proving_ground-scenario" into the 8-byte id a chunk
//! carries, and therefore the piece that lets a container introduce a package
//! the game has never shipped.
//!
//! The CityHash64 here is a faithful port of Google's city.cc (v1.1, the
//! variant UE vendors). Its correctness gate is not a handful of test vectors
//! but the shipped game itself: `mjolnir container idcheck` derives the id of
//! every indexed package in all 28 shipped TOCs and requires an exact match.

#[inline]
fn fetch64(s: &[u8], i: usize) -> u64 {
    u64::from_le_bytes(s[i..i + 8].try_into().unwrap())
}

#[inline]
fn fetch32(s: &[u8], i: usize) -> u64 {
    u32::from_le_bytes(s[i..i + 4].try_into().unwrap()) as u64
}

#[inline]
fn rotate(v: u64, shift: u32) -> u64 {
    v.rotate_right(shift)
}

#[inline]
fn shift_mix(v: u64) -> u64 {
    v ^ (v >> 47)
}

const K0: u64 = 0xc3a5_c85c_97cb_3127;
const K1: u64 = 0xb492_b66f_be98_f273;
const K2: u64 = 0x9ae1_6a3b_2f90_404f;
const K_MUL: u64 = 0x9ddf_ea08_eb38_2d69;

#[inline]
fn hash_len_16_mul(u: u64, v: u64, mul: u64) -> u64 {
    let mut a = (u ^ v).wrapping_mul(mul);
    a ^= a >> 47;
    let mut b = (v ^ a).wrapping_mul(mul);
    b ^= b >> 47;
    b.wrapping_mul(mul)
}

#[inline]
fn hash_len_16(u: u64, v: u64) -> u64 {
    hash_len_16_mul(u, v, K_MUL)
}

fn hash_len_0_to_16(s: &[u8]) -> u64 {
    let len = s.len();
    if len >= 8 {
        let mul = K2.wrapping_add(len as u64 * 2);
        let a = fetch64(s, 0).wrapping_add(K2);
        let b = fetch64(s, len - 8);
        let c = rotate(b, 37).wrapping_mul(mul).wrapping_add(a);
        let d = rotate(a, 25).wrapping_add(b).wrapping_mul(mul);
        return hash_len_16_mul(c, d, mul);
    }
    if len >= 4 {
        let mul = K2.wrapping_add(len as u64 * 2);
        let a = fetch32(s, 0);
        return hash_len_16_mul(
            (len as u64).wrapping_add(a << 3),
            fetch32(s, len - 4),
            mul,
        );
    }
    if len > 0 {
        let a = s[0] as u64;
        let b = s[len >> 1] as u64;
        let c = s[len - 1] as u64;
        let y = a.wrapping_add(b << 8);
        let z = (len as u64).wrapping_add(c << 2);
        return shift_mix(y.wrapping_mul(K2) ^ z.wrapping_mul(K0)).wrapping_mul(K2);
    }
    K2
}

fn hash_len_17_to_32(s: &[u8]) -> u64 {
    let len = s.len();
    let mul = K2.wrapping_add(len as u64 * 2);
    let a = fetch64(s, 0).wrapping_mul(K1);
    let b = fetch64(s, 8);
    let c = fetch64(s, len - 8).wrapping_mul(mul);
    let d = fetch64(s, len - 16).wrapping_mul(K2);
    hash_len_16_mul(
        rotate(a.wrapping_add(b), 43)
            .wrapping_add(rotate(c, 30))
            .wrapping_add(d),
        a.wrapping_add(rotate(b.wrapping_add(K2), 18)).wrapping_add(c),
        mul,
    )
}

fn hash_len_33_to_64(s: &[u8]) -> u64 {
    let len = s.len();
    let mul = K2.wrapping_add(len as u64 * 2);
    let mut a = fetch64(s, 0).wrapping_mul(K2);
    let mut b = fetch64(s, 8);
    let c = fetch64(s, len - 24);
    let d = fetch64(s, len - 32);
    let e = fetch64(s, 16).wrapping_mul(K2);
    let f = fetch64(s, 24).wrapping_mul(9);
    let g = fetch64(s, len - 8);
    let h = fetch64(s, len - 16).wrapping_mul(mul);

    let u = rotate(a.wrapping_add(g), 43)
        .wrapping_add(rotate(b, 30).wrapping_add(c).wrapping_mul(9));
    let v = (a.wrapping_add(g) ^ d).wrapping_add(f).wrapping_add(1);
    let w = u64::swap_bytes(u.wrapping_add(v).wrapping_mul(mul)).wrapping_add(h);
    let x = rotate(e.wrapping_add(f), 42).wrapping_add(c);
    let y = u64::swap_bytes(v.wrapping_add(w).wrapping_mul(mul))
        .wrapping_add(g)
        .wrapping_mul(mul);
    let z = e.wrapping_add(f).wrapping_add(c);
    a = u64::swap_bytes(x.wrapping_add(z).wrapping_mul(mul).wrapping_add(y)).wrapping_add(b);
    b = shift_mix(
        z.wrapping_add(a)
            .wrapping_mul(mul)
            .wrapping_add(d)
            .wrapping_add(h),
    )
    .wrapping_mul(mul);
    b.wrapping_add(x)
}

fn weak_hash_len_32_with_seeds(s: &[u8], i: usize, a0: u64, b0: u64) -> (u64, u64) {
    let w = fetch64(s, i);
    let x = fetch64(s, i + 8);
    let y = fetch64(s, i + 16);
    let z = fetch64(s, i + 24);

    let mut a = a0.wrapping_add(w);
    let mut b = rotate(b0.wrapping_add(a).wrapping_add(z), 21);
    let c = a;
    a = a.wrapping_add(x);
    a = a.wrapping_add(y);
    b = b.wrapping_add(rotate(a, 44));
    (a.wrapping_add(z), b.wrapping_add(c))
}

/// CityHash64 (v1.1) over a byte string.
pub fn city_hash64(s: &[u8]) -> u64 {
    let len = s.len();
    if len <= 32 {
        return if len <= 16 {
            hash_len_0_to_16(s)
        } else {
            hash_len_17_to_32(s)
        };
    }
    if len <= 64 {
        return hash_len_33_to_64(s);
    }

    let mut x = fetch64(s, len - 40);
    let mut y = fetch64(s, len - 16).wrapping_add(fetch64(s, len - 56));
    let mut z = hash_len_16(
        fetch64(s, len - 48).wrapping_add(len as u64),
        fetch64(s, len - 24),
    );
    let mut v = weak_hash_len_32_with_seeds(s, len - 64, len as u64, z);
    let mut w = weak_hash_len_32_with_seeds(s, len - 32, y.wrapping_add(K1), x);
    x = x.wrapping_mul(K1).wrapping_add(fetch64(s, 0));

    let mut i = 0usize;
    let mut remaining = (len - 1) & !63usize;
    loop {
        x = rotate(
            x.wrapping_add(y)
                .wrapping_add(v.0)
                .wrapping_add(fetch64(s, i + 8)),
            37,
        )
        .wrapping_mul(K1);
        y = rotate(y.wrapping_add(v.1).wrapping_add(fetch64(s, i + 48)), 42).wrapping_mul(K1);
        x ^= w.1;
        y = y.wrapping_add(v.0).wrapping_add(fetch64(s, i + 40));
        z = rotate(z.wrapping_add(w.0), 33).wrapping_mul(K1);
        v = weak_hash_len_32_with_seeds(s, i, v.1.wrapping_mul(K1), x.wrapping_add(w.0));
        w = weak_hash_len_32_with_seeds(
            s,
            i + 32,
            z.wrapping_add(w.1),
            y.wrapping_add(fetch64(s, i + 16)),
        );
        std::mem::swap(&mut z, &mut x);
        i += 64;
        remaining -= 64;
        if remaining == 0 {
            break;
        }
    }
    hash_len_16(
        hash_len_16(v.0, w.0)
            .wrapping_add(shift_mix(y).wrapping_mul(K1))
            .wrapping_add(z),
        hash_len_16(v.1, w.1).wrapping_add(x),
    )
}

/// `FPackageId::FromName`: CityHash64 of the package name lower-cased, as
/// UTF-16LE bytes. The name is the object-path form, e.g.
/// `/Game/Levels/Halo1/Solo/B40/B40`.
pub fn package_id(name: &str) -> u64 {
    let lowered = name.to_lowercase();
    let mut wide = Vec::with_capacity(lowered.len() * 2);
    for unit in lowered.encode_utf16() {
        wide.extend_from_slice(&unit.to_le_bytes());
    }
    city_hash64(&wide)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Spot values from Google's city.cc test harness family are not vendored
    // here; the authoritative check is `mjolnir container idcheck`, which
    // derives every shipped package's id and requires equality. These tests
    // pin behaviours that do not depend on the constants being right.

    #[test]
    fn empty_input_is_k2() {
        assert_eq!(city_hash64(&[]), K2);
    }

    #[test]
    fn package_id_is_case_insensitive() {
        assert_eq!(
            package_id("/Game/Levels/Halo1/Solo/B40/B40"),
            package_id("/game/levels/halo1/solo/b40/b40")
        );
    }

    #[test]
    fn different_names_hash_differently() {
        assert_ne!(package_id("/Game/A"), package_id("/Game/B"));
    }
}
