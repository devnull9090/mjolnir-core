-- FName_Constructor.lua
-- Matches the MJOLNIR marker at the start of the injected FName constructor trampoline.
-- The injected trampoline is registered in the PE Exception Table via RtlAddFunctionTable.

function Register()
    return "0F 1F 84 00 4D 4A 4F 4C 0F 1F 84 00 4E 49 52 21"
end

function OnMatchFound(MatchAddress)
    return MatchAddress
end
