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
pub mod ctf;
pub mod powerups;
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
}
