-- Migration number: 0004 	 2026-08-02
-- Device pairing, so the desktop launcher can act as a signed-in user.
--
-- The launcher has no browser session and must never ask for a Discord
-- password, so it pairs the way TVs and consoles do: it starts a handshake,
-- shows a short code, and the user approves that code on mjolnircore.com
-- while already signed in. Approval mints an ordinary scoped API key; from
-- then on the launcher is just another API-key client.
--
-- Two secrets meet here and are treated differently:
--   device_code — long, generated for the device, never displayed. Only its
--                 SHA-256 is stored, like api_keys.
--   user_code   — short, read aloud off a screen and typed into a browser.
--                 Stored plainly because it must be matched by what the user
--                 types, and it is worthless after ten minutes.
--
-- granted_key holds the minted key between approval and the launcher's next
-- poll — the one moment the platform stores a usable key. The delivering
-- poll clears it in the same statement that reads it.

CREATE TABLE device_codes (
  device_code_hash TEXT PRIMARY KEY,
  user_code TEXT UNIQUE NOT NULL,
  client_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'denied')),
  -- Who approved it; null while pending.
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  api_key_id TEXT REFERENCES api_keys(id) ON DELETE CASCADE,
  granted_key TEXT,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_device_codes_user_code ON device_codes(user_code);
CREATE INDEX idx_device_codes_expiry ON device_codes(expires_at);
