"""Tests for the weekly update tool's pure parts."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import weekly_update as wu


class WeeklyUpdateTests(unittest.TestCase):
    def test_newest_weekly_date_ignores_other_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            blog = Path(folder)
            (blog / "2026-11-03-week.md").write_text(
                "# A\n\n**Summary:** s\n**Tags:** weekly-update, maps\n", encoding="utf-8"
            )
            (blog / "2026-11-10-other.md").write_text(
                "# B\n\n**Summary:** s\n**Tags:** maps\n", encoding="utf-8"
            )
            (blog / "2026-11-12-not-weekly-update.md").write_text(
                "# C\n\n**Summary:** s\n**Tags:** not-weekly-update\n", encoding="utf-8"
            )
            self.assertEqual(wu.newest_weekly_date(blog), "2026-11-03")

    def test_newest_weekly_date_none(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(wu.newest_weekly_date(Path(folder)))

    def test_doc_urls_map_source_files_to_routes(self):
        docs = {
            "notes": [{"slug": "bots", "sourcePath": "docs/bots.md"}],
            "guides": [{"slug": "forge-guide", "sourcePath": "docs/forge_guide.md"}],
        }
        self.assertEqual(wu.doc_urls(docs), {
            "docs/bots.md": "/docs/notes/bots",
            "docs/forge_guide.md": "/docs/guides/forge-guide",
        })

    def test_x_length_counts_a_link_as_23(self):
        link = "https://mjolnircore.com/blog/a-very-long-slug-indeed-for-this-post"
        self.assertEqual(wu.x_length(f"Hello {link}"), 6 + 23)

    def test_known_issues_reads_only_that_section(self):
        text = (
            "# Title\n\n### Fixed\n\n- **Not this.** A fix.\n\n"
            "### Known issues\n\n- **Only on one PC.** Untested.\n  More.\n"
            "- **Wraps over\n  two lines.** Not final.\n\n### Later\n\n- **Not this either.**\n"
        )
        self.assertEqual(wu.known_issues(text), ["Only on one PC.", "Wraps over two lines."])
        self.assertEqual(wu.known_issues("# Title\n"), [])

    def test_playtest_markdown_names_the_day_in_mst(self):
        start = dt.datetime(2026, 11, 8, 1, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(
            wu.playtest_markdown(start),
            f'[Saturday, November 7, 6 PM MST]({wu.PLAYTEST_LINK} "2026-11-08T01:00:00Z")',
        )

    def test_playtest_markdown_keeps_minutes(self):
        start = dt.datetime(2026, 12, 13, 1, 30, tzinfo=dt.timezone.utc)
        self.assertIn("Saturday, December 12, 6:30 PM MST", wu.playtest_markdown(start))

    def test_check_playtest_passes_a_full_section(self):
        start = dt.datetime(2026, 11, 8, 1, 0, tzinfo=dt.timezone.utc)
        text = f"## What to test\n\n{wu.playtest_markdown(start)}\n{wu.TWITCH_LINK}\n"
        self.assertEqual(wu.check_playtest(text, dt.date(2026, 11, 6)), [])

    def test_check_playtest_takes_the_same_evening(self):
        # A Saturday post: 6 PM MST that day is already Sunday in UTC.
        start = dt.datetime(2026, 11, 8, 1, 0, tzinfo=dt.timezone.utc)
        text = f"## What to test\n\n{wu.playtest_markdown(start)}\n{wu.TWITCH_LINK}\n"
        self.assertEqual(wu.check_playtest(text, dt.date(2026, 11, 7)), [])

    def test_check_playtest_names_what_is_missing(self):
        self.assertEqual(len(wu.check_playtest("Nothing here.", dt.date(2026, 11, 6))), 4)

    def test_check_playtest_refuses_last_weeks_time(self):
        start = dt.datetime(2026, 11, 8, 1, 0, tzinfo=dt.timezone.utc)
        text = f"## What to test\n\n{wu.playtest_markdown(start)}\n{wu.TWITCH_LINK}\n"
        problems = wu.check_playtest(text, dt.date(2026, 11, 13))
        self.assertEqual(len(problems), 1)
        self.assertIn("is not the one after", problems[0])


if __name__ == "__main__":
    unittest.main()
