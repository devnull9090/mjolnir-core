-- FUObjectHashTables::Get() for Halo Campaign Evolved (Steam).
--
-- History, because this file has now failed twice for opposite reasons:
--
--   1. The upstream signature baked two RIP-relative displacements in as literal
--      bytes (`39 05 12 39 C5 09`, `48 8D 05 B1 CA 74 09`). Those move every
--      build, so a game update broke the scan outright.
--   2. The fix wildcarded them. That made the pattern relocation-safe but left
--      only the *shape* of a compiler idiom:
--
--        sub rsp,0x28 / mov rax,gs:[0x58] / mov ecx,<slot> / mov rax,[rax]
--        mov eax,[rcx+rax] / cmp [rip+d],eax / jg +0xC / lea rax,[rip+d] / ret
--
--      That is the thread-safe accessor MSVC emits for *every* function-local
--      static. On CU3 it matches 195 distinct functions. UE4SS logs an address
--      and starts fine; it is simply not guaranteed to be the right one.
--
-- Ambiguity is the worse failure: a missing signature is loud, a wrong one is a
-- crash somewhere else entirely. So this anchors on a call site instead, which
-- is what upstream's `gamepass/GUObjectHashTables.lua` does, and decodes the
-- rel32 to reach the function.
--
--   mov  [rsp+0xa8], r12           ; four register spills at fixed offsets
--   mov  [rsp+0xa0], r13
--   mov  [rsp+0x98], r14
--   mov  [rsp+0x90], r15
--   jne  <rel32>                   ; wildcarded
--   mov  byte ptr [rip+<disp>], 1  ; wildcarded
--   call FUObjectHashTables::Get() ; rel32 wildcarded, decoded below
--   mov  rbx, rax
--   mov  rcx, [rax]
--   mov  rdi, [rcx+0x80]           ; dereferences the returned singleton
--
-- 63 bytes, 51 of them literal, matching exactly once in CU3's .text.
--
-- Identification of the callee as FUObjectHashTables::Get(), by static analysis
-- rather than by symbol:
--   * it is the function-local-static accessor idiom above;
--   * it returns a .data global referenced from 105 sites - the next most
--     referenced of the 195 candidates has 17;
--   * it is called from 493 sites, consistent with every object hash add,
--     remove and find path;
--   * it sits alongside the other UObject core functions this repo resolves
--     (FName::FName at RVA 0x36fd130, GUObjectArray at RVA 0x379c0f0).
--
-- Verified on CU3 (2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3): the match
-- lands at VA 0x1436801e3 and the decode below yields 0x1435993b0.
--
-- Check this after every game update with:
--   python tools/pe/aob_scan.py "<Win64>/HaloCampaignEvolved.exe"
-- which fails on "matched nothing" and on "matched more than once" alike.
function Register()
    return "4C 89 A4 24 A8 00 00 00 4C 89 AC 24 A0 00 00 00 4C 89 B4 24 98 00 00 00 4C 89 BC 24 90 00 00 00 0F 85 ? ? ? ? C6 05 ? ? ? ? 01 E8 ? ? ? ? 48 8B D8 48 8B 08 48 8B B9 80 00 00 00"
end

-- UE4SS calls the resolved address, so this returns the callee, not the match.
function OnMatchFound(MatchAddress)
    local CallInstruction = MatchAddress + 0x2D
    local NextInstruction = CallInstruction + 0x5
    local DisplacementAddress = CallInstruction + 0x1
    return NextInstruction + DerefToInt32(DisplacementAddress)
end
