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

// math.rs `add`, `sub`, `mul`, `dot` in the CPU's order and rounding
// (`xadd` etc. from gpu_exact_*.wgsl).
fn xadd3(a: vec3f, b: vec3f) -> vec3f {
    return vec3f(xadd(a.x, b.x), xadd(a.y, b.y), xadd(a.z, b.z));
}

fn xsub3(a: vec3f, b: vec3f) -> vec3f {
    return vec3f(xsub(a.x, b.x), xsub(a.y, b.y), xsub(a.z, b.z));
}

fn xscale3(a: vec3f, s: f32) -> vec3f {
    return vec3f(xmul(a.x, s), xmul(a.y, s), xmul(a.z, s));
}

fn xdot(a: vec3f, b: vec3f) -> f32 {
    return xadd(xadd(xmul(a.x, b.x), xmul(a.y, b.y)), xmul(a.z, b.z));
}

// The sign of `dot(a, b) - w` as the CPU finds it: plain f32 when the
// value is clear of zero by more than f32's error on it (a few ulps of the
// terms' magnitude, here bounded by 1e-5 of it), the CPU's own rounding
// otherwise. f64 runs at a sliver of f32's rate on most GPUs, and nearly
// every plane test is far from its plane.
fn plane_side(a: vec3f, b: vec3f, w: f32) -> f32 {
    let fast = a.x * b.x + a.y * b.y + a.z * b.z - w;
    let size = abs(a.x * b.x) + abs(a.y * b.y) + abs(a.z * b.z) + abs(w);
    if (abs(fast) > 1e-5 * size) {
        return fast;
    }
    return xsub(xdot(a, b), w);
}

// collision.rs `in_solid`: a glTF point (metres) in the BSP's solid.
fn in_solid(p: vec3f) -> bool {
    let q = vec3f(xdiv(p.x, WU_TO_M), xdiv(-p.z, WU_TO_M), xdiv(p.y, WU_TO_M));
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
        let d = plane_side(pl.xyz, q, pl.w);
        node = select(solid_nodes[3u * u32(node) + 1u], solid_nodes[3u * u32(node) + 2u], d >= 0.0);
    }
    return false;
}

// transport.rs `Occluders::transmission`, its ray set up in the CPU's
// arithmetic: the solid tests at its ends decide on a few ulps where a
// ray grazes a wall.
fn transmission(src: vec3f, dst: vec3f, end_in_level: bool) -> vec3f {
    let v = xsub3(dst, src);
    let l = xsqrt(xdot(v, v));
    if (l <= 0.002) {
        return vec3f(1.0);
    }
    let d = xscale3(v, xdiv(1.0, l));
    let t0 = 0.001;
    let end = xsub(l, 0.001);
    let start = xadd3(src, xscale3(d, t0));
    if (scene.solid_nodes > 0u) {
        if (in_solid(start) || (end_in_level && in_solid(xadd3(src, xscale3(d, end))))) {
            return vec3f(0.0);
        }
    }
    return trace(start, d, xsub(end, t0));
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
    // 1: every cluster sees every cluster (no visibility test).
    all: u32,
    // visibility.rs `ClusterVis::flat`: words per row, where the group
    // table and the cluster lists start in `vis`.
    words: u32,
    table: u32,
    lists: u32,
}

// Per vertex: position, normal (w unused).
@group(1) @binding(0) var<storage, read> verts: array<vec4f>;
@group(1) @binding(1) var<storage, read> targets: array<u32>;
@group(1) @binding(2) var<storage, read> shooters: array<Shooter>;
// Per target, six floats: the gain, the luminance-weighted incident
// direction.
@group(1) @binding(3) var<storage, read_write> gathered: array<f32>;
@group(1) @binding(4) var<uniform> gp: Gather;
// Per vertex, its cluster group.
@group(1) @binding(5) var<storage, read> vgroup: array<u32>;
// The clusters' visibility rows, then per group (first, count), then the
// groups' cluster lists.
@group(1) @binding(6) var<storage, read> vis: array<u32>;

// visibility.rs `ClusterVis::sees`: a shooter in `cluster` lights a vertex
// of group `g` when its row holds any of the group's clusters.
fn sees(cluster: u32, g: u32) -> bool {
    let first = vis[gp.table + 2u * g];
    let count = vis[gp.table + 2u * g + 1u];
    for (var k = 0u; k < count; k++) {
        let c = vis[gp.lists + first + k];
        if (((vis[cluster * gp.words + c / 32u] >> (c % 32u)) & 1u) != 0u) {
            return true;
        }
    }
    return false;
}

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
    var group = 0u;
    if (gp.all == 0u) {
        group = vgroup[vi];
    }
    var gain = vec3f(0.0);
    var dir = vec3f(0.0);
    let su = array<f32, 3>(1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0);
    let sv = array<f32, 3>(1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0);
    for (var s = 0u; s < gp.shooters; s++) {
        let sh = shooters[s];
        if (gp.all == 0u && !sees(bitcast<u32>(sh.delta.w), group)) {
            continue;
        }
        let n = sh.normal.xyz;
        if (plane_side(n, rp, sh.v1.w) <= 0.0) {
            continue;
        }
        let ignore = sh.normal.w != 0.0;
        let da = sh.v0.w;
        var f = vec3f(0.0);
        var fdir = vec3f(0.0);
        for (var k = 0u; k < 3u; k++) {
            let u = su[k];
            let w = sv[k];
            // The sample point in plain f32 for the tests below; in the CPU's
            // arithmetic for the ray, which only the survivors cast.
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
            let qx = xadd3(xadd3(xscale3(sh.v0.xyz, xsub(xsub(1.0, u), w)), xscale3(sh.v1.xyz, u)), xscale3(sh.v2.xyz, w));
            let t = transmission(rp, qx, true);
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
        let t = transmission(p, xadd3(p, xscale3(towards, dp.sun_ray)), false);
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
