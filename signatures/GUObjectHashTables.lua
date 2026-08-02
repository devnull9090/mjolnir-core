-- FUObjectHashTables::Get() for Halo Campaign Evolved (Steam).
--
-- The upstream signature baked two RIP-relative displacements in as literal
-- bytes (`39 05 12 39 C5 09` and `48 8D 05 B1 CA 74 09`). A displacement is
-- the distance from the instruction to a global, so every shipped build moves
-- it — which is why this scan started failing after a game update while the
-- other three signatures kept resolving.
--
-- Wildcarding the displacements leaves the instruction *shape* as the anchor,
-- which is what actually identifies the function:
--
--   sub  rsp, 0x28
--   mov  rax, gs:[0x58]        ; TLS block
--   mov  ecx, <slot>
--   mov  rax, [rax]
--   mov  eax, [rcx+rax]
--   cmp  [rip+<disp>], eax
--   jg   +0xC
--   lea  rax, [rip+<disp>]     ; the hash tables singleton
--   add  rsp, 0x28
--   ret
--
-- The TLS slot index is wildcarded for the same reason: it depends on how
-- many slots the binary allocates, which is a build-time detail.
function Register()
    return "48 83 EC 28 65 48 8B 04 25 58 00 00 00 B9 ? ? ? ? 48 8B 00 8B 04 01 39 05 ? ? ? ? 7F 0C 48 8D 05 ? ? ? ? 48 83 C4 28 C3"
end

-- UE4SS calls this address, so the match is the function entry itself rather
-- than the singleton it returns.
function OnMatchFound(MatchAddress)
    return MatchAddress
end
