//! Build exact Forge collision models from the authored metre/Z-up meshes.
//!
//! cargo run -p blam-sbsp --example forge_collision -- geometry.json donor.collision_model out-dir
//!
//! The donor stays local. Each output contains the authored triangle surfaces,
//! a linked two-sided BSP and a rebuilt MOPP; a compound doorway is never
//! replaced by the convex hull of its outer bounds.

use std::{error::Error, fs, path::Path};

use blam_sbsp::ce::{Bsp3dNode, Collision, Edge, Leaf, Plane, Surface, Vertex};
use blam_sbsp::{convert, raytest, scenery, unpack16};
use serde::Deserialize;

const METRES_PER_BLAM_UNIT: f32 = 3.048;

#[derive(Deserialize)]
struct Geometry {
    units: String,
    axes: String,
    pieces: Vec<Piece>,
}

#[derive(Deserialize)]
struct Piece {
    id: String,
    collision: Mesh,
}

#[derive(Deserialize)]
struct Mesh {
    vertices: Vec<[f32; 3]>,
    triangles: Vec<[usize; 3]>,
}

fn sub(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [0, 1, 2].map(|i| a[i] - b[i])
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    (0..3).map(|i| a[i] * b[i]).sum()
}

fn collision(mesh: &Mesh) -> Result<Collision, Box<dyn Error>> {
    if mesh.triangles.is_empty() || mesh.triangles.len() > 4096 {
        return Err("piece must have 1..4096 collision triangles".into());
    }
    // Distinct open leaves are essential: scenery::link rewires each child as
    // it partitions that leaf. Sharing one leaf aliases the two half-spaces.
    let leaf = Leaf {
        flags: 0,
        reference_count: 0,
        first_reference: 0,
    };
    let mut c = Collision {
        planes: vec![Plane {
            n: [1.0, 0.0, 0.0],
            d: 0.0,
        }],
        bsp3d_nodes: vec![Bsp3dNode {
            plane: 0,
            back: i32::MIN,
            front: i32::MIN + 1,
        }],
        leaves: vec![leaf, leaf],
        ..Default::default()
    };
    for triangle in &mesh.triangles {
        let mut points = [[0.0; 3]; 3];
        for (index, &vertex) in triangle.iter().enumerate() {
            let v = mesh
                .vertices
                .get(vertex)
                .ok_or("collision vertex index out of range")?;
            if !v.iter().all(|n| n.is_finite()) {
                return Err("non-finite collision coordinate".into());
            }
            // Blender Z-up -> glTF (x,z,-y) -> Blam (x,-z,y)/3.048:
            // the author's source coordinates therefore keep their axes here.
            points[index] = v.map(|n| n / METRES_PER_BLAM_UNIT);
        }
        let n = cross(sub(points[1], points[0]), sub(points[2], points[0]));
        let length = dot(n, n).sqrt();
        if length < 1e-9 {
            return Err("degenerate collision triangle".into());
        }
        let n = n.map(|v| v / length);
        let plane = c.planes.len() as i32;
        c.planes.push(Plane {
            n,
            d: dot(n, points[0]),
        });
        let surface = c.surfaces.len() as i32;
        let first_edge = c.edges.len() as i32;
        let first_vertex = c.vertices.len() as i32;
        for j in 0..3 {
            c.vertices.push(Vertex {
                point: points[j],
                first_edge: first_edge + j as i32,
            });
            c.edges.push(Edge {
                start: first_vertex + j as i32,
                end: first_vertex + ((j + 1) % 3) as i32,
                forward: first_edge + ((j + 1) % 3) as i32,
                reverse: -1,
                left: surface,
                right: -1,
            });
        }
        c.surfaces.push(Surface {
            plane,
            first_edge,
            flags: 1,
            breakable: -1,
            material: 0,
        });
    }
    scenery::link(&mut c, 0);
    Ok(c)
}

fn verify(c: &Collision) -> Result<usize, Box<dyn Error>> {
    let polygons: Vec<_> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(c, s))
        .collect();
    let mut rays = Vec::new();
    for (s, poly) in polygons.iter().enumerate() {
        let center =
            [0, 1, 2].map(|axis| poly.iter().map(|p| p[axis]).sum::<f32>() / poly.len() as f32);
        let n = c.planes[c.surfaces[s].plane as usize].n;
        let a = [0, 1, 2].map(|i| center[i] + n[i] * 0.025);
        let b = [0, 1, 2].map(|i| center[i] - n[i] * 0.025);
        rays.push((a, b));
        rays.push((b, a));
    }
    let bounds = c.bounds().ok_or("empty collision bounds")?;
    // Full-axis sweeps also sample empty door/window/corner space, catching
    // phantom filled collision that centroid-only hit tests would miss.
    for axis in 0..3 {
        let (u, v) = ((axis + 1) % 3, (axis + 2) % 3);
        for i in 0..13 {
            for j in 0..13 {
                let mut a = bounds.min;
                a[axis] -= 0.1;
                a[u] += (bounds.max[u] - bounds.min[u]) * (i as f32 + 0.37) / 13.0;
                a[v] += (bounds.max[v] - bounds.min[v]) * (j as f32 + 0.61) / 13.0;
                let mut b = a;
                b[axis] = bounds.max[axis] + 0.1;
                rays.push((a, b));
            }
        }
    }
    let report = raytest::compare(c, &rays, 0.0005);
    if report.missed != 0 || report.phantom != 0 || report.displaced != 0 {
        return Err(format!("linked collision tree disagrees with triangles: {report:?}").into());
    }
    Ok(rays.len())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 3 {
        return Err(
            "usage: forge_collision <geometry.json> <donor.collision_model> <out-dir>".into(),
        );
    }
    let geometry: Geometry = serde_json::from_slice(&fs::read(&args[0])?)?;
    if geometry.units != "meters" || geometry.axes != "right_handed_z_up" {
        return Err("expected authored metres in right_handed_z_up coordinates".into());
    }
    let donor = fs::read(&args[1])?;
    let output = Path::new(&args[2]);
    fs::create_dir_all(output)?;
    let mut report = Vec::new();
    for piece in geometry.pieces {
        if piece.id.is_empty()
            || !piece
                .id
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        {
            return Err("invalid piece id".into());
        }
        let c = collision(&piece.collision)?;
        let rays = verify(&c)?;
        let surfaces = c.surfaces.len();
        let payload = convert::collision_model(&donor, c)?;
        let target = output.join(format!("{}.collision_model", piece.id));
        fs::write(&target, &payload)?;
        println!(
            "{}: {surfaces} surfaces, {rays} verified rays, {} bytes",
            piece.id,
            payload.len()
        );
        report.push(serde_json::json!({"id": piece.id, "surfaces": surfaces, "verified_rays": rays, "bytes": payload.len()}));
    }
    fs::write(
        output.join("collision-report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(())
}
