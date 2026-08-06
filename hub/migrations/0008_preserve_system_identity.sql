-- Migration number: 0008 	 2026-08-06
-- Keep service identities out of the human moderator reset.
--
-- 0007 cleared every elevated role before seating devnull, on the
-- assumption that elevated meant "a person someone appointed". It does not:
-- `system:mjolnir-core` is the Discord-less identity that owns the
-- first-party script/native mod pages, created as 'admin' by the code-mod
-- sync (src/lib/api/codesync.ts). That upsert's ON CONFLICT touches only
-- updated_at, so a demotion there is permanent — nothing would ever put the
-- role back.
--
-- Restore it, and scope the rule properly: system identities are addressed
-- by a `system:` discord_id prefix, never hold a seat on the moderation
-- queue (they cannot sign in — there is no Discord account behind them),
-- and are not what a moderator reset is aimed at.

UPDATE users SET role = 'admin', updated_at = datetime('now')
  WHERE discord_id LIKE 'system:%' AND role <> 'admin';
