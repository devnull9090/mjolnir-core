//! A machine's device animation, as far as a gear turning about its own
//! vertical axis needs it (Ascension's antennas).
//!
//! A `mach` tag's device part holds its position transition at +0xC8,
//! stored as a rate (1 / seconds; a time of 0 is stored as 900), and its
//! machine type at +0x11C (0 door, 1 platform, 2 gear). A gear's position
//! runs from 0 to 1 over that time and starts again, from the map's load,
//! for ever; the animation called `device:position` is sampled at position
//! x (frame count - 1).
//!
//! The animation graph (`jmad`, the model's +0x10): animations at +0x2C,
//! 0x60 bytes each: name (string id) 0x00, node count u8 0x13, frame count
//! i16 0x14, the frame data as a dataref {size, address} at 0x28 (in the
//! tag, not a raw resource), the static data's size i16 at 0x36. The data
//! is the static codec block, then the animated one. The keyframe codecs
//! (4 byte, 5 word, 6 reverse byte, 7 reverse word frame indices) start
//! u8 codec, u8 rotation / translation / scale node counts, two floats,
//! eight u32 offsets from 0x0C (translation and scale frame info, rotation /
//! translation / scale keyframe indices, rotation / translation / scale
//! data), then one u32 per rotating node at 0x30 (count in the low 12
//! bits, the node's first key in the high 20). A rotation key is i16
//! (i, j, k, w) / 32767, the node's turn from its default pose. Checked on
//! the 34 machines of the 24 maps (every run tiles its arrays, every key is
//! unit length) and against Ascension's antenna sounds, whose lengths fit
//! frames 2 s apart over its 40 s.

use serde_json::{json, Value};

use crate::h2::{Cache, Tag};

/// A gear's turn about its object's +Z: its period in seconds and its
/// keys, (seconds, degrees counter-clockwise seen from above), linear
/// between them.
#[derive(Debug, PartialEq)]
pub struct Turn {
    pub period: f32,
    pub keys: Vec<(f32, f32)>,
}

impl Turn {
    pub fn to_json(&self) -> Value {
        json!({
            "period": self.period,
            "axis": "z",
            "keys": self.keys.iter().map(|&(t, a)| json!([round3(t), round3(a)])).collect::<Vec<_>>(),
        })
    }
}

fn round3(x: f32) -> f64 {
    (x as f64 * 1000.0).round() / 1000.0
}

/// The turn of a machine whose device animation rotates its one node about
/// +Z, or `None` with the reason (a door, a platform, a part that slides,
/// several nodes).
pub fn gear_turn(cache: &Cache, machine: &Tag<'_>) -> Result<Turn, String> {
    let root = machine.root;
    let kind = root.u16(0x11C);
    if kind != 2 {
        return Err(format!("machine type {kind} (only gears turn by themselves)"));
    }
    let rate = root.f32(0xC8);
    if !(rate > 0.0 && rate < 900.0) {
        return Err("no position transition time".into());
    }
    let period = 1.0 / rate;
    let model = root.tagref(0x34).and_then(|r| cache.follow(r)).ok_or("no model")?;
    let graph = model.root.tagref(0x10).and_then(|r| cache.follow(r)).ok_or("no animation graph")?;
    let anim = graph
        .root
        .block(0x2C, 0x60)
        .iter()
        .find(|a| a.sid(0x00) == "device:position")
        .ok_or("no device:position animation")?;
    if graph.root.block(0x0C, 0x20).count != 1 {
        return Err(format!("{} animated nodes (one rigid node only)", graph.root.block(0x0C, 0x20).count));
    }
    let frames = anim.i16(0x14).max(1) as f32;
    let size = anim.u32(0x28) as usize;
    let at = graph.file.offset(anim.u32(0x2C)).ok_or("no animation data")?;
    let data = graph.file.data.get(at..at + size).ok_or("animation data runs past the file")?;
    let d = data.get(anim.i16(0x36).max(0) as usize..).ok_or("no animated codec block")?;
    turn_from_codec(d, frames, period)
}

/// The keys of a keyframe codec block whose one rotating node turns about
/// +Z, at `frames` frames over `period` seconds.
fn turn_from_codec(d: &[u8], frames: f32, period: f32) -> Result<Turn, String> {
    let u32_at = |o: usize| d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap()));
    let codec = *d.first().ok_or("empty codec block")?;
    if !(4..=7).contains(&codec) {
        return Err(format!("codec {codec} (keyframe codecs 4-7 only)"));
    }
    let (rotating, sliding, scaling) = (d[1], d[2], d[3]);
    if rotating != 1 || sliding != 0 || scaling != 0 {
        return Err(format!("{rotating} turning, {sliding} sliding, {scaling} scaling node(s)"));
    }
    let (keyframes, keys) = (u32_at(0x14).ok_or("short")? as usize, u32_at(0x20).ok_or("short")? as usize);
    let info = u32_at(0x30).ok_or("short")?;
    let (count, first) = ((info & 0xFFF) as usize, (info >> 12) as usize);
    let wide = codec == 5 || codec == 7;
    let mut out: Vec<(f32, f32)> = Vec::new();
    for k in first..first + count {
        let frame = if wide {
            d.get(keyframes + 2 * k..keyframes + 2 * k + 2).map(|b| u16::from_le_bytes([b[0], b[1]]) as f32)
        } else {
            d.get(keyframes + k).map(|&b| b as f32)
        }
        .ok_or("keyframe index past the block")?;
        let q: Vec<f32> = (0..4)
            .map(|c| d.get(keys + 8 * k + 2 * c..keys + 8 * k + 2 * c + 2).map(|b| i16::from_le_bytes([b[0], b[1]]) as f32 / 32767.0))
            .collect::<Option<_>>()
            .ok_or("key past the block")?;
        let n = q.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-6);
        // q and -q are the same turn; Halo writes the identity as w = -1.
        let sign = if q[3] < 0.0 { -1.0 } else { 1.0 };
        let [i, j, kz, w] = [sign * q[0] / n, sign * q[1] / n, sign * q[2] / n, sign * q[3] / n];
        if i.abs() > 0.02 || j.abs() > 0.02 {
            return Err("the node tilts as well as turning".into());
        }
        let mut angle = (2.0 * kz.atan2(w)).to_degrees();
        // Continuous with the key before (a quaternion and its negation
        // are the same turn).
        if let Some(&(_, prev)) = out.last() {
            while angle - prev > 180.0 {
                angle -= 360.0;
            }
            while angle - prev < -180.0 {
                angle += 360.0;
            }
        }
        out.push((frame / (frames - 1.0).max(1.0) * period, angle));
    }
    if out.len() < 2 {
        return Err("fewer than two keys".into());
    }
    Ok(Turn { period, keys: out })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A codec 6 block with one node's keys at frames 0, 3 and 20 of 21:
    /// 0, +20 and 0 degrees about +Z over 40 s.
    #[test]
    fn a_turn_reads_its_keys_and_times() {
        let mut d = vec![0u8; 0x48];
        d[0] = 6;
        d[1] = 1;
        let key = |deg: f32| {
            let h = (deg.to_radians() / 2.0) as f32;
            [0.0f32, 0.0, h.sin(), h.cos()]
        };
        // Offsets: keyframe indices at 0x40, keys at 0x48.
        d[0x14..0x18].copy_from_slice(&0x40u32.to_le_bytes());
        d[0x20..0x24].copy_from_slice(&0x48u32.to_le_bytes());
        d[0x30..0x34].copy_from_slice(&3u32.to_le_bytes());
        d[0x40] = 0;
        d[0x41] = 3;
        d[0x42] = 20;
        for (n, deg) in [0.0, 20.0, 0.0].into_iter().enumerate() {
            // The first as Halo writes the identity, (0, 0, 0, -1).
            let sign = if n == 0 { -1.0 } else { 1.0 };
            for c in key(deg).map(|c| c * sign) {
                d.extend_from_slice(&((c * 32767.0).round() as i16).to_le_bytes());
            }
        }
        let t = turn_from_codec(&d, 21.0, 40.0).unwrap();
        assert_eq!(t.keys.len(), 3);
        assert!(t.keys[0].1.abs() < 0.01, "{:?}", t.keys);
        assert!((t.keys[1].0 - 6.0).abs() < 1e-4 && (t.keys[1].1 - 20.0).abs() < 0.01, "{:?}", t.keys);
        assert!((t.keys[2].0 - 40.0).abs() < 1e-4);
        d[2] = 1;
        assert!(turn_from_codec(&d, 21.0, 40.0).is_err(), "a sliding node is refused");
    }
}
