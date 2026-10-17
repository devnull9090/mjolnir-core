-- MJOLNIR HUD: `mjolnir_feed_demo`, a preview of the kill feed, the medal
-- callout and the score bars in a match, with no other player needed
-- (docs/multiplayer_hud.md). It draws through the HUD's own code with
-- made-up names; no tally, score or match record changes.

local Demo = {}

local T = "Blam.DamageReporting.Type."

--- { at (seconds from the start), what, ... }. `you` lines name the local
--- player.
Demo.STEPS = {
    { 0.0, "kill", "Noble Six", "Kat", T .. "AssaultRifle", 0 },
    { 0.7, "kill", "YOU", "Jorge", T .. "SniperRifle", 1 },
    { 1.0, "medal", "YOU", "Double Kill", "Medal", "medal" },
    { 1.0, "bars", 0.72, 18, 0.40, 10 },
    { 1.6, "event", "Emile", "Joined", "joined", "joined the game" },
    { 2.3, "kill", "Carter", "Jun", T .. "Melee", 0 },
    { 3.0, "kill", "Jun", "Noble Six", T .. "Ghost", 3 },
    { 3.7, "kill", "Kat", "YOU", T .. "PlasmaGrenade", 4 },
    { 4.4, "event", "Jorge", "Fall", "words", "fell to their death" },
    { 5.1, "kill", "YOU", "Carter", T .. "Shotgun", 0 },
    { 5.4, "medal", "YOU", "Triple Kill", "Medal", "medal" },
    { 5.4, "bars", 0.80, 20, 0.40, 10 },
    { 6.1, "event", "Emile", "Kicked", "kicked", "was kicked" },
    { 6.8, "kill", "Kat", "Emile", T .. "RocketLauncher", 0 },
    { 7.5, "medal", "Kat", "Killing Spree", "Spree", "spree" },
    -- The respawn countdown, as after a death (display only).
    { 8.2, "respawn", "dead" },
    { 9.2, "respawn", "tick" },
    { 10.2, "respawn", "tick" },
    { 11.2, "respawn", "tick" },
    { 12.2, "respawn", "alive" },
}

--- How long the demo holds the score bars before the real scores return.
Demo.SECONDS = 14

return Demo
