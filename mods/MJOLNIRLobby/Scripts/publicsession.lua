-- Public session identity for Discord. A listing is never proof of membership:
-- guests also need a recent message from the host of their current game world.
local Session = {}
Session.__index = Session
Session.HOST_TTL = 45
Session.MESSAGE_TTL = 12
Session.LIST_TTL = 40

function Session.validId(id)
    return type(id) == "string" and #id >= 1 and #id <= 64 and id:match("^[A-Za-z0-9%-]+$") ~= nil
end

function Session.new()
    return setmetatable({ generation = 0 }, Session)
end

function Session:clear()
    self.generation = self.generation + 1
    self.id, self.received, self.checked, self.listing = nil, nil, nil, nil
    self.checking, self.nextCheck = false, 0
end

function Session:worldChanged(world)
    if world ~= self.world then
        self.world = world
        self.blockedWorld = nil
        self:clear()
        return true
    end
    return false
end

function Session:joining(id, now)
    self:clear()
    self.blockedWorld = nil
    self.pending, self.pendingUntil = id, now + 60
end

function Session:leave()
    self:clear()
    self.pending, self.pendingUntil = nil, nil
    self.blockedWorld = self.world
end

function Session:receive(fields, now)
    if self.blockedWorld and self.blockedWorld == self.world then return end
    local id = fields[1]
    if self.pending and now > self.pendingUntil then self.pending = nil end
    if self.pending and id ~= self.pending then return end
    if not Session.validId(id) then self:clear(); return end
    if id ~= self.id then self:clear(); self.id = id end
    self.pending, self.pendingUntil = nil, nil
    self.received = now
    self.joinable = fields[2] == "1"
    self.players = tonumber(fields[3])
    self.maxPlayers = tonumber(fields[4])
end

-- The generation closes the race where a hub response arrives after a leave,
-- another join, a host switch, or world travel.
function Session:check(now, request)
    if not self.id or not self.received or now - self.received > Session.MESSAGE_TTL then return end
    if self.checking or now < (self.nextCheck or 0) then return end
    self.checking = true
    self.nextCheck = now + 30
    local generation, id = self.generation, self.id
    request(function(lobbies, answeredAt)
        if generation ~= self.generation or id ~= self.id then return end
        self.checking = false
        self.checked, self.listing = answeredAt, nil
        for _, lobby in ipairs(lobbies or {}) do
            if lobby.id == id then self.listing = lobby; break end
        end
    end)
end

function Session:guest(now)
    local row = self.listing
    if not (self.id and self.received and now - self.received <= Session.MESSAGE_TTL
        and self.checked and now - self.checked <= Session.LIST_TTL and row) then return nil end
    local count, cap = self.players, self.maxPlayers
    if not (count and cap and count >= 1 and count <= 16 and count % 1 == 0 and cap >= 1 and cap <= 16 and cap % 1 == 0) then return nil end
    return { id = self.id, players = count, maxPlayers = cap,
        joinable = self.joinable and count < cap and row.state ~= "full"
            and (row.state == "open" or row.state == "in_game")
            and type(row.players) == "number" and type(row.max_players) == "number"
            and row.players < row.max_players }
end

function Session.host(host, info, now, online, jip)
    if not (host.public and Session.validId(host.id) and host.confirmed
        and now - host.confirmed <= Session.HOST_TTL and online and info) then return nil end
    local count, cap = math.max(1, info.players or 1), host.maxPlayers
    return { id = host.id, players = count, maxPlayers = cap,
        joinable = count < cap and (not info.in_game or jip) }
end

return Session
