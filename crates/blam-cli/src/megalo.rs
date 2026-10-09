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
    /// A Megalo label the map's "hide unless megalo required" objects must
    /// carry to be placed (repeatable): an object filter on the label, which
    /// the script itself never uses. CE's vehicle sets per game type
    /// (docs/ce_map_conversion.md, "Vehicle sets").
    #[arg(long = "require-label", value_name = "LABEL")]
    pub require_labels: Vec<String>,
    /// Put CE's vehicle set labels (`ce_<type>_<rank>`, VEHICLE_SET_TYPES x
    /// 1..=VEHICLE_SET_RANKS) in the string table, and write
    /// `<out>.layout.json` beside the variant: the bit its object filters
    /// begin at, the filters it has, and each label's string index, from
    /// which MJOLNIRLevelLoader adds a map's vehicle set filters when a
    /// match starts.
    #[arg(long)]
    pub vehicle_label_pool: bool,
    #[command(flatten)]
    pub base: BaseArgs,
    #[arg(long)]
    pub out: PathBuf,
}

/// The base options a host can change (docs/host_game_settings.md), each
/// left at MJOLNIR's default when not given.
#[derive(Args)]
pub struct BaseArgs {
    /// Minutes before the round ends (0: no limit).
    #[arg(long)]
    pub time_limit: Option<u8>,
    /// Sudden death, stored plus one (0: unlimited, 1: none, n: n-1 s).
    #[arg(long)]
    pub sudden_death_raw: Option<u8>,
    /// Lives per round (0: unlimited; at most 63).
    #[arg(long)]
    pub lives: Option<u8>,
    /// Lives per team (0: unlimited; at most 127).
    #[arg(long)]
    pub team_lives: Option<u8>,
    /// Seconds before a respawn (default 5).
    #[arg(long)]
    pub respawn_seconds: Option<u8>,
    /// Seconds added after a suicide (default 5).
    #[arg(long)]
    pub suicide_seconds: Option<u8>,
    /// Seconds added after killing a teammate (default 5).
    #[arg(long)]
    pub betrayal_seconds: Option<u8>,
    /// Seconds added to each successive respawn (at most 15).
    #[arg(long)]
    pub respawn_growth: Option<u8>,
    /// Social options' team changing field (u2).
    #[arg(long)]
    pub team_changing: Option<u8>,
    /// Social options' five flags as one number (u5; order unverified).
    #[arg(long)]
    pub social_flags: Option<u8>,
    /// What the map variant may place (u6; default 0b011111).
    #[arg(long)]
    pub map_flags: Option<u8>,
    /// Every player's trait, `name=value` (repeatable; names in
    /// blam_megalo::variant::TRAITS, 0 = unchanged).
    #[arg(long = "trait", value_name = "NAME=VALUE")]
    pub traits: Vec<String>,
    /// A respawn trait, `name=value` (repeatable).
    #[arg(long = "respawn-trait", value_name = "NAME=VALUE")]
    pub respawn_traits: Vec<String>,
    /// Seconds the respawn traits last (at most 63).
    #[arg(long)]
    pub respawn_traits_seconds: Option<u8>,
}

fn set_traits(t: &mut blam_megalo::variant::Traits, pairs: &[String]) -> Result<()> {
    for pair in pairs {
        let (name, value) = pair
            .split_once('=')
            .with_context(|| format!("{pair}: expected NAME=VALUE"))?;
        let value: u8 = value
            .parse()
            .with_context(|| format!("{pair}: the value is not a number"))?;
        t.set(name, value)
            .map_err(|e| anyhow::anyhow!("{pair}: {e}"))?;
    }
    Ok(())
}

impl BaseArgs {
    fn apply(&self, b: &mut blam_megalo::variant::BaseOptions) -> Result<()> {
        let fields = [
            (self.time_limit, &mut b.time_limit),
            (self.sudden_death_raw, &mut b.sudden_death_raw),
            (self.lives, &mut b.lives),
            (self.team_lives, &mut b.team_lives),
            (self.respawn_seconds, &mut b.respawn_seconds),
            (self.suicide_seconds, &mut b.suicide_seconds),
            (self.betrayal_seconds, &mut b.betrayal_seconds),
            (self.respawn_growth, &mut b.respawn_growth),
            (self.team_changing, &mut b.team_changing),
            (self.social_flags, &mut b.social_flags),
            (self.map_flags, &mut b.map_flags),
            (self.respawn_traits_seconds, &mut b.respawn_traits_seconds),
        ];
        for (value, field) in fields {
            if let Some(v) = value {
                *field = v;
            }
        }
        set_traits(&mut b.player_traits, &self.traits)?;
        set_traits(&mut b.respawn_traits, &self.respawn_traits)
    }
}

/// Object filters the simulation holds (see `--require-label`).
pub const MAX_FILTERS: usize = 16;

/// CE's vehicle set categories, as tools/level/gen_ce_level.py labels them.
pub const VEHICLE_SET_TYPES: [&str; 7] = [
    "warthog", "rwarthog", "scorpion", "ghost", "banshee", "turret", "other",
];
/// Ranks per category and team (`ce_<type>_<rank>`); a map's further ones
/// share the last.
pub const VEHICLE_SET_RANKS: u8 = 10;

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
            let mut v = Variant {
                rounds: w.rounds,
                ..v
            };
            if matches!(w.mode, Mode::Slayer | Mode::Ctf) {
                v = v.with_time_limit();
            }
            w.base.apply(&mut v.base)?;
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
            let mut v = v;
            for spec in &w.require_labels {
                // `LABEL` or `LABEL@TEAM` (0-based team: 0 red, 1 blue).
                let (label, team) = match spec.split_once('@') {
                    Some((l, t)) => (
                        l,
                        Some(
                            t.parse::<u8>()
                                .with_context(|| format!("{spec}: team must be a number"))?,
                        ),
                    ),
                    None => (spec.as_str(), None),
                };
                let label = &label.to_string();
                let s = match v.strings.iter().position(|s| s == label) {
                    Some(i) => i,
                    None => {
                        v.strings.push(label.clone());
                        v.strings.len() - 1
                    }
                };
                let s = u8::try_from(s).context("too many strings for a label")?;
                let f = blam_megalo::variant::Filter { label: s, team };
                if !v.filters.contains(&f) {
                    v.filters.push(f);
                }
            }
            // The format counts to 31, but the simulation holds 16: 17 put
            // every object out of play and lost the GPU device (Death
            // Island, 2026-10-08); 9 were fine.
            let mut pool = serde_json::Map::new();
            if w.vehicle_label_pool {
                for t in VEHICLE_SET_TYPES {
                    for r in 1..=VEHICLE_SET_RANKS {
                        let label = format!("ce_{t}_{r}");
                        let i = match v.strings.iter().position(|s| *s == label) {
                            Some(i) => i,
                            None => {
                                v.strings.push(label.clone());
                                v.strings.len() - 1
                            }
                        };
                        pool.insert(label, serde_json::json!(i));
                    }
                }
                if v.strings.len() > 127 {
                    anyhow::bail!("{} strings; the table holds at most 127", v.strings.len());
                }
            }
            if v.filters.len() > MAX_FILTERS {
                anyhow::bail!(
                    "{} object filters; the simulation holds at most {MAX_FILTERS}",
                    v.filters.len()
                );
            }
            let (bytes, filters_at) = v.write_layout().map_err(|e| anyhow::anyhow!("{e}"))?;
            if w.vehicle_label_pool {
                let layout = serde_json::json!({
                    "filters_at": filters_at,
                    "max_filters": MAX_FILTERS,
                    "filters": v.filters.iter().map(|f| serde_json::json!({"label": f.label, "team": f.team})).collect::<Vec<_>>(),
                    "labels": pool,
                });
                let path = w.out.with_extension("layout.json");
                std::fs::write(&path, serde_json::to_string_pretty(&layout)?)
                    .with_context(|| format!("writing {}", path.display()))?;
            }
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
