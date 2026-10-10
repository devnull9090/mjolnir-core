// The CPU's single-precision steps on a GPU without f64 (gpu_exact_f64.wgsl
// has the exact ones): plain f32, which the driver may fuse and approximate.

fn xadd(a: f32, b: f32) -> f32 {
    return a + b;
}

fn xsub(a: f32, b: f32) -> f32 {
    return a - b;
}

fn xmul(a: f32, b: f32) -> f32 {
    return a * b;
}

fn xdiv(a: f32, b: f32) -> f32 {
    return a / b;
}

fn xsqrt(a: f32) -> f32 {
    return sqrt(a);
}
