// Single-precision arithmetic exactly as the CPU does it (gpu.wgsl's ray
// setup and solid test): each operation in f64, rounded back to f32. The
// product or sum of two f32 is exact in f64, so the rounding back is the
// correctly rounded f32 result, and no multiply can fuse into the next add.
// A ray grazing a wall starts a few ulps off its collision plane, where the
// GPU's own fused, approximate f32 put whole charts on the other side of the
// solid test (Gephyrophobia's sunvis, 2026-10-10).

fn xadd(a: f32, b: f32) -> f32 {
    return f32(f64(a) + f64(b));
}

fn xsub(a: f32, b: f32) -> f32 {
    return f32(f64(a) - f64(b));
}

fn xmul(a: f32, b: f32) -> f32 {
    return f32(f64(a) * f64(b));
}

fn xdiv(a: f32, b: f32) -> f32 {
    return f32(f64(a) / f64(b));
}

fn xsqrt(a: f32) -> f32 {
    return f32(sqrt(f64(a)));
}
