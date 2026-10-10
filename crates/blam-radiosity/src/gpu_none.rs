//! The GPU path's stand-in when the crate is built without the `gpu`
//! feature: there is never an adapter, so every solve runs on the CPU.

use crate::elements::Elements;
use crate::math::V3;
use crate::transport::{Light, Occluders, Options, PlacedLights};
use crate::visibility::ClusterVis;

pub struct Gpu {
    pub name: String,
}

impl Gpu {
    pub fn new(_occ: &Occluders) -> Result<Gpu, String> {
        Err("built without the `gpu` feature".into())
    }

    pub fn gather(&mut self, _elements: &Elements, _shooters: &[u32], _clusters: &[u32], _targets: &[u32], _generation: u64, _cull: f32, _vis: &mut ClusterVis) -> Result<Vec<(V3, V3)>, String> {
        Err("built without the `gpu` feature".into())
    }

    pub fn direct(&mut self, _samples: &[(V3, V3, u32, i32)], _exterior: &[Light], _interior: &[Light], _placed: &PlacedLights, _opt: &Options) -> Result<Vec<(V3, V3, V3, f32)>, String> {
        Err("built without the `gpu` feature".into())
    }
}
