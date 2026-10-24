//! Megalo game variants: the rules engine behind Halo Reach's multiplayer
//! modes, which the Campaign Evolved simulation still carries and runs
//! (docs/re/megalo_engine.md).
//!
//! A variant reaches the simulation as a bitstream its own decoder reads
//! (HaloSimulation CU4, Megalo vtable slot 5, `0x392a40`), for example from a
//! `<name>.mglo` file its round-reset path loads. This crate writes that
//! bitstream, and reads it back the same way, so a variant can be checked
//! offline before the game ever sees it.

pub mod bits;
pub mod blf;
pub mod ctf;
pub mod dump;
pub mod powerups;
pub mod raw;
pub(crate) mod script;
pub mod variant;

pub use variant::Variant;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("bitstream ended at bit {at}, {want} more bit(s) wanted")]
    Truncated { at: usize, want: u32 },
    #[error("value {value} does not fit {bits} bit(s)")]
    TooWide { value: i64, bits: u32 },
    #[error("not modelled: {0}")]
    Unsupported(String),
    /// The grammar (`grammar/megalo_cu4.json`) is malformed.
    #[error("grammar: {0}")]
    Grammar(String),
    /// The bitstream does not decode under the grammar.
    #[error("{path}: bit {at}: {msg}")]
    Decode {
        path: String,
        at: usize,
        msg: String,
    },
    /// A union selector with no case in the grammar.
    #[error("{path}: bit {at}: {ty} has no case {value}")]
    UnknownCase {
        ty: String,
        value: i64,
        path: String,
        at: usize,
    },
    /// A tree that does not fit its grammar, or a round trip that differs.
    #[error("{path}: {msg}")]
    Mismatch { path: String, msg: String },
    /// A BLF container that does not parse.
    #[error("BLF: {0}")]
    Blf(String),
}
