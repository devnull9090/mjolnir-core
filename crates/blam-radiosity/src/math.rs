//! Three-vectors, as plain arrays: the solver's inner loops stay free of
//! any linear-algebra crate's conventions, and the GPU kernels take the
//! same layout.

pub type V3 = [f32; 3];

#[inline]
pub fn sub(a: V3, b: V3) -> V3 {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
#[inline]
pub fn add(a: V3, b: V3) -> V3 {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
#[inline]
pub fn mul(a: V3, s: f32) -> V3 {
    [a[0] * s, a[1] * s, a[2] * s]
}
#[inline]
pub fn dot(a: V3, b: V3) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
#[inline]
pub fn cross(a: V3, b: V3) -> V3 {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}
#[inline]
pub fn len(a: V3) -> f32 {
    dot(a, a).sqrt()
}
/// `a` normalised; straight up (glTF y) for a zero vector.
#[inline]
pub fn norm(a: V3) -> V3 {
    let l = len(a);
    if l > 1e-12 {
        mul(a, 1.0 / l)
    } else {
        [0.0, 1.0, 0.0]
    }
}
#[inline]
pub fn lerp(a: V3, b: V3, t: f32) -> V3 {
    add(mul(a, 1.0 - t), mul(b, t))
}

/// CE's luminance weights, which the solver uses to weight incident
/// directions (tool.exe: 0.299, 0.587, 0.114).
#[inline]
pub fn luma(c: V3) -> f32 {
    0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
}
