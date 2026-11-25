-- Extra modes share a descriptor across the lobby, loader and presentation.
-- Trusted shipped data only; this does not implement arbitrary hub game types.
return {
    warfare = {
        id = "warfare", engine = "koth", family = "warfare", slot = 3,
        name = "PELICAN WARFARE", title = "Pelican Warfare", teams = true,
        description = "Deploy from Pelicans. Capture three sites to score for Red or Blue. Respawn at your permanent home base.",
        scoreHeading = "CONTROL", toWin = 500, unit = "control", stat = "objectiveScore",
        authoritativeTeams = true, teamOnlyScore = true,
        icon = "Koth", maps = { PWR = true },
        postgameSameMode = true,
        -- No events.json row: the loader stays silent at the first spawn,
        -- and MJOLNIRHud's warfare_voice.lua announces "Pelican Warfare!"
        -- (it said "King of the Hill" before).
        vehicleMode = "koth", startEvent = "warfare_game_start",
        lockScore = true, -- the generated native script and variant share its threshold
        fixedOptions = {
            score = { value = 500, text = "500", label = "CONTROL TO WIN",
                help = "Each uncontested owned site gives one team control point per second." },
            time_limit = { value = 0, text = "20 MINUTES OF COMBAT",
                help = "The combat clock begins after insertion. The highest control score wins at the limit." },
            respawn = { value = 5, text = "5 SECONDS", help = "Respawn at your permanent team base after five seconds." },
            suicide_penalty = { value = 0, text = "NONE", help = "All deaths use the same five-second respawn." },
        },
        -- These are structural rules, not lobby overrides. The mode owns
        -- its combat-only clock; base time_limit must remain disabled.
        fixedSettings = { time_limit = 0, lives = 0, team_lives = 0, respawn_growth = 0,
            respawn_seconds = 5, suicide_seconds = 0, betrayal_seconds = 0 },
    },
}
