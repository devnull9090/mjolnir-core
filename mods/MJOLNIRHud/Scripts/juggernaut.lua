-- MJOLNIR HUD: who the Juggernaut is, or Reverse Tag's it, or the Stalker.
--
-- `new_juggernaut` names them (cause), or says the slot is free (no cause).
-- Everyone else sees a plasma beacon over them and a marker on the screen,
-- and they read their line ("YOU ARE THE JUGGERNAUT") under the score. Their
-- own screen has no beacon: from their feet up it stood through their camera
-- (playtest 2026-11-07, #351). The Stalker is invisible, so either would undo
-- the mode: they get the line and nobody gets a beacon or a marker. The
-- beacon and the marker follow the holder's actor every frame (Hill.field's
-- track); the update that finds it runs a few times a second. Only their index
-- is kept between updates: `players` is walked afresh from the game state each
-- update, and the actor it gives is checked before each use (a stored biped
-- crashes once it is freed).

local Juggernaut = {}

local MARKER_HEIGHT_CM = 230 -- above the pawn's middle: clear of the head
local BEACON_UP_CM = 150 -- the beacon's foot, above the pawn's middle: over the head

--- One match's marker. Scripts/hill.lua gives the drawing; `holder` is the
--- mode's row (Scripts/scoreboard.lua): { line, unseen }.
function Juggernaut.new(Hill, holder)
    local self = Hill.field("mjolnir_juggernaut")
    local hideAll = self.hide

    function self.hide()
        self.track(nil)
        hideAll()
    end

    --- The new Juggernaut, nobody for no player. True when someone new took it.
    function self.named(index)
        if type(index) ~= "number" or index < 0 then index = nil end
        if index == self.it then return false end
        self.it = index
        return index ~= nil
    end

    --- `players` lists { index, at, actor } for each one with a body.
    function self.tick(now, pc, hidden, me, players)
        if hidden or not self.it then return self.hide() end
        pcall(function()
            local world = self.worldOf(pc)
            if not world then return end
            self.ensureLine(pc)
            local at, actor
            for _, p in ipairs(players and players() or {}) do
                if p.index == self.it then at, actor = p.at, p.actor end
            end
            if not at then return self.hide() end
            if self.it == me then
                self.track(nil)
                self.unpillar()
                self.unmark()
                self.say(holder.line)
                return
            end
            self.hideLine()
            if holder.unseen then
                self.track(nil)
                return self.unmark()
            end
            self.pillar(world, now, at, BEACON_UP_CM)
            self.paint("other", now)
            self.track(actor, MARKER_HEIGHT_CM, BEACON_UP_CM)
            local mine = pc.Pawn
            if not (mine and mine:IsValid()) then return self.unmark() end
            local _, metres, _, level = Hill.bearing({ x = at.X, y = at.Y, z = at.Z, r = 0 },
                mine:K2_GetActorLocation(), 0)
            self.mark(pc, { x = at.X, y = at.Y, z = at.Z + MARKER_HEIGHT_CM }, "other", "Juggernaut",
                Hill.Waypoint and Hill.Waypoint.label(metres, level) or "", now)
        end)
    end

    return self
end

return Juggernaut
