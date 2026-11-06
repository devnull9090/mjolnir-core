//! A rewrite as JSON, for `mjolnir jmad rewrite`.
//!
//! ```json
//! {
//!   "keep": ["root", "body"],
//!   "nodes": [{ "name": "wheel", "parent": "body", "translation": [1, 0, 0] }],
//!   "animations": [{
//!     "name": "any:idle",
//!     "frames": 2,
//!     "nodes": { "wheel": { "rotation": [[0, 0, 0, 1], [0, 0, 1, 0]] } }
//!   }]
//! }
//! ```
//!
//! `keep` names donor nodes, in donor order; each hangs from its nearest kept
//! ancestor. `nodes` follow, by name: `from` continues a donor node under the
//! new name, and without it the node is new and holds the pose given. With
//! neither, the skeleton stays as it is. An animation listed changes only the
//! nodes it names, and the rest keep the donor's frames, or their first frame
//! if `frames` differs. An animation not listed is carried across from the
//! donor. `"reencode": true` writes every member afresh, in codecs 1, 2 and 3.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::clip::{unit, Channel, Pose, Track};
use crate::codec::{Quat, Vec3};
use crate::graph::{AnimationEdit, Graph, NodeSpec, Rewrite};
use crate::Error;

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    #[serde(default)]
    pub keep: Vec<String>,
    #[serde(default)]
    pub nodes: Vec<SpecNode>,
    #[serde(default)]
    pub animations: Vec<SpecAnimation>,
    #[serde(default)]
    pub reencode: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpecNode {
    pub name: String,
    #[serde(default)]
    pub parent: Option<String>,
    #[serde(default)]
    pub from: Option<String>,
    #[serde(default)]
    pub rotation: Option<Quat>,
    #[serde(default)]
    pub translation: Option<Vec3>,
    #[serde(default)]
    pub scale: Option<f32>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpecAnimation {
    pub name: String,
    pub frames: usize,
    #[serde(default)]
    pub nodes: BTreeMap<String, SpecTrack>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpecTrack {
    #[serde(default)]
    pub rotation: Option<Values<Quat>>,
    #[serde(default)]
    pub translation: Option<Values<Vec3>>,
    #[serde(default)]
    pub scale: Option<Values<f32>>,
}

/// One value held throughout, or one a frame.
#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum Values<T> {
    One(T),
    Each(Vec<T>),
}

impl<T: Copy> Values<T> {
    fn channel(&self, tidy: impl Fn(T) -> T) -> Channel<T> {
        match self {
            Values::One(v) => Channel::Static(tidy(*v)),
            Values::Each(v) => Channel::Animated(v.iter().map(|x| tidy(*x)).collect()),
        }
    }
}

impl Spec {
    /// The rewrite this spec describes on a donor graph.
    pub fn resolve(&self, graph: &Graph) -> Result<Rewrite, Error> {
        let old = |name: &str| {
            graph
                .nodes
                .iter()
                .position(|n| n.name == name)
                .ok_or_else(|| Error::Unsupported(format!("the donor has no node {name}")))
        };
        let mut kept = Vec::new();
        for name in &self.keep {
            kept.push(old(name)?);
        }
        if self.keep.is_empty() && self.nodes.is_empty() {
            kept.extend(0..graph.nodes.len());
        }
        kept.sort_unstable();
        kept.dedup();
        let mut nodes: Vec<NodeSpec> = kept
            .iter()
            .map(|&o| {
                let mut up = graph.nodes[o].parent;
                while let Some(p) = up {
                    if let Ok(at) = kept.binary_search(&p) {
                        return (o, Some(at));
                    }
                    up = graph.nodes[p].parent;
                }
                (o, None)
            })
            .map(|(o, parent)| NodeSpec {
                name: graph.nodes[o].name.clone(),
                parent,
                source: Some(o),
                default: None,
            })
            .collect();
        let start = nodes.len();
        for n in &self.nodes {
            let source = n.from.as_deref().map(old).transpose()?;
            let posed = n.rotation.is_some() || n.translation.is_some() || n.scale.is_some();
            let base = source.map_or(Pose::IDENTITY, |o| graph.nodes[o].default);
            let default = (posed || source.is_none()).then(|| Pose {
                rotation: n.rotation.map_or(base.rotation, unit),
                translation: n.translation.unwrap_or(base.translation),
                scale: n.scale.unwrap_or(base.scale),
            });
            nodes.push(NodeSpec {
                name: n.name.clone(),
                parent: None,
                source,
                default,
            });
        }
        let at = |nodes: &[NodeSpec], name: &str| {
            nodes
                .iter()
                .position(|n| n.name == name)
                .ok_or_else(|| Error::Unsupported(format!("no node {name} in the spec")))
        };
        for (k, n) in self.nodes.iter().enumerate() {
            if let Some(p) = &n.parent {
                nodes[start + k].parent = Some(at(&nodes, p)?);
            }
        }
        let mut edits = Vec::new();
        for a in &self.animations {
            let mut tracks = Vec::new();
            for (name, t) in &a.nodes {
                let set = Track {
                    rotation: t
                        .rotation
                        .as_ref()
                        .map_or(Channel::Absent, |v| v.channel(unit)),
                    translation: t
                        .translation
                        .as_ref()
                        .map_or(Channel::Absent, |v| v.channel(|x| x)),
                    scale: t
                        .scale
                        .as_ref()
                        .map_or(Channel::Absent, |v| v.channel(|x| x)),
                };
                tracks.push((at(&nodes, name)?, set));
            }
            edits.push(AnimationEdit {
                name: a.name.clone(),
                frames: a.frames,
                tracks,
            });
        }
        Ok(Rewrite {
            nodes,
            edits,
            reencode: self.reencode,
        })
    }
}
