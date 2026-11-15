//! A Halo 2 door's opening (machine type 1: Zanzibar's house gate, whose
//! bars, locks, doors and ramps swing and slide apart as its keypad is
//! pressed): its render model's node hierarchy and default pose, and its
//! `device:position` animation decoded for every node at every frame.
//!
//! Layouts (MCC Halo 2): render model (`mode`) nodes at 0x48 (0x60 each:
//! name 0x00, parent i16 0x04, default translation 0x0C, default rotation
//! (i, j, k, w) 0x18). The animation's keyframe codecs 4-7 (docs/h2_cache_format.md):
//! after the codec, the rotating / sliding / scaling node counts, error and
//! rate, eight u32 offsets from 0x0C (translation and scale frame info, the
//! three keyframe index arrays, the three key arrays); the rotating nodes'
//! frame info from 0x30 and the translation frame info at its offset, one
//! u32 a node (key count in the low 12 bits, first key in the high 20),
//! stored last node first (the gate's mirrored pairs read in pairs only
//! that way); the frame data ends with three bit fields, one bit a node
//! (u32s: rotation, translation, scale), naming the animated nodes. A
//! rotation key is i16 (i, j, k, w) / 32767, a translation key three floats
//! (world units), both the node's local transform, replacing its default.
use super::{Cache, Tag};

#[derive(Debug, Clone)]
pub struct Node {
    pub name: String,
    pub parent: i16,
    pub translation: [f32; 3],
    pub rotation: [f32; 4],
}

#[derive(Debug, Clone)]
pub struct Opening {
    pub nodes: Vec<Node>,
    pub frames: usize,
    /// Local (translation, rotation) of every node at every frame.
    pub poses: Vec<Vec<([f32; 3], [f32; 4])>>,
    /// Seconds the opening takes (the machine's position transition time).
    pub seconds: f32,
}

fn norm(q: [f32; 4]) -> [f32; 4] {
    let n = q.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-9);
    q.map(|c| c / n)
}

fn nlerp(a: [f32; 4], b: [f32; 4], t: f32) -> [f32; 4] {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let b = if dot < 0.0 { b.map(|c| -c) } else { b };
    norm([0, 1, 2, 3].map(|k| a[k] + (b[k] - a[k]) * t))
}

/// The keys of one node track as (frame, value), sampled at every frame.
fn sample<T: Copy>(keys: &[(usize, T)], frames: usize, lerp: impl Fn(T, T, f32) -> T) -> Vec<T> {
    (0..frames)
        .map(|f| {
            let i = keys.iter().rposition(|&(k, _)| k <= f).unwrap_or(0);
            let (fa, a) = keys[i];
            match keys.get(i + 1) {
                Some(&(fb, b)) if fb > fa => lerp(a, b, (f - fa) as f32 / (fb - fa) as f32),
                _ => a,
            }
        })
        .collect()
}

/// The door's opening, or the reason it cannot be read.
pub fn opening(cache: &Cache, machine: &Tag<'_>) -> Result<Opening, String> {
    let hlmt = machine.root.tagref(0x34).and_then(|r| cache.follow(r)).ok_or("no model")?;
    let mode = hlmt.root.tagref(0x00).and_then(|r| cache.follow(r)).ok_or("no render model")?;
    let graph = hlmt.root.tagref(0x10).and_then(|r| cache.follow(r)).ok_or("no animation graph")?;
    let nodes: Vec<Node> = mode
        .root
        .block(0x48, 0x60)
        .iter()
        .map(|n| Node {
            name: n.sid(0x00).to_string(),
            parent: n.i16(0x04),
            translation: n.vec3(0x0C),
            rotation: norm([n.f32(0x18), n.f32(0x1C), n.f32(0x20), n.f32(0x24)]),
        })
        .collect();
    let count = nodes.len();
    let anim = graph
        .root
        .block(0x2C, 0x60)
        .iter()
        .find(|a| a.sid(0x00) == "device:position")
        .ok_or("no device:position animation")?;
    let frames = anim.i16(0x14).max(1) as usize;
    let size = anim.u32(0x28) as usize;
    let at = graph.file.offset(anim.u32(0x2C)).ok_or("no animation data")?;
    let data = graph.file.data.get(at..at + size).ok_or("animation data runs past the file")?;
    let d = data.get(anim.i16(0x36).max(0) as usize..).ok_or("no animated codec block")?;
    let u32_at = |o: usize| -> Result<u32, String> {
        d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())).ok_or_else(|| format!("short at {o:#x}"))
    };
    let codec = d[0];
    if !(4..=7).contains(&codec) {
        return Err(format!("codec {codec} (keyframe codecs 4-7 only)"));
    }
    let (rotating, sliding, scaling) = (d[1] as usize, d[2] as usize, d[3] as usize);
    if scaling != 0 {
        return Err("scaling nodes".into());
    }
    let words = count.div_ceil(32);
    let tail = data.len().checked_sub(12 * words).ok_or("no node flags")?;
    let flags = |which: usize| -> Vec<usize> {
        (0..count)
            .filter(|&n| {
                let o = tail + 4 * (which * words + n / 32);
                let w = u32::from_le_bytes(data[o..o + 4].try_into().unwrap());
                w >> (n % 32) & 1 == 1
            })
            .collect()
    };
    let (rot_nodes, slide_nodes) = (flags(0), flags(1));
    if rot_nodes.len() != rotating || slide_nodes.len() != sliding {
        return Err(format!(
            "node flags name {} turning and {} sliding nodes, the codec {rotating} and {sliding}",
            rot_nodes.len(),
            slide_nodes.len()
        ));
    }
    let wide = codec == 5 || codec == 7;
    let frame_of = |base: usize, k: usize| -> Result<usize, String> {
        if wide {
            d.get(base + 2 * k..base + 2 * k + 2).map(|b| u16::from_le_bytes([b[0], b[1]]) as usize)
        } else {
            d.get(base + k).map(|&b| b as usize)
        }
        .ok_or_else(|| "keyframe index past the block".into())
    };
    // One frame info word a node, last node first: sorted by first key.
    let infos = |base: usize, n: usize| -> Result<Vec<(usize, usize)>, String> {
        let mut v = (0..n)
            .map(|i| u32_at(base + 4 * i).map(|w| ((w >> 12) as usize, (w & 0xFFF) as usize)))
            .collect::<Result<Vec<_>, _>>()?;
        v.sort();
        Ok(v)
    };
    let (rot_kf, slide_kf) = (u32_at(0x14)? as usize, u32_at(0x18)? as usize);
    let (rot_data, slide_data) = (u32_at(0x20)? as usize, u32_at(0x24)? as usize);
    let mut poses: Vec<Vec<([f32; 3], [f32; 4])>> =
        (0..frames).map(|_| nodes.iter().map(|n| (n.translation, n.rotation)).collect()).collect();
    for (node, (first, n)) in rot_nodes.iter().zip(infos(0x30, rotating)?) {
        let mut keys = Vec::new();
        for k in first..first + n {
            let q = d.get(rot_data + 8 * k..rot_data + 8 * k + 8).ok_or("rotation key past the block")?;
            let c = |i: usize| i16::from_le_bytes([q[2 * i], q[2 * i + 1]]) as f32 / 32767.0;
            keys.push((frame_of(rot_kf, k)?, norm([c(0), c(1), c(2), c(3)])));
        }
        for (f, q) in sample(&keys, frames, nlerp).into_iter().enumerate() {
            poses[f][*node].1 = q;
        }
    }
    for (node, (first, n)) in slide_nodes.iter().zip(infos(u32_at(0x0C)? as usize, sliding)?) {
        let mut keys = Vec::new();
        for k in first..first + n {
            let o = slide_data + 12 * k;
            let f = |i: usize| d.get(o + 4 * i..o + 4 * i + 4).map(|b| f32::from_le_bytes(b.try_into().unwrap()));
            keys.push((frame_of(slide_kf, k)?, [f(0).ok_or("short")?, f(1).ok_or("short")?, f(2).ok_or("short")?]));
        }
        let lerp = |a: [f32; 3], b: [f32; 3], t: f32| [0, 1, 2].map(|i| a[i] + (b[i] - a[i]) * t);
        for (f, t) in sample(&keys, frames, lerp).into_iter().enumerate() {
            poses[f][*node].0 = t;
        }
    }
    let rate = machine.root.f32(0xC8);
    let seconds = if rate > 0.0 && rate < 900.0 { 1.0 / rate } else { 1.0 };
    Ok(Opening { nodes, frames, poses, seconds })
}
