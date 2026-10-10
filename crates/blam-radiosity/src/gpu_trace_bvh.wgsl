// The software tree walk behind `transmission` (gpu.wgsl): the CPU's BVH
// as flat arrays, any GPU. Prepended to gpu.wgsl by gpu.rs.

struct Node {
    lo: vec3f,
    // Leaf: first triangle; inner: right child (left is the next node).
    index: u32,
    hi: vec3f,
    // Leaf: triangle count; inner: 0.
    count: u32,
}

@group(0) @binding(0) var<storage, read> nodes: array<Node>;
// Per triangle in tree order: its first corner and its two edges (w unused).
@group(0) @binding(1) var<storage, read> tris: array<vec4f>;
// Per triangle in tree order: the glass tint, w = 1; w = 0 blocks.
@group(0) @binding(2) var<storage, read> tint: array<vec4f>;

// A finite reciprocal: an axis-parallel ray's slabs stay well defined.
fn safe_inv(x: f32) -> f32 {
    if (abs(x) < 1e-20) {
        return select(-1e20, 1e20, x >= 0.0);
    }
    return 1.0 / x;
}

// The light through every triangle on `o + t d`, t in (1e-5, tmax): zero at
// the first opaque one, the tints' product through glass. The product does
// not depend on the order the panes are met in, so one any-hit walk of the
// tree finds it (the CPU walks pane to pane, nearest first).
fn trace(o: vec3f, d: vec3f, tmax: f32) -> vec3f {
    var t = vec3f(1.0);
    if (scene.tris == 0u) {
        return t;
    }
    let inv = vec3f(safe_inv(d.x), safe_inv(d.y), safe_inv(d.z));
    var stack: array<u32, 64>;
    var sp = 1u;
    stack[0] = 0u;
    while (sp > 0u) {
        sp -= 1u;
        let at = stack[sp];
        let node = nodes[at];
        let a = (node.lo - o) * inv;
        let b = (node.hi - o) * inv;
        let lo = min(a, b);
        let hi = max(a, b);
        let t0 = max(max(lo.x, lo.y), max(lo.z, 0.0));
        let t1 = min(min(hi.x, hi.y), min(hi.z, tmax));
        if (t0 > t1) {
            continue;
        }
        if (node.count > 0u) {
            for (var i = node.index; i < node.index + node.count; i++) {
                // Moller-Trumbore, both faces.
                let v0 = tris[3u * i].xyz;
                let e1 = tris[3u * i + 1u].xyz;
                let e2 = tris[3u * i + 2u].xyz;
                let p = cross(d, e2);
                let det = dot(e1, p);
                if (abs(det) < 1e-12) {
                    continue;
                }
                let inv_det = 1.0 / det;
                let s = o - v0;
                let u = dot(s, p) * inv_det;
                if (u < 0.0 || u > 1.0) {
                    continue;
                }
                let q = cross(s, e1);
                let v = dot(d, q) * inv_det;
                if (v < 0.0 || u + v > 1.0) {
                    continue;
                }
                let th = dot(e2, q) * inv_det;
                if (th > 1e-5 && th < tmax) {
                    let c = tint[i];
                    if (c.w == 0.0) {
                        return vec3f(0.0);
                    }
                    t *= c.xyz;
                    if (all(t <= vec3f(1e-4))) {
                        return vec3f(0.0);
                    }
                }
            }
        } else if (sp + 2u <= 64u) {
            stack[sp] = at + 1u;
            stack[sp + 1u] = node.index;
            sp += 2u;
        }
    }
    return t;
}

