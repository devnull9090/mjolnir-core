// The solver's two ray-bound loops on the GPU (`gpu.rs`): the receivers'
// gather from a batch of shooters, and the sky's direct light at a list of
// points (the per-texel pass). Both follow transport.rs line for line; the
// shadow rays are `Occluders::transmission` with the same collision BSP and
// glass tints. The walk along a ray, `trace`, comes from
// gpu_trace_bvh.wgsl (the CPU's tree, any GPU) or gpu_trace_rt.wgsl (the
// GPU's own ray tracing hardware), which gpu.rs puts in front of this.

struct Scene {
    tris: u32,
    // The collision BSP's nodes (0: no solid test).
    solid_nodes: u32,
    solid_planes: u32,
    pad: u32,
}

// The collision BSP: per node (plane, back child, front child).
@group(0) @binding(3) var<storage, read> solid_nodes: array<i32>;
@group(0) @binding(4) var<storage, read> solid_planes: array<vec4f>;
@group(0) @binding(5) var<uniform> scene: Scene;

const WU_TO_M: f32 = 3.048;
const PI: f32 = 3.14159265358979;

// collision.rs `in_solid`: a glTF point (metres) in the BSP's solid.
fn in_solid(p: vec3f) -> bool {
    let q = vec3f(p.x / WU_TO_M, -p.z / WU_TO_M, p.y / WU_TO_M);
    var node = 0i;
    for (var i = 0; i < 256; i++) {
        if (node == -1i) {
            return true;
        }
        if ((u32(node) & 0x80000000u) != 0u) {
            return false;
        }
        if (u32(node) >= scene.solid_nodes) {
            return false;
        }
        let plane = solid_nodes[3u * u32(node)];
        if (plane < 0i || u32(plane) >= scene.solid_planes) {
            return false;
        }
        let pl = solid_planes[u32(plane)];
        let d = pl.x * q.x + pl.y * q.y + pl.z * q.z - pl.w;
        node = select(solid_nodes[3u * u32(node) + 1u], solid_nodes[3u * u32(node) + 2u], d >= 0.0);
    }
    return false;
}

// transport.rs `Occluders::transmission`.
fn transmission(src: vec3f, dst: vec3f, end_in_level: bool) -> vec3f {
    let v = dst - src;
    let l = length(v);
    if (l <= 0.002) {
        return vec3f(1.0);
    }
    let d = v * (1.0 / l);
    let t0 = 0.001;
    let end = l - 0.001;
    if (scene.solid_nodes > 0u) {
        if (in_solid(src + d * t0) || (end_in_level && in_solid(src + d * end))) {
            return vec3f(0.0);
        }
    }
    return trace(src + d * t0, d, end - t0);
}

fn luma(c: vec3f) -> f32 {
    return 0.299 * c.x + 0.587 * c.y + 0.114 * c.z;
}

// ---- The gather -----------------------------------------------------------

struct Shooter {
    // Corners; v0.w = area / 3, v1.w = the plane's d, v2.w = r + g + b of
    // the unshot energy.
    v0: vec4f,
    v1: vec4f,
    v2: vec4f,
    // w = 1: the shader ignores normals.
    normal: vec4f,
    delta: vec4f,
}

struct Gather {
    targets: u32,
    shooters: u32,
    cull: f32,
    // The first target of this dispatch.
    offset: u32,
}

// Per vertex: position, normal (w unused).
@group(1) @binding(0) var<storage, read> verts: array<vec4f>;
@group(1) @binding(1) var<storage, read> targets: array<u32>;
@group(1) @binding(2) var<storage, read> shooters: array<Shooter>;
// Per target, six floats: the gain, the luminance-weighted incident
// direction.
@group(1) @binding(3) var<storage, read_write> gathered: array<f32>;
@group(1) @binding(4) var<uniform> gp: Gather;

// transport.rs `form_factor` and `Solver::shoot`'s inner loop.
@compute @workgroup_size(64)
fn gather(@builtin(workgroup_id) wg: vec3u, @builtin(num_workgroups) groups: vec3u, @builtin(local_invocation_index) lane: u32) {
    let i = (wg.y * groups.x + wg.x) * 64u + lane + gp.offset;
    if (i >= gp.targets) {
        return;
    }
    let vi = targets[i];
    let rp = verts[2u * vi].xyz;
    let rn = verts[2u * vi + 1u].xyz;
    var gain = vec3f(0.0);
    var dir = vec3f(0.0);
    let su = array<f32, 3>(1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0);
    let sv = array<f32, 3>(1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0);
    for (var s = 0u; s < gp.shooters; s++) {
        let sh = shooters[s];
        let n = sh.normal.xyz;
        if (dot(n, rp) - sh.v1.w <= 0.0) {
            continue;
        }
        let ignore = sh.normal.w != 0.0;
        let da = sh.v0.w;
        var f = vec3f(0.0);
        var fdir = vec3f(0.0);
        for (var k = 0u; k < 3u; k++) {
            let u = su[k];
            let w = sv[k];
            let q = sh.v0.xyz * (1.0 - u - w) + sh.v1.xyz * u + sh.v2.xyz * w;
            let v = q - rp;
            if (dot(v, rn) <= 0.0 && !ignore) {
                continue;
            }
            let r = length(v);
            if (r < 1e-4) {
                continue;
            }
            let d = v * (1.0 / r);
            let cos_r = select(dot(rn, d), 1.0, ignore);
            let cos_s = dot(n, -d);
            if (cos_s <= 0.0) {
                continue;
            }
            let fi = cos_s * da * cos_r / (PI * r * r + da);
            if (fi * sh.v2.w <= gp.cull) {
                continue;
            }
            let t = transmission(rp, q, true);
            if (all(t <= vec3f(0.0))) {
                continue;
            }
            f += t * fi;
            fdir = d;
        }
        f = clamp(f, vec3f(0.0), vec3f(1.0));
        if (all(f <= vec3f(0.0))) {
            continue;
        }
        let c = f * sh.delta.xyz;
        gain += c;
        dir += fdir * luma(c);
    }
    gathered[6u * i] = gain.x;
    gathered[6u * i + 1u] = gain.y;
    gathered[6u * i + 2u] = gain.z;
    gathered[6u * i + 3u] = dir.x;
    gathered[6u * i + 4u] = dir.y;
    gathered[6u * i + 5u] = dir.z;
}

// ---- The direct light -----------------------------------------------------

struct Directional {
    // Towards the light; w: its set (0 exterior, 1 interior).
    towards: vec4f,
    // w = 1: part of the sky's sun.
    colour: vec4f,
}

struct Placed {
    // w: reach in metres.
    pos: vec4f,
    // w = 1: a spot.
    colour: vec4f,
    // The spot's axis; w: cos falloff.
    axis: vec4f,
    // x: cos cutoff; y = 1: reaches every cluster; z: its first word in
    // `reach`.
    extra: vec4f,
}

struct Direct {
    samples: u32,
    lights: u32,
    placed: u32,
    // Words per placed light's cluster row.
    words: u32,
    sun_ray: f32,
    // 1: the receiver's cosine scales a directional light.
    sun_cosine: u32,
    offset: u32,
    pad: u32,
}

// Per sample: position (w: set, as bits), normal (w: cluster, as bits).
@group(1) @binding(0) var<storage, read> samples: array<vec4f>;
@group(1) @binding(1) var<storage, read> lights: array<Directional>;
@group(1) @binding(2) var<storage, read> placed: array<Placed>;
@group(1) @binding(3) var<storage, read> reach: array<u32>;
// Per sample: (all, vis), (sun, 0), (potential, 0).
@group(1) @binding(4) var<storage, read_write> direct: array<vec4f>;
@group(1) @binding(5) var<uniform> dp: Direct;

// transport.rs `point_gain`.
fn point_gain(l: Placed, p: vec3f, n: vec3f) -> vec3f {
    let v = l.pos.xyz - p;
    let d = length(v);
    if (d > l.pos.w || d < 1e-3) {
        return vec3f(0.0);
    }
    let dir = v * (1.0 / d);
    let cs = dot(n, dir);
    if (cs <= 0.0) {
        return vec3f(0.0);
    }
    var spot = 1.0;
    if (l.colour.w != 0.0) {
        let c = dot(-dir, l.axis.xyz);
        let cf = l.axis.w;
        let cc = l.extra.x;
        if (c >= cf) {
            spot = 1.0;
        } else if (c <= cc) {
            spot = 0.0;
        } else {
            spot = (c - cc) / max(cf - cc, 1e-6);
        }
    }
    if (spot <= 0.0) {
        return vec3f(0.0);
    }
    let t = transmission(p, l.pos.xyz, false);
    if (all(t <= vec3f(0.0))) {
        return vec3f(0.0);
    }
    let dw = d / WU_TO_M;
    let s = spot * cs / (dw * dw);
    return l.colour.xyz * t * s;
}

// transport.rs `direct_terms_placed`.
@compute @workgroup_size(64)
fn direct_light(@builtin(global_invocation_id) gid: vec3u) {
    let i = gid.x + dp.offset;
    if (i >= dp.samples) {
        return;
    }
    let ps = samples[2u * i];
    let ns = samples[2u * i + 1u];
    let p = ps.xyz;
    let n = ns.xyz;
    let light_set = bitcast<u32>(ps.w);
    let cluster = bitcast<i32>(ns.w);
    var gain = vec3f(0.0);
    var sun = vec3f(0.0);
    var potential = vec3f(0.0);
    var vis = 0.0;
    var count = 0u;
    for (var k = 0u; k < dp.lights; k++) {
        let l = lights[k];
        if (u32(l.towards.w) != light_set) {
            continue;
        }
        let towards = l.towards.xyz;
        let is_sun = l.colour.w != 0.0;
        var cs = 1.0;
        if (dp.sun_cosine != 0u) {
            cs = max(dot(n, towards), 0.0);
        }
        if (is_sun) {
            count += 1u;
        }
        if (cs <= 0.0) {
            continue;
        }
        let unblocked = l.colour.xyz * cs;
        if (is_sun) {
            potential += unblocked;
        }
        let t = transmission(p, p + towards * dp.sun_ray, false);
        if (all(t <= vec3f(0.0))) {
            continue;
        }
        let c = unblocked * t;
        gain += c;
        if (is_sun) {
            sun += c;
            vis += (t.x + t.y + t.z) / 3.0;
        }
    }
    for (var k = 0u; k < dp.placed; k++) {
        let l = placed[k];
        if (l.extra.y == 0.0 && cluster >= 0i) {
            let c = u32(cluster);
            let word = u32(l.extra.z) + c / 32u;
            if (c / 32u >= dp.words || (reach[word] & (1u << (c % 32u))) == 0u) {
                continue;
            }
        }
        gain += point_gain(l, p, n);
    }
    var v = 0.0;
    if (count > 0u) {
        v = vis / f32(count);
    }
    direct[3u * i] = vec4f(gain, v);
    direct[3u * i + 1u] = vec4f(sun, 0.0);
    direct[3u * i + 2u] = vec4f(potential, 0.0);
}
