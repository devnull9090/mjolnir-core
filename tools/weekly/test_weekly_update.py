"""Tests for the weekly update tool's pure parts."""

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


if __name__ == "__main__":
    unittest.main()
