-- MJOLNIR HUD: the score bars, number pops and medal callouts
-- (docs/multiplayer_hud.md).
--
-- Like the feed's rows (Scripts/feed.lua), every value here is a function of
-- the time alone: a target and when it was set, eased toward. The per-frame
-- hook and the poll both draw from it.

local Anim = {}

Anim.BAR = 0.45       -- a bar's fill easing to a new score
Anim.POP = 0.32       -- a number growing and settling when it changes
Anim.POP_SCALE = 0.35
Anim.CALL_IN = 0.22
Anim.CALL_HOLD = 1.9  -- a medal on its own; a queue moves faster
Anim.CALL_QUICK = 1.15
Anim.CALL_OUT = 0.35

local function clamp01(p)
    if p < 0 then return 0 elseif p > 1 then return 1 end
    return p
end

local function easeOut(p)
    p = clamp01(p)
    local q = 1 - p
    return 1 - q * q * q
end

--- Overshoots a little before settling (the medal's arrival).
local function easeBack(p)
    p = clamp01(p)
    local c = 1.7
    local q = p - 1
    return 1 + (c + 1) * q * q * q + c * q * q
end

function Anim.new()
    return { bars = {}, pops = {}, calls = {}, call = nil }
end

--------------------------------------------------------------------------------
-- Bars
--------------------------------------------------------------------------------

local function barAt(b, t)
    local p = (t - b.at) / Anim.BAR
    if p >= 1 then return b.to end
    return b.from + (b.to - b.from) * easeOut(p)
end

--- Sets bar `key` to `frac` (0..1) from now; the first value is shown at once.
function Anim.bar(state, key, frac, t)
    frac = clamp01(frac or 0)
    local b = state.bars[key]
    if not b then
        state.bars[key] = { from = frac, to = frac, at = t - Anim.BAR }
        return
    end
    if b.to == frac then return end
    b.from, b.to, b.at = barAt(b, t), frac, t
end

function Anim.barAt(state, key, t)
    local b = state.bars[key]
    return b and barAt(b, t) or 0
end

--------------------------------------------------------------------------------
-- Pops
--------------------------------------------------------------------------------

--- Value `value` for pop `key`: a change makes it pop. The first value does
--- not.
function Anim.value(state, key, value, t)
    local p = state.pops[key]
    if not p then
        state.pops[key] = { value = value, at = t - Anim.POP }
        return
    end
    if p.value == value then return end
    p.value, p.at = value, t
end

function Anim.scale(state, key, t)
    local p = state.pops[key]
    if not p then return 1 end
    local k = clamp01((t - p.at) / Anim.POP)
    if k >= 1 then return 1 end
    -- Up fast, down slower.
    local up = 0.25
    if k < up then return 1 + Anim.POP_SCALE * easeOut(k / up) end
    return 1 + Anim.POP_SCALE * (1 - easeOut((k - up) / (1 - up)))
end

--------------------------------------------------------------------------------
-- Callouts (the local player's medals, in the middle of the screen)
--------------------------------------------------------------------------------

--- Queues { title, sub, glyph, color }. A burst never queues more than three.
function Anim.callout(state, item, t)
    if #state.calls >= 3 then table.remove(state.calls, 1) end
    state.calls[#state.calls + 1] = item
    Anim.nextCall(state, t)
end

--- Starts the next queued callout when the current one is done.
function Anim.nextCall(state, t)
    local c = state.call
    if c and t < c.endAt then
        -- A medal waiting cuts the one showing short (never under CALL_QUICK).
        -- A cut only ever brings the end nearer: one that came after the
        -- quick time used to set the end to t + CALL_OUT on every frame, so
        -- the callout never ended and the medals behind it never came up
        -- (a Killing Spree just after a Triple Kill, #242).
        if #state.calls > 0 and c.endAt - c.at > Anim.CALL_QUICK + Anim.CALL_OUT then
            c.endAt = math.min(c.endAt, math.max(t + Anim.CALL_OUT, c.at + Anim.CALL_QUICK + Anim.CALL_OUT))
        end
        return false
    end
    local item = table.remove(state.calls, 1)
    if not item then
        local ended = c ~= nil
        state.call = nil
        return ended
    end
    item.at = t
    item.endAt = t + (#state.calls > 0 and Anim.CALL_QUICK or Anim.CALL_HOLD) + Anim.CALL_OUT
    item.fresh = true
    state.call = item
    return true
end

--- The callout showing, its scale and opacity; nil when none is.
function Anim.callPose(state, t)
    local c = state.call
    if not c then return nil end
    local pin = (t - c.at) / Anim.CALL_IN
    local scale = 1.45 - 0.45 * easeBack(pin)
    local alpha = easeOut(pin * 1.4)
    local out = (t - (c.endAt - Anim.CALL_OUT)) / Anim.CALL_OUT
    if out > 0 then
        alpha = alpha * (1 - clamp01(out))
        scale = scale * (1 - 0.06 * clamp01(out))
    end
    return c, scale, alpha
end

--------------------------------------------------------------------------------

--- Whether anything is still moving at `t`.
function Anim.busy(state, t)
    if state.call or #state.calls > 0 then return true end
    for _, b in pairs(state.bars) do
        if t - b.at < Anim.BAR then return true end
    end
    for _, p in pairs(state.pops) do
        if t - p.at < Anim.POP then return true end
    end
    return false
end

return Anim
