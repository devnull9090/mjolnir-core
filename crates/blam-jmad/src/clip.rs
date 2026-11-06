//! An animation as poses: what each node does on each frame, independent of
//! how a member stores it.
//!
//! [`Clip::read`] turns a member into a clip and [`Clip::write`] turns a clip
//! into a member. Writing is stable: a clip read back from a member it wrote
//! writes the same bytes again.

use crate::codec::{pack, unpack, Frames, Quat, Rotations, StaticPose, Vec3, PACKED, RAW};
use crate::member::{
    has_bit, seg, set_bit, Animated, Member, NodeFlags, ObjectPose, ObjectSpace, NODE_BOUND_OPAQUE,
    SEGMENTS,
};
use crate::Error;

/// One channel of one node.
#[derive(Debug, Clone, PartialEq)]
pub enum Channel<T> {
    /// The animation leaves this channel at the node's default.
    Absent,
    Static(T),
    Animated(Vec<T>),
}

impl<T: Copy> Channel<T> {
    /// The channel's value on a frame, or `fallback` if it has none.
    pub fn at(&self, frame: usize, fallback: T) -> T {
        match self {
            Channel::Absent => fallback,
            Channel::Static(v) => *v,
            Channel::Animated(v) => v.get(frame).or(v.last()).copied().unwrap_or(fallback),
        }
    }

    fn first(&self) -> Channel<T> {
        match self {
            Channel::Animated(v) => v.first().map_or(Channel::Absent, |x| Channel::Static(*x)),
            Channel::Static(v) => Channel::Static(*v),
            Channel::Absent => Channel::Absent,
        }
    }

    fn moves(&self) -> bool {
        matches!(self, Channel::Animated(_))
    }

    fn present(&self) -> bool {
        !matches!(self, Channel::Absent)
    }
}

/// What one node does through an animation.
#[derive(Debug, Clone, PartialEq)]
pub struct Track {
    pub rotation: Channel<Quat>,
    pub translation: Channel<Vec3>,
    pub scale: Channel<f32>,
}

impl Track {
    /// A node that holds its default pose without saying so.
    pub const ABSENT: Track = Track {
        rotation: Channel::Absent,
        translation: Channel::Absent,
        scale: Channel::Absent,
    };

    pub fn holding(pose: Pose) -> Track {
        Track {
            rotation: Channel::Static(pose.rotation),
            translation: Channel::Static(pose.translation),
            scale: Channel::Static(pose.scale),
        }
    }

    fn pose(&self, frame: usize, default: Pose) -> Pose {
        Pose {
            rotation: self.rotation.at(frame, default.rotation),
            translation: self.translation.at(frame, default.translation),
            scale: self.scale.at(frame, default.scale),
        }
    }
}

/// A node's pose relative to its parent.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pose {
    pub rotation: Quat,
    pub translation: Vec3,
    pub scale: f32,
}

impl Pose {
    pub const IDENTITY: Pose = Pose {
        rotation: [0.0, 0.0, 0.0, 1.0],
        translation: [0.0; 3],
        scale: 1.0,
    };

    /// This pose, relative to its parent, placed under the parent's pose.
    pub fn under(self, parent: Pose) -> Pose {
        let moved = rotate(parent.rotation, self.translation.map(|c| c * parent.scale));
        Pose {
            rotation: multiply(parent.rotation, unit(self.rotation)),
            translation: std::array::from_fn(|k| parent.translation[k] + moved[k]),
            scale: parent.scale * self.scale,
        }
    }

    fn object(self) -> ObjectPose {
        let (q, t) = (self.rotation, self.translation);
        [q[0], q[1], q[2], q[3], t[0], t[1], t[2], self.scale]
    }
}

/// The rotation scaled to unit length; a zero rotation becomes the identity.
pub fn unit(q: Quat) -> Quat {
    let n = q.iter().map(|c| c * c).sum::<f32>().sqrt();
    if n > 0.0 {
        q.map(|c| c / n)
    } else {
        [0.0, 0.0, 0.0, 1.0]
    }
}

fn multiply(a: Quat, b: Quat) -> Quat {
    let [ax, ay, az, aw] = a;
    let [bx, by, bz, bw] = b;
    [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]
}

fn cross(a: Vec3, b: Vec3) -> Vec3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn rotate(q: Quat, v: Vec3) -> Vec3 {
    let axis = [q[0], q[1], q[2]];
    let once = cross(axis, v);
    let twice = cross(axis, once);
    std::array::from_fn(|k| v[k] + 2.0 * (q[3] * once[k] + twice[k]))
}

/// A skeleton as far as posing needs it.
#[derive(Debug, Clone, Copy)]
pub struct Skeleton<'a> {
    pub parents: &'a [Option<usize>],
    pub defaults: &'a [Pose],
}

impl Skeleton<'_> {
    /// Every node's pose in object space, given each node's pose relative to
    /// its parent.
    pub fn object_poses(&self, local: &[Pose]) -> Vec<Pose> {
        fn place(
            i: usize,
            parents: &[Option<usize>],
            local: &[Pose],
            out: &mut [Option<Pose>],
        ) -> Pose {
            if let Some(p) = out[i] {
                return p;
            }
            let pose = match parents[i] {
                Some(parent) => local[i].under(place(parent, parents, local, out)),
                None => local[i].under(Pose::IDENTITY),
            };
            out[i] = Some(pose);
            pose
        }
        let mut out = vec![None; local.len()];
        (0..local.len())
            .map(|i| place(i, self.parents, local, &mut out))
            .collect()
    }
}

/// An animation in poses, with the per-frame data that does not depend on the
/// skeleton.
#[derive(Debug, Clone, PartialEq)]
pub struct Clip {
    pub frames: usize,
    pub nodes: Vec<Track>,
    /// The member's movement kind and its per-frame root movement.
    pub movement_kind: u8,
    pub movement: Vec<u8>,
    /// Twelve bytes a frame. Empty writes zeros.
    pub pill: Vec<u8>,
    pub blend_screen: Vec<u8>,
    /// The segments of [`NODE_BOUND_OPAQUE`], in that order, as bytes: IK
    /// chain transforms and weights, among others. The tag's rows index into
    /// them, and they hold the frame count, so they stay with the frames.
    pub node_bound: [Vec<u8>; NODE_BOUND_OPAQUE.len()],
}

impl Clip {
    /// A clip of `frames` frames with no root movement.
    pub fn new(frames: usize, nodes: Vec<Track>) -> Clip {
        Clip {
            frames,
            nodes,
            movement_kind: 0,
            movement: Vec::new(),
            pill: Vec::new(),
            blend_screen: Vec::new(),
            node_bound: Default::default(),
        }
    }

    /// Whether the clip carries segments that only hold for its frame count.
    pub fn has_node_bound_data(&self) -> bool {
        self.node_bound.iter().any(|b| !b.is_empty())
    }

    /// Decode a member. The frames come from the uncompressed copy, or from
    /// the compressed slot if it has none and this crate reads its codec.
    pub fn read(m: &Member) -> Result<Clip, Error> {
        let frames = m.frames.max(0) as usize;
        let source = m.raw.as_ref().or(match &m.animated {
            Animated::Frames(f) => Some(f),
            Animated::Opaque(_) => None,
        });
        let flags = &m.animated_flags;
        let moving = flags
            .rotation
            .iter()
            .chain(&flags.translation)
            .chain(&flags.scale)
            .any(|w| *w != 0);
        if source.is_none() && moving {
            return Err(Error::Unsupported(format!(
                "no decodable frames (codec {})",
                m.animated.codec()
            )));
        }
        let mut nodes = vec![Track::ABSENT; m.nodes as usize];
        let mut next = [0usize; 3];
        let mut live = [0usize; 3];
        for (i, track) in nodes.iter_mut().enumerate() {
            if has_bit(&m.static_flags.rotation, i) {
                track.rotation = Channel::Static(m.static_pose.rotations[next[0]].map(unpack));
                next[0] += 1;
            }
            if has_bit(&m.static_flags.translation, i) {
                track.translation = Channel::Static(m.static_pose.translations[next[1]]);
                next[1] += 1;
            }
            if has_bit(&m.static_flags.scale, i) {
                track.scale = Channel::Static(m.static_pose.scales[next[2]]);
                next[2] += 1;
            }
            let Some(f) = source else { continue };
            if has_bit(&flags.rotation, i) {
                track.rotation = Channel::Animated(
                    (0..frames)
                        .map(|k| f.rotations.get(live[0] * frames + k))
                        .collect(),
                );
                live[0] += 1;
            }
            if has_bit(&flags.translation, i) {
                track.translation = Channel::Animated(
                    f.translations[live[1] * frames..(live[1] + 1) * frames].to_vec(),
                );
                live[1] += 1;
            }
            if has_bit(&flags.scale, i) {
                track.scale =
                    Channel::Animated(f.scales[live[2] * frames..(live[2] + 1) * frames].to_vec());
                live[2] += 1;
            }
        }
        Ok(Clip {
            frames,
            nodes,
            movement_kind: m.movement_kind,
            movement: m.opaque[seg::MOVEMENT].clone(),
            pill: m.opaque[seg::PILL].clone(),
            blend_screen: m.opaque[seg::BLEND_SCREEN].clone(),
            node_bound: NODE_BOUND_OPAQUE.map(|s| m.opaque[s].clone()),
        })
    }

    /// Encode the clip as a member: the static pose (codec 1), the moving
    /// nodes in codec 3 and again uncompressed (codec 2), and, when
    /// `object_space` is set, object-space frames worked out from `skeleton`.
    pub fn write(
        &self,
        skeleton: Skeleton<'_>,
        object_space: bool,
        data_tail: [u8; 16],
    ) -> Result<Member, Error> {
        let n = self.nodes.len();
        if n == 0 || n > 255 {
            return Err(Error::Unsupported(format!(
                "{n} nodes (a member holds 1 to 255)"
            )));
        }
        if self.frames == 0 || self.frames > i16::MAX as usize {
            return Err(Error::Unsupported(format!("{} frames", self.frames)));
        }
        let f = self.frames;
        let mut static_flags = NodeFlags::new(n);
        let mut animated_flags = NodeFlags::new(n);
        let mut pose = StaticPose {
            quality: [0.0, 0.0],
            rotations: Vec::new(),
            translations: Vec::new(),
            scales: Vec::new(),
        };
        let (mut rotations, mut translations, mut scales) = (Vec::new(), Vec::new(), Vec::new());
        let (mut rotating, mut translating, mut scaling) = (0, 0, 0);
        let long = |name: &str, i: usize, len: usize| {
            Error::Unsupported(format!("node {i}'s {name} has {len} frames, the clip {f}"))
        };
        for (i, t) in self.nodes.iter().enumerate() {
            match &t.rotation {
                Channel::Absent => {}
                Channel::Static(q) => {
                    set_bit(&mut static_flags.rotation, i);
                    pose.rotations.push(q.map(pack));
                }
                Channel::Animated(v) if v.len() == f => {
                    set_bit(&mut animated_flags.rotation, i);
                    rotations.extend_from_slice(v);
                    rotating += 1;
                }
                Channel::Animated(v) => return Err(long("rotation", i, v.len())),
            }
            match &t.translation {
                Channel::Absent => {}
                Channel::Static(v) => {
                    set_bit(&mut static_flags.translation, i);
                    pose.translations.push(*v);
                }
                Channel::Animated(v) if v.len() == f => {
                    set_bit(&mut animated_flags.translation, i);
                    translations.extend_from_slice(v);
                    translating += 1;
                }
                Channel::Animated(v) => return Err(long("translation", i, v.len())),
            }
            match &t.scale {
                Channel::Absent => {}
                Channel::Static(v) => {
                    set_bit(&mut static_flags.scale, i);
                    pose.scales.push(*v);
                }
                Channel::Animated(v) if v.len() == f => {
                    set_bit(&mut animated_flags.scale, i);
                    scales.extend_from_slice(v);
                    scaling += 1;
                }
                Channel::Animated(v) => return Err(long("scale", i, v.len())),
            }
        }
        let frames_of = |codec: u8, quality: [f32; 2], rotations: Rotations| Frames {
            codec,
            quality,
            frames: f,
            rotation_nodes: rotating,
            translation_nodes: translating,
            scale_nodes: scaling,
            rotations,
            translations: translations.clone(),
            scales: scales.clone(),
        };
        let packed = rotations.iter().map(|q: &Quat| q.map(pack)).collect();
        let mut opaque: [Vec<u8>; SEGMENTS] = Default::default();
        opaque[seg::MOVEMENT] = self.movement.clone();
        opaque[seg::PILL] = if self.pill.is_empty() {
            vec![0; 12 * f]
        } else {
            self.pill.clone()
        };
        opaque[seg::BLEND_SCREEN] = self.blend_screen.clone();
        for (s, bytes) in NODE_BOUND_OPAQUE.iter().zip(&self.node_bound) {
            opaque[*s] = bytes.clone();
        }
        Ok(Member {
            animation_index: 0,
            checksum: 0,
            frames: f as i16,
            nodes: n as u8,
            movement_kind: self.movement_kind,
            data_tail,
            static_pose: pose,
            animated: Animated::Frames(frames_of(PACKED, [0.0, 1.0], Rotations::Packed(packed))),
            static_flags,
            animated_flags,
            raw: Some(frames_of(
                RAW,
                [0.0, 0.0],
                Rotations::Float(rotations.clone()),
            )),
            object_space: object_space.then(|| self.as_stored().object_space(skeleton)),
            opaque,
        })
    }

    /// The clip at `frames` frames with `tracks` set over it. Channels left
    /// alone keep their frames if the count is unchanged, and hold their
    /// first frame if not, when the data that runs per frame goes too.
    pub fn edited(&self, frames: usize, tracks: &[(usize, Track)]) -> Clip {
        let mut clip = self.clone();
        if frames != self.frames {
            for t in &mut clip.nodes {
                t.rotation = t.rotation.first();
                t.translation = t.translation.first();
                t.scale = t.scale.first();
            }
            clip.frames = frames;
            clip.movement_kind = 0;
            clip.movement.clear();
            clip.pill.clear();
            clip.blend_screen.clear();
            clip.node_bound = Default::default();
        }
        for (node, t) in tracks {
            let to = &mut clip.nodes[*node];
            if t.rotation.present() {
                to.rotation = t.rotation.clone();
            }
            if t.translation.present() {
                to.translation = t.translation.clone();
            }
            if t.scale.present() {
                to.scale = t.scale.clone();
            }
        }
        clip
    }

    /// The clip as a member keeps it: static rotations are 16 bit, and
    /// object-space frames must agree with what is read back.
    fn as_stored(&self) -> Clip {
        let mut clip = self.clone();
        for t in &mut clip.nodes {
            if let Channel::Static(q) = &mut t.rotation {
                *q = q.map(|c| unpack(pack(c)));
            }
        }
        clip
    }

    /// Object-space frames by forward kinematics, for every node the clip
    /// poses. Every shipped base animation matches this to within 6e-4;
    /// overlays store something else (see `docs/jmad_format.md`).
    pub fn object_space(&self, skeleton: Skeleton<'_>) -> ObjectSpace {
        let mut mask = [0u32; 8];
        let posed: Vec<usize> = (0..self.nodes.len())
            .filter(|&i| {
                let t = &self.nodes[i];
                t.rotation.present() || t.translation.present() || t.scale.present()
            })
            .collect();
        for &i in &posed {
            set_bit(&mut mask, i);
        }
        let per_frame: Vec<Vec<Pose>> = (0..self.frames)
            .map(|f| {
                let local: Vec<Pose> = self
                    .nodes
                    .iter()
                    .zip(skeleton.defaults)
                    .map(|(t, d)| t.pose(f, *d))
                    .collect();
                skeleton.object_poses(&local)
            })
            .collect();
        let poses = posed
            .iter()
            .flat_map(|&i| per_frame.iter().map(move |p| p[i].object()))
            .collect();
        ObjectSpace {
            frames: self.frames,
            poses,
            mask,
        }
    }

    /// The clip on a new skeleton. `chains[i]` lists the old nodes new node
    /// `i` stands for, top first, ending at its source: more than one when
    /// nodes between it and its new parent are gone, whose motion it then
    /// takes on. An empty chain is a node the old skeleton did not have,
    /// which holds `defaults[i]`.
    pub fn remap(&self, chains: &[Vec<usize>], old_defaults: &[Pose], defaults: &[Pose]) -> Clip {
        let nodes = chains
            .iter()
            .zip(defaults)
            .map(|(chain, default)| match chain.as_slice() {
                [] => Track::holding(*default),
                [one] => self.nodes[*one].clone(),
                _ => self.compose(chain, old_defaults),
            })
            .collect();
        Clip {
            nodes,
            ..self.clone()
        }
    }

    fn compose(&self, chain: &[usize], defaults: &[Pose]) -> Track {
        let pose_at = |f: usize| {
            chain
                .iter()
                .fold(None, |above: Option<Pose>, &i| {
                    let local = self.nodes[i].pose(f, defaults[i]);
                    Some(match above {
                        Some(parent) => local.under(parent),
                        None => Pose {
                            rotation: unit(local.rotation),
                            ..local
                        },
                    })
                })
                .unwrap_or(Pose::IDENTITY)
        };
        let tracks = || chain.iter().map(|&i| &self.nodes[i]);
        let turns = tracks().any(|t| t.rotation.moves());
        let grows = tracks().any(|t| t.scale.moves());
        let shifts = turns || grows || tracks().any(|t| t.translation.moves());
        let all: Vec<Pose> = (0..self.frames.max(1)).map(pose_at).collect();
        Track {
            rotation: if turns {
                Channel::Animated(all.iter().map(|p| p.rotation).collect())
            } else {
                Channel::Static(all[0].rotation)
            },
            translation: if shifts {
                Channel::Animated(all.iter().map(|p| p.translation).collect())
            } else {
                Channel::Static(all[0].translation)
            },
            scale: if grows {
                Channel::Animated(all.iter().map(|p| p.scale).collect())
            } else {
                Channel::Static(all[0].scale)
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TAIL: [u8; 16] = [
        0x10, 0, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0,
    ];

    fn turn(deg: f32) -> Quat {
        let h = deg.to_radians() / 2.0;
        [0.0, 0.0, h.sin(), h.cos()]
    }

    fn clip() -> Clip {
        Clip::new(
            3,
            vec![
                Track {
                    rotation: Channel::Animated(vec![turn(0.0), turn(45.0), turn(90.0)]),
                    translation: Channel::Static([0.0; 3]),
                    scale: Channel::Static(1.0),
                },
                Track::holding(Pose {
                    translation: [1.0, 0.0, 0.0],
                    ..Pose::IDENTITY
                }),
                Track {
                    rotation: Channel::Static(turn(10.0)),
                    translation: Channel::Animated(vec![
                        [0.0, 1.0, 0.0],
                        [0.0, 2.0, 0.0],
                        [0.0, 3.0, 0.0],
                    ]),
                    scale: Channel::Animated(vec![1.0, 1.25, 1.5]),
                },
                Track::ABSENT,
            ],
        )
    }

    const PARENTS: [Option<usize>; 4] = [None, Some(0), Some(1), Some(1)];
    const DEFAULTS: [Pose; 4] = [Pose::IDENTITY; 4];

    fn skeleton() -> Skeleton<'static> {
        Skeleton {
            parents: &PARENTS,
            defaults: &DEFAULTS,
        }
    }

    #[test]
    fn writing_is_stable_through_the_bytes() {
        let once = clip().write(skeleton(), true, TAIL).unwrap();
        let (record, blob) = once.write();
        let read = Member::read(&record, &blob).unwrap();
        assert_eq!(read, once);
        let again = Clip::read(&read)
            .unwrap()
            .write(skeleton(), true, TAIL)
            .unwrap();
        assert_eq!(again.write(), (record, blob));
    }

    #[test]
    fn a_member_says_which_nodes_are_where() {
        let m = clip().write(skeleton(), false, TAIL).unwrap();
        assert_eq!(m.animated_flags.rotation, vec![0b0001]);
        assert_eq!(m.static_flags.rotation, vec![0b0110]);
        assert_eq!(m.animated_flags.translation, vec![0b0100]);
        assert_eq!(m.static_flags.translation, vec![0b0011]);
        assert_eq!(m.animated_flags.scale, vec![0b0100]);
        assert!(m.object_space.is_none());
        assert_eq!(m.opaque[seg::PILL].len(), 36);
    }

    #[test]
    fn object_space_places_children_under_their_parents() {
        let os = clip().object_space(skeleton());
        assert_eq!(os.nodes(), 3);
        // Node 1 sits 1 along x from a root turned 90 degrees on frame 2.
        let p = os.poses[3 + 2];
        assert!((p[4]).abs() < 1e-6 && (p[5] - 1.0).abs() < 1e-6, "{p:?}");
    }

    #[test]
    fn a_dropped_node_hands_its_motion_down() {
        // Node 1 goes: node 2 now hangs from the root and keeps its place.
        let chains = vec![vec![0], vec![1, 2]];
        let parents = [None, Some(0)];
        let defaults = [Pose::IDENTITY; 2];
        let small = clip().remap(&chains, &DEFAULTS, &defaults);
        let big = clip().object_space(skeleton());
        let less = small.object_space(Skeleton {
            parents: &parents,
            defaults: &defaults,
        });
        for f in 0..3 {
            let (a, b) = (big.poses[2 * 3 + f], less.poses[3 + f]);
            for c in 0..8 {
                assert!((a[c] - b[c]).abs() < 1e-5, "frame {f}: {a:?} {b:?}");
            }
        }
    }

    #[test]
    fn a_new_node_holds_its_default() {
        let d = Pose {
            translation: [0.0, 0.0, 2.0],
            ..Pose::IDENTITY
        };
        let c = clip().remap(&[vec![0], vec![]], &DEFAULTS, &[Pose::IDENTITY, d]);
        assert_eq!(c.nodes[1], Track::holding(d));
    }

    #[test]
    fn an_edit_at_another_length_holds_what_it_leaves_alone() {
        let set = Track {
            rotation: Channel::Animated(vec![turn(1.0), turn(2.0)]),
            ..Track::ABSENT
        };
        let c = clip().edited(2, &[(1, set)]);
        assert_eq!(c.frames, 2);
        assert_eq!(c.nodes[0].rotation, Channel::Static(turn(0.0)));
        assert_eq!(
            c.nodes[1].rotation,
            Channel::Animated(vec![turn(1.0), turn(2.0)])
        );
        assert_eq!(c.nodes[1].translation, Channel::Static([1.0, 0.0, 0.0]));
        assert_eq!(c.nodes[3], Track::ABSENT);
    }

    #[test]
    fn an_edit_keeps_the_chain_segments_while_the_frame_count_holds() {
        let mut donor = clip().write(skeleton(), true, TAIL).unwrap();
        let carried = [(8, 3), (9, 452), (10, 132), (14, 7), (16, 5)];
        for (s, len) in carried {
            donor.opaque[s] = (0..len).map(|i| (i + s) as u8).collect();
        }
        let (record, blob) = donor.write();
        let read = Member::read(&record, &blob).unwrap();

        let set = Track {
            rotation: Channel::Static(turn(30.0)),
            ..Track::ABSENT
        };
        let decoded = Clip::read(&read).unwrap();
        let same = decoded.edited(3, &[(1, set.clone())]);
        let written = same.write(skeleton(), true, TAIL).unwrap();
        for (s, _) in carried {
            assert_eq!(written.opaque[s], read.opaque[s], "segment {s}");
        }
        assert_ne!(written.static_pose, read.static_pose);

        let (record, blob) = written.write();
        assert_eq!(Member::read(&record, &blob).unwrap(), written);

        assert!(!decoded.edited(2, &[(1, set)]).has_node_bound_data());
    }

    #[test]
    fn frames_of_the_wrong_length_are_refused() {
        let mut c = clip();
        c.nodes[0].rotation = Channel::Animated(vec![turn(0.0)]);
        assert!(c.write(skeleton(), false, TAIL).is_err());
    }
}
