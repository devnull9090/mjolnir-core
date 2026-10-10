// The walk along a ray behind `transmission` (gpu.wgsl) on the GPU's ray
// tracing hardware: one acceleration structure over the occluders, the
// opaque triangles as an opaque geometry (the hardware commits the first one
// met and stops) and the glass as a non-opaque one, whose every pane comes
// back as a candidate to multiply its tint in. gpu.rs puts this, after
// `enable wgpu_ray_query;`, in front of gpu.wgsl.

@group(0) @binding(0) var occluders: acceleration_structure;
// Per glass triangle (the non-opaque geometry's primitives): its tint.
@group(0) @binding(1) var<storage, read> glass: array<vec4f>;

// The light through every triangle on `o + t d`, t in (1e-5, tmax): zero
// when an opaque one is met, the panes' tints' product through glass (in
// any order: the product does not care).
fn trace(o: vec3f, d: vec3f, tmax: f32) -> vec3f {
    var t = vec3f(1.0);
    if (scene.tris == 0u || tmax <= 1e-5) {
        return t;
    }
    var rq: ray_query;
    rayQueryInitialize(&rq, occluders, RayDesc(RAY_FLAG_TERMINATE_ON_FIRST_HIT, 0xFFu, 1e-5, tmax, o, d));
    while (rayQueryProceed(&rq)) {
        let c = rayQueryGetCandidateIntersection(&rq);
        t *= glass[c.primitive_index].xyz;
        if (all(t <= vec3f(1e-4))) {
            rayQueryTerminate(&rq);
            return vec3f(0.0);
        }
    }
    if (rayQueryGetCommittedIntersection(&rq).kind != RAY_QUERY_INTERSECTION_NONE) {
        return vec3f(0.0);
    }
    return t;
}
