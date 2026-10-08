//! The merged scene glTF a converted map is built from
//! (`tools/level/merge_ce_scene.py`): every triangle of the BSP and the
//! placed scenery, with its lightmap page and UVs where it has them. glTF
//! units are metres, y up (CE (x, y, z) is glTF (x, z, -y) in metres).

use crate::math::V3;
use std::path::Path;

/// One triangle of the scene.
#[derive(Clone, Debug)]
pub struct Tri {
    pub p: [V3; 3],
    /// The vertex normals (CE's, smoothed across the mesh).
    pub n: [V3; 3],
    /// Texture UVs (the base map's), for the reflectance samples.
    pub uv0: [[f32; 2]; 3],
    /// Lightmap UVs on the triangle's page, when the surface is lightmapped.
    pub uv1: Option<[[f32; 2]; 3]>,
    /// The lightmap page the UVs address (`__lmN` of the material's name).
    pub page: Option<usize>,
    /// The scene material (index into [`Scene::materials`]).
    pub material: usize,
    /// The glTF primitive and the triangle's index within it: the BSP's
    /// cluster table (`bsp/clusters_0.json`) is keyed that way.
    pub prim: u32,
    pub index: u32,
}

/// A glTF material: a CE shader on one lightmap page, or a placed object's
/// (`__lmobj`) or the sky's (`__sky`).
#[derive(Clone, Debug)]
pub struct Material {
    pub name: String,
    /// The CE shader's name (the glTF name without its `__lm` suffix).
    pub shader: String,
    pub page: Option<usize>,
    /// A placed object's material: lit per object in CE, not lightmapped.
    pub object: bool,
    pub sky: bool,
}

pub struct Scene {
    pub tris: Vec<Tri>,
    pub materials: Vec<Material>,
}

struct Doc {
    doc: serde_json::Value,
    bin: Vec<u8>,
}

impl Doc {
    fn view(&self, index: usize) -> (usize, usize, usize, u64) {
        let acc = &self.doc["accessors"][index];
        let count = acc["count"].as_u64().unwrap() as usize;
        let view = &self.doc["bufferViews"][acc["bufferView"].as_u64().unwrap() as usize];
        let base = view["byteOffset"].as_u64().unwrap_or(0) as usize + acc["byteOffset"].as_u64().unwrap_or(0) as usize;
        let stride = view["byteStride"].as_u64().unwrap_or(0) as usize;
        (count, base, stride, acc["componentType"].as_u64().unwrap())
    }

    fn floats(&self, index: usize, comps: usize) -> Vec<f32> {
        let (count, base, stride, _) = self.view(index);
        let step = if stride > 0 { stride } else { comps * 4 };
        let mut out = Vec::with_capacity(count * comps);
        for i in 0..count {
            for c in 0..comps {
                let at = base + i * step + c * 4;
                out.push(f32::from_le_bytes(self.bin[at..at + 4].try_into().unwrap()));
            }
        }
        out
    }

    fn indices(&self, index: usize) -> Vec<u32> {
        let (count, base, _, kind) = self.view(index);
        (0..count)
            .map(|i| match kind {
                5125 => u32::from_le_bytes(self.bin[base + i * 4..base + i * 4 + 4].try_into().unwrap()),
                5123 => u16::from_le_bytes(self.bin[base + i * 2..base + i * 2 + 2].try_into().unwrap()) as u32,
                5121 => self.bin[base + i] as u32,
                k => panic!("index component type {k}"),
            })
            .collect()
    }
}

impl Scene {
    pub fn load(path: &Path) -> Result<Scene, String> {
        let doc: serde_json::Value = serde_json::from_slice(&std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?)
            .map_err(|e| format!("{}: {e}", path.display()))?;
        let uri = doc["buffers"][0]["uri"].as_str().ok_or("glTF without a buffer uri")?;
        let bin = std::fs::read(path.parent().unwrap_or(Path::new(".")).join(uri)).map_err(|e| format!("{uri}: {e}"))?;
        let g = Doc { doc, bin };

        let materials: Vec<Material> = g.doc["materials"]
            .as_array()
            .map(|ms| {
                ms.iter()
                    .map(|m| {
                        let name = m["name"].as_str().unwrap_or("").to_string();
                        let (shader, suffix) = name.rsplit_once("__").unwrap_or((name.as_str(), ""));
                        let page = suffix.strip_prefix("lm").and_then(|n| n.parse::<usize>().ok());
                        Material {
                            shader: shader.to_string(),
                            page,
                            object: suffix == "lmobj",
                            sky: suffix == "sky",
                            name,
                        }
                    })
                    .collect()
            })
            .unwrap_or_default();

        let mut tris = Vec::new();
        let mut prim_index = 0u32;
        for mesh in g.doc["meshes"].as_array().ok_or("glTF without meshes")? {
            for prim in mesh["primitives"].as_array().unwrap_or(&Vec::new()) {
                let this_prim = prim_index;
                prim_index += 1;
                let at = &prim["attributes"];
                let pos = g.floats(at["POSITION"].as_u64().ok_or("primitive without POSITION")? as usize, 3);
                let nrm = at["NORMAL"].as_u64().map(|i| g.floats(i as usize, 3));
                let uv0 = at["TEXCOORD_0"].as_u64().map(|i| g.floats(i as usize, 2));
                let uv1 = at["TEXCOORD_1"].as_u64().map(|i| g.floats(i as usize, 2));
                let idx = g.indices(prim["indices"].as_u64().ok_or("primitive without indices")? as usize);
                let material = prim["material"].as_u64().unwrap_or(0) as usize;
                let page = materials.get(material).and_then(|m| m.page);
                let v = |i: u32| -> V3 {
                    let i = i as usize * 3;
                    [pos[i], pos[i + 1], pos[i + 2]]
                };
                for (k, t) in idx.chunks_exact(3).enumerate() {
                    let p = [v(t[0]), v(t[1]), v(t[2])];
                    let n = match &nrm {
                        Some(n) => {
                            let nv = |i: u32| -> V3 {
                                let i = i as usize * 3;
                                [n[i], n[i + 1], n[i + 2]]
                            };
                            [nv(t[0]), nv(t[1]), nv(t[2])]
                        }
                        None => {
                            let f = crate::math::norm(crate::math::cross(
                                crate::math::sub(p[1], p[0]),
                                crate::math::sub(p[2], p[0]),
                            ));
                            [f, f, f]
                        }
                    };
                    let uv0 = match &uv0 {
                        Some(uv) => {
                            let u = |i: u32| -> [f32; 2] {
                                let i = i as usize * 2;
                                [uv[i], uv[i + 1]]
                            };
                            [u(t[0]), u(t[1]), u(t[2])]
                        }
                        None => [[0.0; 2]; 3],
                    };
                    let uv1 = match (&uv1, page) {
                        (Some(uv), Some(_)) => {
                            let u = |i: u32| -> [f32; 2] {
                                let i = i as usize * 2;
                                [uv[i], uv[i + 1]]
                            };
                            Some([u(t[0]), u(t[1]), u(t[2])])
                        }
                        _ => None,
                    };
                    tris.push(Tri { p, n, uv0, uv1, page, material, prim: this_prim, index: k as u32 });
                }
            }
        }
        Ok(Scene { tris, materials })
    }

    /// The triangles' positions alone, for a [`crate::bvh::Bvh`].
    pub fn positions(&self) -> Vec<[V3; 3]> {
        self.tris.iter().map(|t| t.p).collect()
    }
}
