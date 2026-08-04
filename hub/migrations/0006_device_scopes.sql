-- Migration number: 0006 	 2026-08-02
-- Let a pairing client ask for the scopes it needs.
--
-- 0004 minted every paired key with one hardcoded scope list, chosen for the
-- launcher: read, rate, comment. The tag editor publishes, so it needs
-- `mods:write`, and the alternative to asking for it here is what the editor
-- shipped with — a key the user mints by hand on the account page and pastes
-- into a text box. That is not the safer option: a hand-made key is whatever
-- scopes the user happened to tick, usually never expires, and travels
-- through the clipboard. A paired key is narrow, dated, named, and revocable.
--
-- The scopes a client asked for are recorded at handshake time and are what
-- approval mints. Storing them here rather than deriving them at approval is
-- what lets the approval page tell the user what they are about to grant —
-- and with `mods:write` in the list, that sentence is the whole defence.
--
-- Existing rows predate the column and can only be launcher handshakes, so
-- they get the launcher's scopes. Live handshakes expire within ten minutes
-- of this running either way.

ALTER TABLE device_codes
  ADD COLUMN scopes TEXT NOT NULL DEFAULT 'mods:read ratings:write comments:write';
