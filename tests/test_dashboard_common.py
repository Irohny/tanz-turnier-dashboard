import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from etl.archiv import archive_pages
from etl.common import (
    ANALYSIS_CACHE_VERSION,
    archive_token,
    cached_analysis,
    cached_pages,
    pair_catalog,
)


class DashboardCacheTests(unittest.TestCase):
    def test_external_import_and_database_replacement_invalidate_cache(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "titel": "First",
            "paare": [{"name": "Ada Muster / Ben Beispiel"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            database = str(Path(temporary) / "test.sqlite")
            archive_pages(database, page["url"], [page])
            first = archive_token(database)
            self.assertEqual(cached_pages(database, first)[0]["titel"], "First")
            archive_pages(database, page["url"], [{**page, "titel": "Second"}])
            second = archive_token(database)
            self.assertNotEqual(first, second)
            self.assertEqual(cached_pages(database, second)[0]["titel"], "Second")
            replacement = Path(temporary) / "replacement.sqlite"
            archive_pages(replacement, page["url"], [{**page, "titel": "Third"}])
            os.replace(replacement, database)
            third = archive_token(database)
            self.assertNotEqual(second, third)
            self.assertEqual(cached_pages(database, third)[0]["titel"], "Third")

    def test_catalogue_and_analysis_reuse_archive_revision(self):
        pair = "Ada Muster / Ben Beispiel"
        pages = [
            {
                "url": "https://example.test/event/ergwert.htm",
                "titel": "01.03.2026 Hgr. D Standard",
                "paare": [{"name": pair}],
                "paar_ergebnisse": [{"paar": pair}],
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            database = str(Path(temporary) / "test.sqlite")
            archive_pages(database, pages[0]["url"], pages)
            token = archive_token(database)
            self.assertEqual(pair_catalog(database, token, pages), ([pair], pair))
            keys = (("https://example.test", "/event/"),)
            with patch(
                "etl.common.build_pair_dashboard", return_value={"ready": True}
            ) as build:
                self.assertEqual(
                    cached_analysis(
                        database, token, pair, keys, pages, ANALYSIS_CACHE_VERSION
                    ),
                    {"ready": True},
                )
                cached_analysis(
                    database, token, pair, keys, pages, ANALYSIS_CACHE_VERSION
                )
                self.assertEqual(build.call_count, 1)

    def test_analysis_cache_rebuilds_after_schema_version_changes(self):
        args = ("schema-test.sqlite", (), "Ada / Ben", (), [])
        cached_analysis.clear()
        self.addCleanup(cached_analysis.clear)
        with patch("etl.common.build_pair_dashboard") as build:
            build.return_value = {"opponent_evidence": [{"title": "Oldenburg"}]}
            old = cached_analysis(*args, analysis_version=1)
            build.return_value = {
                "opponent_evidence": [{"title": "Oldenburg", "city": "Oldenburg"}]
            }
            self.assertEqual(cached_analysis(*args, analysis_version=1), old)
            updated = cached_analysis(*args, analysis_version=2)
            self.assertEqual(updated["opponent_evidence"][0]["city"], "Oldenburg")
            self.assertEqual(build.call_count, 2)


class DashboardThemeTests(unittest.TestCase):
    def test_theme_colors_have_readable_contrast(self):
        config_path = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
        with config_path.open("rb") as file:
            themes = tomllib.load(file)["theme"]

        def luminance(color):
            channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                for value in channels
            ]
            return sum(
                channel * weight
                for channel, weight in zip(
                    linear, (0.2126, 0.7152, 0.0722), strict=True
                )
            )

        def contrast(first, second):
            lower, higher = sorted((luminance(first), luminance(second)))
            return (higher + 0.05) / (lower + 0.05)

        for mode in ("light", "dark"):
            theme = themes[mode]
            for section in (theme, theme["sidebar"]):
                with self.subTest(mode=mode, section=section):
                    for background in ("backgroundColor", "secondaryBackgroundColor"):
                        self.assertGreaterEqual(
                            contrast(section["textColor"], section[background]), 4.5
                        )
                    self.assertGreaterEqual(
                        contrast("#ffffff", section["primaryColor"]), 4.5
                    )
            for color in theme["chartCategoricalColors"]:
                with self.subTest(mode=mode, chart_color=color):
                    for background in ("backgroundColor", "secondaryBackgroundColor"):
                        self.assertGreaterEqual(contrast(color, theme[background]), 3)
