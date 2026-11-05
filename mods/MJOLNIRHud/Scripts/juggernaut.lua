-- MJOLNIR HUD: who the Juggernaut is.
--
-- `new_juggernaut` names them (cause), or says the slot is free (no cause).
-- Everyone sees a plasma beacon on them, and they read "YOU ARE THE
-- JUGGERNAUT" under the score. Only their index is
-- kept: `players` is walked afresh from the game state each update, so no actor
-- outlives the tick that read it (a stored biped crashes once it is freed).

local Juggernaut = {}

--- One match's marker. Scripts/hill.lua gives the drawing.
function Juggernaut.new(Hill)
    local self = Hill.field("mjolnir_juggernaut")

    --- The new Juggernaut, nobody for no player. True when someone new took it.
    function self.named(index)
        if type(index) ~= "number" or index < 0 then index = nil end
        if index == self.it then return false end
        self.it = index
        return index ~= nil
    end

    --- `players` lists { index, at } for each one with a body.
    function self.tick(now, pc, hidden, me, players)
        if hidden or not self.it then return self.hide() end
        pcall(function()
            local world = self.worldOf(pc)
            if not world then return end
            self.ensureLine(pc)
            local at
            for _, p in ipairs(players and players() or {}) do
                if p.index == self.it then at = p.at end
            end
            if not at then return self.hide() end
            self.pillar(world, now, at)
            self.paint(self.it == me and "you" or "other", now)
            if self.it == me then
                self.say("YOU ARE THE JUGGERNAUT")
            else
                self.hideLine()
            end
        end)
    end

    return self
end

return Juggernaut
