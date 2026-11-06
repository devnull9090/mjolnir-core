//! `model_animation_graph` tags: read them down to their frames, write them
//! back byte for byte, and rewrite them for a skeleton of any size.
//!
//! - [`codec`]: the frame blocks a member stores (static, raw, packed).
//! - [`member`]: one animation's record and data segments.
//! - [`resource`]: a `tag resource groups` body.
//! - [`clip`]: an animation as poses, and the encoder to and from members.
//! - [`graph`]: the tag as a whole, and [`graph::rewrite`].
//! - [`mod@child`]: a graph cut down to a few animations over a parent.
//! - [`spec`]: the JSON form of a rewrite.
//!
//! The format as far as it is established is in `docs/jmad_format.md`.

pub mod child;
pub mod clip;
pub mod codec;
pub mod graph;
pub mod member;
pub mod resource;
pub mod spec;

pub use child::{child, Child};
pub use clip::{Channel, Clip, Pose, Skeleton, Track};
pub use graph::{rewrite, Graph, NodeSpec, Rewrite};
pub use member::Member;
pub use resource::Group;
pub use spec::Spec;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("tag: {0}")]
    Tag(String),
    #[error("format: {0}")]
    Format(String),
    #[error("unsupported: {0}")]
    Unsupported(String),
}
