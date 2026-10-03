//! `mjolnir megalo` — write Megalo game variants (docs/re/megalo_engine.md)
//! the simulation can load from a `.mglo` file.

use std::path::PathBuf;

use anyhow::{Context, Result};
use blam_megalo::Variant;
use clap::{Args, Subcommand, ValueEnum};

#[derive(Args)]
pub struct MegaloArgs {
    #[command(subcommand)]
    pub command: MegaloCommand,
}

#[derive(Subcommand)]
pub enum MegaloCommand {
    /// Write a variant as the simulation's decoder reads it.
    Write(WriteArgs),
    /// Read a variant back and print what it holds.
    Read {
        /// The `.mglo` file.
        file: PathBuf,
    },
}

#[derive(Clone, Copy, ValueEnum)]
pub enum Mode {
    /// No rules: players spawn, nothing scores.
    Empty,
    /// Free-for-all Slayer: a kill scores 1; the round ends at the score to win.
    Slayer,
    /// Interpreter smoke test: every player scores 1 every tick.
    Tick,
    /// Capture the Flag (CE rules): flags on the map's `ctf_flag_return`
    /// stands; carry the enemy's to your own while yours is home.
    Ctf,
}

#[derive(Args)]
pub struct WriteArgs {
    #[arg(long, value_enum, default_value = "slayer")]
    pub mode: Mode,
    /// Score to win (default 25; 3 captures for CTF).
    #[arg(long)]
    pub score: Option<u16>,
    /// Rounds in a game (1..=31). An end of round before the last resets
    /// the round in place; the last ends the game, and the game's own return
    /// to the menu then drops every fireteam client. MJOLNIR's matches are
    /// one round: at its end MJOLNIRHud shows the final standings and the
    /// host takes the fireteam back to the lobby itself, so the default
    /// keeps the game from ever ending on its own
    /// (docs/multiplayer_postgame.md).
    #[arg(long, default_value_t = 31)]
    pub rounds: u8,
    /// CTF: the flag's index in `multiplayer_object_type_list` (the entry
    /// tools/level/build_ctf_flag.sh adds).
    #[arg(long, default_value_t = 18)]
    pub flag_type: u16,
    /// CTF: seconds a dropped flag lies before it resets.
    #[arg(long, default_value_t = 30)]
    pub reset_seconds: u16,
    /// CTF: raise marker incidents through the capture check (diagnostic).
    #[arg(long)]
    pub debug_capture: bool,
    /// Halo CE health packs (blam_megalo::powerups): the pack's index in
    /// `multiplayer_object_type_list` (the entry
    /// tools/level/build_ctf_flag.sh adds).
    #[arg(long, default_value_t = 19)]
    pub health_type: u16,
    /// Seconds before a taken health pack comes back.
    #[arg(long, default_value_t = 30)]
    pub health_respawn_seconds: u16,
    /// How close a player must come to a health pack, in feet (ten to a
    /// world unit).
    #[arg(long, default_value_t = 8)]
    pub health_reach_feet: i16,
    /// Leave health packs out.
    #[arg(long)]
    pub no_health_packs: bool,
    /// Simulation ticks per second (the CTF reset counts ticks).
    #[arg(long, default_value_t = 30)]
    pub tick_rate: u16,
    #[arg(long)]
    pub out: PathBuf,
}

pub fn run(a: MegaloArgs) -> Result<()> {
    match a.command {
        MegaloCommand::Write(w) => {
            let v = match w.mode {
                Mode::Empty => Variant::empty(w.score.unwrap_or(25)),
                Mode::Slayer => Variant::slayer(w.score.unwrap_or(25)),
                Mode::Tick => Variant::tick(w.score.unwrap_or(25)),
                Mode::Ctf => Variant::ctf(blam_megalo::ctf::Ctf {
                    flag_type: w.flag_type,
                    score_to_win: w.score.unwrap_or(3),
                    reset_ticks: i16::try_from(u32::from(w.reset_seconds) * u32::from(w.tick_rate))
                        .context("--reset-seconds times --tick-rate is past 32767 ticks")?,
                    debug: w.debug_capture,
                }),
            };
            let v = Variant {
                rounds: w.rounds,
                ..v
            };
            let ticks = |seconds: u16, what: &str| {
                i16::try_from(u32::from(seconds) * u32::from(w.tick_rate))
                    .with_context(|| format!("{what} times --tick-rate is past 32767 ticks"))
            };
            let v = if w.no_health_packs || matches!(w.mode, Mode::Empty | Mode::Tick) {
                v
            } else {
                v.with_health_packs(blam_megalo::powerups::HealthPacks {
                    object_type: w.health_type,
                    respawn_ticks: ticks(w.health_respawn_seconds, "--health-respawn-seconds")?,
                    reach_feet: w.health_reach_feet,
                })
                .map_err(|e| anyhow::anyhow!("{e}"))?
            };
            let bytes = v.write().map_err(|e| anyhow::anyhow!("{e}"))?;
            // Read back through the decoder's grammar before anything ships.
            Variant::read(&bytes).map_err(|e| anyhow::anyhow!("reads back wrong: {e}"))?;
            std::fs::write(&w.out, &bytes)
                .with_context(|| format!("writing {}", w.out.display()))?;
            println!(
                "wrote {} ({} bytes): {} condition(s), {} action(s), {} trigger(s), score to win {}, {} round(s)",
                w.out.display(),
                bytes.len(),
                v.conditions.len(),
                v.actions.len(),
                v.triggers.len(),
                v.score_to_win,
                v.rounds
            );
            Ok(())
        }
        MegaloCommand::Read { file } => {
            let bytes =
                std::fs::read(&file).with_context(|| format!("reading {}", file.display()))?;
            let v = Variant::read(&bytes).map_err(|e| anyhow::anyhow!("{e}"))?;
            println!("{v:#?}");
            Ok(())
        }
    }
}
