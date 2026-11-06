-- The Wwise banks a release's archive carries, as its scan saw them: a JSON
-- array of member names, `[]` for none. NULL means the scan predates this
-- column, not that there are none, because a moderator reads this to judge a
-- held release. On mod_releases rather than release_reviews so a trusted
-- author's banks are on record too, and a rescan replaces it.
ALTER TABLE mod_releases ADD COLUMN banks_json TEXT;
