-- MJOLNIR HUD: where a racer goes next.
--
-- No Megalo waypoint reaches Unreal (docs/game_modes.md, B4), so as with the
-- hill the level file lists the flags in rank order (`race_flags`: x, y, z and
-- radius, Unreal cm, tools/level/ce_objectives.py) and the variant says which
-- one counts. `checkpoint_reached` with the local player as cause gives that
-- player's next rank; Rally's, with no cause, gives the live flag for everyone.
-- This draws that flag as Scripts/hill.lua draws a hill, and one line under the
-- score: "LAP 1 OF 3 / FLAG 3 OF 9, 42 M AHEAD".
--
-- Whether an incident's value reaches a client is unproven for this one, so a
-- Race that hears nothing a few seconds after the first spawn keeps its own
-- count: rank 0 first, on to the next when the pawn stands on the flag.

local Race = {}

local EVERY = 0.2 -- seconds between updates
local GRACE_SECONDS = 4 -- after the first spawn, how long the script has to speak

--- The flags in a level file's text, in rank order.
function Race.parse(Hill, text)
    return Hill.parse(text, "race_flags")
end

--- The words for flag `rank` (from 0) of `count`, from Hill.bearing's answers.
function Race.flagLine(rank, count, rally, inside, metres, way, level)
    local name = rally and "FLAG" or string.format("FLAG %d OF %d", rank + 1, count)
    if inside then return name .. (level == "" and " HERE" or level) end
    return string.format("%s%s %d M %s%s", name, rally and "" or ",", metres, way, level)
end

--- "LAP 1 OF 3" after `done` laps of `limit`.
function Race.lapLine(done, limit)
    if limit <= 0 then return string.format("LAP %d", done + 1) end
    return string.format("LAP %d OF %d", math.min(done + 1, limit), limit)
end

--- One match's marker. `read` gives a map's level file text; `rally` is one
--- live flag for everyone rather than each player's own next rank.
function Race.new(Hill, read, rally)
    local self = Hill.field("mjolnir_race")
    self.flags, self.rank, self.next, self.rally = {}, 0, 0, rally == true
    self.laps = 0 -- counted here, when the script is not heard

    function self.start(code)
        self.flags = Race.parse(Hill, read(code))
        self.rank, self.next, self.laps = 0, 0, 0
        self.heard, self.passed, self.spawnedAt = nil, nil, nil
        self.reset()
        return #self.flags
    end

    --- `checkpoint_reached`, for the player `me`.
    function self.checkpoint(cause, rank, me)
        if not self.rally and cause ~= me then return end
        if type(rank) ~= "number" or not self.flags[rank + 1] then return end
        self.rank, self.heard = rank, true
    end

    --- The local count: only while the script has said nothing.
    local function mirror(now, at)
        self.spawnedAt = self.spawnedAt or now
        if self.heard or self.rally or now - self.spawnedAt < GRACE_SECONDS then return end
        if not Hill.on(self.flags[self.rank + 1], at) then return end
        if self.rank == 0 and self.passed then self.laps = self.laps + 1 end
        self.rank = (self.rank + 1) % #self.flags
        if self.rank == 0 then self.passed = true end
    end

    --- `done` is the laps the board shows of `limit`.
    function self.tick(now, pc, hidden, done, limit)
        if #self.flags == 0 or now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            local world = self.worldOf(pc)
            if not world then return end
            self.ensureLine(pc)
            local pawn = pc.Pawn
            local at = pawn and pawn:IsValid() and pawn:K2_GetActorLocation() or nil
            if at then mirror(now, at) end
            local flag = self.flags[self.rank + 1]
            self.draw(world, now, self.rank, flag)
            self.paint(self.rally and "empty" or "you", now)
            if not at then return self.hideLine() end
            local line = Race.flagLine(self.rank, #self.flags, self.rally,
                Hill.bearing(flag, at, pc:GetControlRotation().Yaw))
            if not self.rally then line = Race.lapLine(math.max(done, self.laps), limit) .. " / " .. line end
            self.say(line)
        end)
    end

    return self
end

return Race
