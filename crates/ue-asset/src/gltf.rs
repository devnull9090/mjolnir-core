//! Writing meshes as glTF 2.0 binary (`.glb`).
//!
//! One file per mesh: a node per LOD (LOD 0 visible, the rest present but
//! unattached to the scene so a viewer shows one), a primitive per section
//! with its material slot's name, positions, normals and the first UV channel
//! as accessors over a single buffer. No textures: a material is a named slot
//! with a default appearance, which is what a DCC tool needs to rebind.
//!
//! Skeletal meshes come out as static geometry in the rest pose. The bone
//! hierarchy is written as nodes so the skeleton is visible, but the mesh is
//! not skinned to it: the cooked vertex buffers this reader decodes carry no
//! weights, so a skin would be a lie.
//!
//! glTF's axes are +Y up, right-handed, metres; Unreal's are +Z up,
//! left-handed, centimetres. Positions and normals are converted:
//! `(x, y, z)` in Unreal becomes `(x, z, y) / 100` here, which flips
//! handedness by swapping two axes, so triangle winding is reversed as well.

use crate::mesh::{Bone, Lod, Section};

const UE_TO_GLTF_SCALE: f32 = 0.01;

/// Convert an Unreal position or direction to glTF space.
fn to_gltf(v: [f32; 3], scale: f32) -> [f32; 3] {
    [v[0] * scale, v[2] * scale, v[1] * scale]
}

/// Pad to a four-byte boundary with `fill`.
fn pad4(buf: &mut Vec<u8>, fill: u8) {
    while buf.len() % 4 != 0 {
        buf.push(fill);
    }
}

struct Accessor {
    view: usize,
    count: usize,
    component_type: u32,
    kind: &'static str,
    min: Option<[f32; 3]>,
    max: Option<[f32; 3]>,
}

struct View {
    offset: usize,
    length: usize,
    target: u32,
}

/// Build the binary buffer and bookkeeping for the accessors.
struct Buffer {
    bytes: Vec<u8>,
    views: Vec<View>,
    accessors: Vec<Accessor>,
}

impl Buffer {
    fn push_f32s(&mut self, data: &[[f32; 3]], target: u32, bounds: bool) -> usize {
        pad4(&mut self.bytes, 0);
        let offset = self.bytes.len();
        let (mut min, mut max) = ([f32::MAX; 3], [f32::MIN; 3]);
        for v in data {
            for k in 0..3 {
                self.bytes.extend_from_slice(&v[k].to_le_bytes());
                min[k] = min[k].min(v[k]);
                max[k] = max[k].max(v[k]);
            }
        }
        self.views.push(View {
            offset,
            length: self.bytes.len() - offset,
            target,
        });
        self.accessors.push(Accessor {
            view: self.views.len() - 1,
            count: data.len(),
            component_type: 5126,
            kind: "VEC3",
            min: bounds.then_some(min),
            max: bounds.then_some(max),
        });
        self.accessors.len() - 1
    }

    fn push_uvs(&mut self, data: &[[f32; 2]]) -> usize {
        pad4(&mut self.bytes, 0);
        let offset = self.bytes.len();
        for v in data {
            self.bytes.extend_from_slice(&v[0].to_le_bytes());
            self.bytes.extend_from_slice(&v[1].to_le_bytes());
        }
        self.views.push(View {
            offset,
            length: self.bytes.len() - offset,
            target: 34962,
        });
        self.accessors.push(Accessor {
            view: self.views.len() - 1,
            count: data.len(),
            component_type: 5126,
            kind: "VEC2",
            min: None,
            max: None,
        });
        self.accessors.len() - 1
    }

    fn push_indices(&mut self, data: &[u32]) -> usize {
        pad4(&mut self.bytes, 0);
        let offset = self.bytes.len();
        for i in data {
            self.bytes.extend_from_slice(&i.to_le_bytes());
        }
        self.views.push(View {
            offset,
            length: self.bytes.len() - offset,
            target: 34963,
        });
        self.accessors.push(Accessor {
            view: self.views.len() - 1,
            count: data.len(),
            component_type: 5125,
            kind: "SCALAR",
            min: None,
            max: None,
        });
        self.accessors.len() - 1
    }
}

fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// One mesh's LODs and the material names its sections refer to.
pub struct MeshExport<'a> {
    pub name: &'a str,
    pub materials: &'a [(String, i32)],
    pub lods: &'a [Lod],
    /// Bones to write as a node hierarchy; empty for a static mesh.
    pub bones: &'a [Bone],
}

/// Serialize a mesh as a `.glb`.
pub fn write_glb(mesh: &MeshExport<'_>) -> Result<Vec<u8>, String> {
    let lods: Vec<&Lod> = mesh
        .lods
        .iter()
        .filter(|l| !l.positions.is_empty() && !l.indices.is_empty())
        .collect();
    if lods.is_empty() {
        return Err("the mesh has no LOD with geometry".into());
    }

    let mut buffer = Buffer {
        bytes: Vec::new(),
        views: Vec::new(),
        accessors: Vec::new(),
    };
    let mut materials_json: Vec<String> = mesh
        .materials
        .iter()
        .map(|(name, _)| {
            format!(
                "{{\"name\":{},\"pbrMetallicRoughness\":{{\"baseColorFactor\":[0.8,0.8,0.8,1],\"metallicFactor\":0,\"roughnessFactor\":0.8}},\"doubleSided\":true}}",
                json_str(name)
            )
        })
        .collect();
    if materials_json.is_empty() {
        materials_json.push(
            "{\"name\":\"default\",\"pbrMetallicRoughness\":{\"baseColorFactor\":[0.8,0.8,0.8,1],\"metallicFactor\":0,\"roughnessFactor\":0.8},\"doubleSided\":true}"
                .into(),
        );
    }

    let mut meshes_json = Vec::new();
    for (li, lod) in lods.iter().enumerate() {
        let vertex_count = lod.positions.len() / 3;
        let positions: Vec<[f32; 3]> = lod
            .positions
            .chunks_exact(3)
            .map(|p| to_gltf([p[0], p[1], p[2]], UE_TO_GLTF_SCALE))
            .collect();
        let pos = buffer.push_f32s(&positions, 34962, true);
        let normal = if lod.normals.len() == lod.positions.len() {
            let normals: Vec<[f32; 3]> = lod
                .normals
                .chunks_exact(3)
                .map(|n| {
                    let v = to_gltf([n[0], n[1], n[2]], 1.0);
                    let len = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
                    if len > 1e-6 {
                        [v[0] / len, v[1] / len, v[2] / len]
                    } else {
                        [0.0, 1.0, 0.0]
                    }
                })
                .collect();
            Some(buffer.push_f32s(&normals, 34962, false))
        } else {
            None
        };
        let uv = if lod.uvs.len() == vertex_count * 2 {
            let uvs: Vec<[f32; 2]> = lod.uvs.chunks_exact(2).map(|t| [t[0], t[1]]).collect();
            Some(buffer.push_uvs(&uvs))
        } else {
            None
        };

        let sections: Vec<&Section> = if lod.sections.is_empty() {
            Vec::new()
        } else {
            lod.sections.iter().collect()
        };
        let mut primitives = Vec::new();
        let ranges: Vec<(usize, usize, i32)> = if sections.is_empty() {
            vec![(0, lod.indices.len() / 3, 0)]
        } else {
            sections
                .iter()
                .map(|s| {
                    (
                        s.first_index as usize,
                        s.num_triangles as usize,
                        s.material_index,
                    )
                })
                .collect()
        };
        for (first, triangles, material) in ranges {
            let end = (first + triangles * 3).min(lod.indices.len());
            if first >= end {
                continue;
            }
            // Swapping two axes mirrors the geometry; reversing the winding
            // keeps the faces pointing out.
            let mut indices = Vec::with_capacity(end - first);
            for tri in lod.indices[first..end].chunks_exact(3) {
                indices.extend_from_slice(&[tri[0], tri[2], tri[1]]);
            }
            if indices.iter().any(|&i| i as usize >= vertex_count) {
                return Err(format!(
                    "LOD {li}: an index reaches past the {vertex_count} vertices"
                ));
            }
            let idx = buffer.push_indices(&indices);
            let material = usize::try_from(material)
                .ok()
                .filter(|m| *m < materials_json.len())
                .unwrap_or(0);
            let mut attrs = format!("\"POSITION\":{pos}");
            if let Some(n) = normal {
                attrs.push_str(&format!(",\"NORMAL\":{n}"));
            }
            if let Some(t) = uv {
                attrs.push_str(&format!(",\"TEXCOORD_0\":{t}"));
            }
            primitives.push(format!(
                "{{\"attributes\":{{{attrs}}},\"indices\":{idx},\"material\":{material},\"mode\":4}}"
            ));
        }
        if primitives.is_empty() {
            continue;
        }
        meshes_json.push(format!(
            "{{\"name\":{},\"primitives\":[{}]}}",
            json_str(&format!("{}_LOD{li}", mesh.name)),
            primitives.join(",")
        ));
    }
    if meshes_json.is_empty() {
        return Err("no section had any triangles".into());
    }

    // Nodes: one per LOD mesh (LOD 0 in the scene), then the bones as a
    // hierarchy under a root the scene also holds.
    let mut nodes_json: Vec<String> = meshes_json
        .iter()
        .enumerate()
        .map(|(i, _)| {
            format!(
                "{{\"name\":{},\"mesh\":{i}}}",
                json_str(&format!("{}_LOD{i}", mesh.name))
            )
        })
        .collect();
    let mut scene_nodes: Vec<usize> = vec![0];
    if !mesh.bones.is_empty() {
        let base = nodes_json.len();
        let mut children: Vec<Vec<usize>> = vec![Vec::new(); mesh.bones.len()];
        let mut roots = Vec::new();
        for (i, b) in mesh.bones.iter().enumerate() {
            match usize::try_from(b.parent) {
                Ok(p) if p < mesh.bones.len() && p != i => children[p].push(base + i),
                _ => roots.push(base + i),
            }
        }
        for (i, b) in mesh.bones.iter().enumerate() {
            let t = to_gltf(b.translation, UE_TO_GLTF_SCALE);
            // A quaternion under the same axis swap: (x, y, z, w) -> (x, z, y, -w).
            let r = [b.rotation[0], b.rotation[2], b.rotation[1], -b.rotation[3]];
            let kids = if children[i].is_empty() {
                String::new()
            } else {
                format!(
                    ",\"children\":[{}]",
                    children[i]
                        .iter()
                        .map(|c| c.to_string())
                        .collect::<Vec<_>>()
                        .join(",")
                )
            };
            nodes_json.push(format!(
                "{{\"name\":{},\"translation\":[{},{},{}],\"rotation\":[{},{},{},{}]{kids}}}",
                json_str(&b.name),
                t[0],
                t[1],
                t[2],
                r[0],
                r[1],
                r[2],
                r[3]
            ));
        }
        scene_nodes.extend(roots);
    }

    let views_json: Vec<String> = buffer
        .views
        .iter()
        .map(|v| {
            format!(
                "{{\"buffer\":0,\"byteOffset\":{},\"byteLength\":{},\"target\":{}}}",
                v.offset, v.length, v.target
            )
        })
        .collect();
    let accessors_json: Vec<String> = buffer
        .accessors
        .iter()
        .map(|a| {
            let bounds = match (a.min, a.max) {
                (Some(min), Some(max)) => format!(
                    ",\"min\":[{},{},{}],\"max\":[{},{},{}]",
                    min[0], min[1], min[2], max[0], max[1], max[2]
                ),
                _ => String::new(),
            };
            format!(
                "{{\"bufferView\":{},\"componentType\":{},\"count\":{},\"type\":\"{}\"{bounds}}}",
                a.view, a.component_type, a.count, a.kind
            )
        })
        .collect();

    pad4(&mut buffer.bytes, 0);
    let json = format!(
        "{{\"asset\":{{\"version\":\"2.0\",\"generator\":\"mjolnir\"}},\"scene\":0,\"scenes\":[{{\"nodes\":[{}]}}],\"nodes\":[{}],\"meshes\":[{}],\"materials\":[{}],\"bufferViews\":[{}],\"accessors\":[{}],\"buffers\":[{{\"byteLength\":{}}}]}}",
        scene_nodes
            .iter()
            .map(|n| n.to_string())
            .collect::<Vec<_>>()
            .join(","),
        nodes_json.join(","),
        meshes_json.join(","),
        materials_json.join(","),
        views_json.join(","),
        accessors_json.join(","),
        buffer.bytes.len()
    );
    let mut json_bytes = json.into_bytes();
    pad4(&mut json_bytes, b' ');

    let total = 12 + 8 + json_bytes.len() + 8 + buffer.bytes.len();
    let mut out = Vec::with_capacity(total);
    out.extend_from_slice(b"glTF");
    out.extend_from_slice(&2u32.to_le_bytes());
    out.extend_from_slice(&(total as u32).to_le_bytes());
    out.extend_from_slice(&(json_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&0x4E4F_534Au32.to_le_bytes()); // JSON
    out.extend_from_slice(&json_bytes);
    out.extend_from_slice(&(buffer.bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&0x004E_4942u32.to_le_bytes()); // BIN
    out.extend_from_slice(&buffer.bytes);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn quad() -> Lod {
        Lod {
            sections: vec![Section {
                material_index: 0,
                first_index: 0,
                num_triangles: 2,
            }],
            positions: vec![
                0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 100.0, 100.0, 0.0, 0.0, 100.0, 0.0,
            ],
            normals: vec![0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0],
            uvs: vec![0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
            indices: vec![0, 1, 2, 0, 2, 3],
            inlined: true,
        }
    }

    #[test]
    fn a_quad_becomes_a_well_formed_glb() {
        let lod = quad();
        let glb = write_glb(&MeshExport {
            name: "quad",
            materials: &[("slot".to_string(), -1)],
            lods: std::slice::from_ref(&lod),
            bones: &[],
        })
        .unwrap();
        assert_eq!(&glb[..4], b"glTF");
        let total = u32::from_le_bytes(glb[8..12].try_into().unwrap()) as usize;
        assert_eq!(total, glb.len());
        assert_eq!(total % 4, 0);
        let json_len = u32::from_le_bytes(glb[12..16].try_into().unwrap()) as usize;
        let json = std::str::from_utf8(&glb[20..20 + json_len]).unwrap();
        assert!(json.contains("\"POSITION\":0"));
        assert!(json.contains("\"NORMAL\":1"));
        assert!(json.contains("\"TEXCOORD_0\":2"));
        assert!(json.contains("\"name\":\"slot\""));
        // Unreal's +Z up became glTF's +Y up, in metres: the max corner is
        // (1, 0, 1) and normals point +Y.
        assert!(json.contains("\"max\":[1,0,1]"));
        let bin_start = 20 + json_len + 8;
        let bin = &glb[bin_start..];
        let n0 = f32::from_le_bytes(bin[48..52].try_into().unwrap());
        let n1 = f32::from_le_bytes(bin[52..56].try_into().unwrap());
        assert_eq!((n0, n1), (0.0, 1.0));
        // The first triangle's winding was reversed.
        let idx_at = bin.len() - 24;
        let first: Vec<u32> = bin[idx_at..idx_at + 12]
            .chunks_exact(4)
            .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
            .collect();
        assert_eq!(first, vec![0, 2, 1]);
    }

    #[test]
    fn bones_become_a_node_hierarchy() {
        let lod = quad();
        let bones = vec![
            Bone {
                name: "root".into(),
                parent: -1,
                translation: [0.0, 0.0, 0.0],
                rotation: [0.0, 0.0, 0.0, 1.0],
            },
            Bone {
                name: "child".into(),
                parent: 0,
                translation: [0.0, 0.0, 50.0],
                rotation: [0.0, 0.0, 0.0, 1.0],
            },
        ];
        let glb = write_glb(&MeshExport {
            name: "m",
            materials: &[],
            lods: std::slice::from_ref(&lod),
            bones: &bones,
        })
        .unwrap();
        let json_len = u32::from_le_bytes(glb[12..16].try_into().unwrap()) as usize;
        let json = std::str::from_utf8(&glb[20..20 + json_len]).unwrap();
        assert!(json.contains("\"name\":\"root\""));
        assert!(json.contains("\"children\":[2]"));
        assert!(json.contains("\"translation\":[0,0.5,0]"));
        assert!(json.contains("\"scenes\":[{\"nodes\":[0,1]}]"));
    }
}
