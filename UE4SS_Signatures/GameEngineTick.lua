-- GameEngineTick.lua
-- Required by UE4SS when FName_Constructor.lua is present.
-- Matches UGameEngine::Tick function at RVA 0x5F9D060.
-- Uses a long AOB from the function body to ensure uniqueness.

function Register()
    -- Bytes from GameEngineTick function (RVA 0x5F9D060)
    -- Using 32 bytes for uniqueness
    return "0C 0A 4D 85 D2 74 25 66 41 83 38 2E 74 0E 49 83 C0 02 4C 3B C1 75 F0 49 8B C1 EB 24 4D 2B C1 49"
end

function OnMatchFound(MatchAddress)
    return MatchAddress
end
