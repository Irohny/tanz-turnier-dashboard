import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest

from app import AUTH_STATE_KEY
from etl.archiv import archive_pages, load_pages
from etl.common import CONTEXT_KEY, archive_token, cached_analysis
from etl.data import build_pair_dashboard

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
TEST_SECRETS = {"auth": {"user": "test-user", "password": "test-password"}}


class DashboardLoginTests(unittest.TestCase):
    def test_missing_auth_secrets_keep_dashboard_locked(self):
        app = AppTest.from_file(APP_PATH)
        app.secrets = {"other": "value"}
        app.run()

        self.assertEqual(app.exception, [])
        self.assertTrue(
            any("Zugang ist nicht konfiguriert" in item.value for item in app.error)
        )
        self.assertNotIn(AUTH_STATE_KEY, app.session_state)

    def test_login_rejects_invalid_and_accepts_valid_credentials(self):
        app = AppTest.from_file(APP_PATH)
        app.secrets = TEST_SECRETS
        app.run()

        next(item for item in app.text_input if item.label == "Benutzer").set_value(
            "test-user"
        )
        next(item for item in app.text_input if item.label == "Passwort").set_value(
            "falsch"
        )
        next(item for item in app.button if item.label == "Anmelden").click().run()

        self.assertTrue(any("nicht korrekt" in item.value for item in app.error))
        next(item for item in app.text_input if item.label == "Passwort").set_value(
            "test-password"
        )
        next(item for item in app.button if item.label == "Anmelden").click().run()

        self.assertEqual(app.exception, [])
        self.assertTrue(app.session_state[AUTH_STATE_KEY])
        self.assertTrue(any(item.label == "Abmelden" for item in app.button))


class DashboardNavigationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = str(Path(temporary.name) / "test.sqlite")
        self.database = database
        pair = "Ada Muster / Ben Beispiel"
        archive_pages(
            database,
            "https://example.test/event/index.htm",
            [
                {
                    "url": "https://example.test/event/ergwert.htm",
                    "titel": "01.03.2026 Hgr. D Standard",
                    "stadt": "Oldenburg",
                    "paare": [
                        {
                            "name": name,
                            "platz_von": index,
                            "platz_bis": index,
                            "verein": (
                                "TSC Beispiel" if name != pair else "Eigener Verein"
                            ),
                        }
                        for index, name in enumerate(
                            [
                                pair,
                                "Eva Beispiel / Tom Muster",
                                "Mia Beispiel / Leo Muster",
                            ],
                            1,
                        )
                    ],
                    "paar_ergebnisse": [
                        {
                            "paar": pair,
                            "runde": "Finale",
                            "feldgroesse": 3,
                            "platzierung_spalten": {"Platz": "1."},
                            "alle_weiteren_spalten": {"Tango | Su": "1,0"},
                        },
                        {
                            "paar": pair,
                            "runde": "Vorrunde",
                            "richter_wertungen": [
                                {
                                    "kuerzel": "A",
                                    "name": "Ada Richter",
                                    "tanz": "Tango",
                                    "rohwert": "X",
                                }
                            ],
                        },
                    ],
                },
                {
                    "url": "https://example.test/event/wert_er.htm",
                    "titel": "01.03.2026 Hgr. D Standard",
                    "paar_ergebnisse": [
                        {
                            "paar": pair,
                            "runde": "Finale",
                            "feldgroesse": 3,
                            "richter_wertungen": [
                                {
                                    "kuerzel": code,
                                    "name": name,
                                    "tanz": "Tango",
                                    "rohwert": value,
                                }
                                for code, name, value in (
                                    ("A", "Ada Richter", "1"),
                                    ("B", "Ben Richter", "3"),
                                )
                            ],
                        }
                    ],
                },
                {
                    "url": "https://example.test/event/tabges.htm",
                    "titel": "01.03.2026 Hgr. D Standard",
                    "alle_paare_erfasst": True,
                    "paar_ergebnisse": [
                        {
                            "paar": name,
                            "runde": "Vorrunde",
                            "feldgroesse": 3,
                            "kreuze_anzahl": crosses,
                            "moegliche_kreuzstimmen": 6,
                            "qualifiziert": qualified,
                            "richteranzahl": 2,
                            "alle_weiteren_spalten": (
                                {"Aufstiegspunkte": "7"} if name == pair else {}
                            ),
                            "richter_kreuze": (
                                [
                                    {
                                        "kuerzel": code,
                                        "name": judge,
                                        "kreuze": count,
                                        "max_kreuze": 3,
                                    }
                                    for code, judge, count in (
                                        ("A", "Ada Richter", 3),
                                        ("B", "Ben Richter", 0),
                                    )
                                ]
                                if name == pair
                                else []
                            ),
                        }
                        for name, crosses, qualified in (
                            (pair, 3, True),
                            ("Eva Beispiel / Tom Muster", 1, False),
                            ("Mia Beispiel / Leo Muster", 2, True),
                        )
                    ]
                    + [
                        {
                            "paar": pair,
                            "runde": "Zwischenrunde",
                            "feldgroesse": 3,
                            "moegliche_kreuzstimmen": None,
                            "richter_kreuze": [
                                {
                                    "kuerzel": "A",
                                    "name": "Ada Richter",
                                    "kreuze": 1,
                                    "max_kreuze": 2,
                                },
                                {
                                    "kuerzel": "C",
                                    "name": "Chris Richter",
                                    "kreuze": 2,
                                },
                            ],
                        }
                    ],
                },
            ],
        )
        database_patch = patch("etl.common.DEFAULT_DATABASE", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        original_from_file = AppTest.from_file

        def authenticated_from_file(*args, **kwargs):
            app = original_from_file(*args, **kwargs)
            app.secrets = TEST_SECRETS
            app.session_state[AUTH_STATE_KEY] = True
            return app

        app_test_patch = patch.object(
            AppTest, "from_file", side_effect=authenticated_from_file
        )
        app_test_patch.start()
        self.addCleanup(app_test_patch.stop)

    def test_analysis_pages_and_aggregated_judge_crosses_are_rendered(self):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        for page in ("dance", "judges", "opponents"):
            app.switch_page(f"dashboard_pages/{page}.py").run()
            self.assertEqual(app.exception, [])
            if page == "judges":
                self.assertTrue(
                    any("Geringe Aussagekraft" in item.value for item in app.warning)
                )
                self.assertTrue(
                    any("Vergleiche" in item.value.columns for item in app.dataframe)
                )
        app.switch_page("dashboard_pages/tournament_archive.py").run()
        self.assertEqual(app.exception, [])
        table = next(
            item
            for item in app.dataframe
            if item.value.index.name == "Runde"
            and item.value.columns.name == "Wertungsrichter"
        )
        matrix = table.value
        self.assertEqual(
            list(matrix.columns), ["Ada Richter", "Ben Richter", "Chris Richter"]
        )
        self.assertEqual(matrix.loc["Vorrunde", "Ada Richter"], "3")
        self.assertEqual(matrix.loc["Vorrunde", "Ben Richter"], "0")
        self.assertEqual(matrix.loc["Zwischenrunde", "Ada Richter"], "1")
        self.assertEqual(matrix.loc["Zwischenrunde", "Ben Richter"], "—")
        self.assertEqual(matrix.loc["Zwischenrunde", "Chris Richter"], "2")
        styles = table.proto.arrow_data.styler.styles
        self.assertIn("#bbf7d0", styles)
        self.assertIn("#fecaca", styles)
        self.assertIn("#dce0cd", styles)
        row = matrix.index.get_loc("Zwischenrunde")
        for judge in ("Ben Richter", "Chris Richter"):
            column = matrix.columns.get_loc(judge)
            self.assertNotIn(f"row{row}_col{column}", styles)
        self.assertFalse(
            any("aggregierte Richter-Kreuzsummen" in info.value for info in app.info)
        )
        self.assertFalse(
            any(
                "gegebene / mögliche Kreuze pro Tanz" in item.value
                for item in app.caption
            )
        )
        self.assertTrue(
            any(
                item.value.index.name == "Wertungsrichter"
                and "Tango" in item.value.columns
                for item in app.dataframe
            )
        )

    def test_selecting_dance_heatmap_cell_shows_its_evidence(self):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/dance.py").run()
        self.assertEqual(app.exception, [])
        heatmap = next(table for table in app.dataframe if table.key == "dance_heatmap")
        assert heatmap.key is not None
        self.assertEqual(heatmap.value.iloc[0, 0], 100)
        app.session_state[heatmap.key] = {"selection": {"cells": [[0, "Tango"]]}}
        app.run()
        self.assertEqual(app.exception, [])
        self.assertTrue(any("Quelle:" in item.value for item in app.caption))
        self.assertTrue(any("auf ganze Prozent" in item.value for item in app.caption))

    def test_club_tables_allow_opponent_style_cell_selection(self):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/clubs.py").run()
        self.assertEqual(app.exception, [])
        club_table = next(
            table
            for table in app.dataframe
            if "Paare" in table.value.columns and "Ihr besser" in table.value.columns
        )
        self.assertIsNotNone(club_table.key)
        app.session_state[club_table.key] = {"selection": {"cells": [[0, "name"]]}}
        app.run()
        self.assertTrue(
            any(
                "Begegnete Paare von TSC Beispiel" in item.value
                for item in app.subheader
            )
        )
        pair_table = next(
            table
            for table in app.dataframe
            if "Begegnungen" in table.value.columns
            and "Letzte Begegnung" in table.value.columns
        )
        self.assertIsNotNone(pair_table.key)
        app.session_state[pair_table.key] = {"selection": {"cells": [[0, "name"]]}}
        app.run()
        self.assertTrue(
            any("Begegnungen mit Eva Beispiel" in item.value for item in app.subheader)
        )

    def test_import_refreshes_shared_context_immediately(self):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
        app.switch_page("dashboard_pages/fetch_results.py").run()
        next(
            widget
            for widget in app.text_input
            if widget.label == "Link zur Ergebnisseite"
        ).set_value("https://example.test/second/index.htm")
        html = """<title>02.03.2026 Hgr. D Standard</title><table>
        <tr><th>Platz</th><th>Paar</th><th>Nr</th></tr>
        <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>1</td></tr></table>"""
        with patch(
            "etl.crawler.crawl",
            return_value={
                "https://example.test/second/ergwert.htm": BeautifulSoup(
                    html, "html.parser"
                )
            },
        ):
            next(
                widget
                for widget in app.button
                if widget.label == "Ergebnisse abrufen und speichern"
            ).click().run()
        self.assertEqual(app.exception, [])
        self.assertTrue(
            any(
                "/second/" in page["url"]
                for page in app.session_state[CONTEXT_KEY]["pages"]
            )
        )
        self.assertTrue(any("Import für" in item.value for item in app.success))
        self.assertEqual(
            app.session_state["dashboard_pair"], "Ada Muster / Ben Beispiel"
        )
        app.date_input[0].set_value((date(2026, 3, 1), date(2026, 3, 2))).run()
        self.assertEqual(len(app.session_state[CONTEXT_KEY]["events"]), 2)

    def test_native_navigation_runs_each_page_script(self):
        entrypoint = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(entrypoint).run()
        self.assertEqual(app.exception, [])

        for page_path in (
            "dashboard_pages/overview.py",
            "dashboard_pages/dance.py",
            "dashboard_pages/judges.py",
            "dashboard_pages/opponents.py",
            "dashboard_pages/clubs.py",
            "dashboard_pages/locations.py",
            "dashboard_pages/data_quality.py",
            "dashboard_pages/tournament_archive.py",
            "dashboard_pages/points.py",
            "dashboard_pages/fetch_results.py",
        ):
            with self.subTest(page=page_path):
                app.switch_page(page_path).run()
                self.assertEqual(app.exception, [])

    def test_points_are_grouped_by_class_discipline_and_point_type(self):
        pair = "Ada Muster / Ben Beispiel"
        for slug, title, values in (
            (
                "second",
                "02.03.2026 Hgr. C Standard",
                {"Aufstiegspunkte": "12", "Sonderpunkte": "4"},
            ),
            ("unknown", "03.03.2026 Standard", {"Aufstiegspunkte": "5"}),
        ):
            base = f"https://example.test/{slug}/"
            archive_pages(
                self.database,
                base + "index.htm",
                [
                    {
                        "url": base + "ergwert.htm",
                        "titel": title,
                        "paare": [{"name": pair, "platz_von": 1, "platz_bis": 1}],
                    },
                    {
                        "url": base + "tabges.htm",
                        "titel": title,
                        "paar_ergebnisse": [
                            {"paar": pair, "alle_weiteren_spalten": values}
                        ],
                    },
                ],
            )
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/points.py").run()
        self.assertEqual(app.exception, [])
        totals = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(totals["Hgr. D · Standard · Aufstiegspunkte"], "7")
        self.assertEqual(totals["Hgr. C · Standard · Aufstiegspunkte"], "12")
        self.assertEqual(totals["Hgr. C · Standard · Sonderpunkte"], "4")
        self.assertTrue(
            any("1 Punkteintrag ohne eindeutige" in item.value for item in app.caption)
        )
        points = next(
            item.value
            for item in app.dataframe
            if "Gespeicherte Punkte" in item.value.columns
        )
        self.assertEqual(len(points), 4)

    def test_filters_persist_across_pages_and_hide_single_class_selector(self):
        pair = "Ada Muster / Ben Beispiel"
        base = "https://example.test/other-class/"
        archive_pages(
            self.database,
            base + "index.htm",
            [
                {
                    "url": base + "ergwert.htm",
                    "titel": "02.03.2026 Hgr. C Standard",
                    "paare": [{"name": pair, "platz_von": 1, "platz_bis": 1}],
                    "paar_ergebnisse": [
                        {
                            "paar": pair,
                            "runde": "Finale",
                            "feldgroesse": 3,
                            "alle_weiteren_spalten": {"Tango | Su": "2,0"},
                        }
                    ],
                }
            ],
        )
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        next(
            widget for widget in app.selectbox if widget.label == "Startgruppe"
        ).set_value("Hgr. D").run()
        self.assertEqual(len(app.session_state[CONTEXT_KEY]["events"]), 1)
        app.switch_page("dashboard_pages/dance.py").run()
        self.assertEqual(app.exception, [])
        self.assertEqual(
            [event["group"] for event in app.session_state[CONTEXT_KEY]["events"]],
            ["Hgr. D"],
        )
        self.assertFalse(app.get("segmented_control"))
        self.assertTrue(any("Startklasse: D" in item.value for item in app.caption))
        next(
            widget for widget in app.selectbox if widget.label == "Startgruppe"
        ).set_value("Alle").run()
        self.assertEqual(len(app.session_state[CONTEXT_KEY]["events"]), 2)
        self.assertTrue(app.get("segmented_control"))

    def test_latest_result_does_not_choose_arbitrarily_on_same_date(self):
        pair = "Ada Muster / Ben Beispiel"
        base = "https://example.test/same-day/"
        archive_pages(
            self.database,
            base + "index.htm",
            [
                {
                    "url": base + "ergwert.htm",
                    "titel": "01.03.2026 Hgr. C Standard",
                    "paare": [{"name": pair, "platz_von": 2, "platz_bis": 2}],
                }
            ],
        )
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        self.assertEqual(app.exception, [])
        latest = next(
            metric for metric in app.metric if metric.label == "Letztes Ergebnis"
        )
        self.assertEqual(latest.value, "Mehrere")

    def test_dark_theme_preserves_readable_judge_table(self):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        )
        app.context["theme"] = "dark"
        app.run()
        app.switch_page("dashboard_pages/judges.py").run()
        self.assertEqual(app.exception, [])
        table = next(
            item
            for item in app.dataframe
            if "Relative Tendenz (Prozentpunkte)" in item.value.columns
        )
        styles = table.proto.arrow_data.styler.styles
        self.assertIn("color: #e5eee7", styles)
        self.assertIn("background-color: #1e3028", styles)
        self.assertNotIn("background-color: #f5f6f1", styles)

    def test_selecting_judge_and_opponent_shows_matching_tournaments(self):
        pair = "Ada Muster / Ben Beispiel"
        pages = load_pages(self.database)
        pages[0]["stadt"] = "Oldenburg"
        archive_pages(self.database, "https://example.test/event/index.htm", pages)
        pages = load_pages(self.database)
        stale = build_pair_dashboard(pages, pair)
        for row in stale["opponent_evidence"]:
            del row["city"]
        with patch("etl.common.build_pair_dashboard", return_value=stale):
            cached_analysis(
                self.database,
                archive_token(self.database),
                pair,
                (("https://example.test", "/event/"),),
                pages,
                analysis_version=1,
            )
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/judges.py").run()
        judge_table = next(
            table
            for table in app.dataframe
            if table.key and table.key.startswith("judge_table_selection_")
        )
        judge = judge_table.value.iloc[0]["Wertungsrichter"]
        judge_table_key = judge_table.key
        assert judge_table_key is not None
        app.session_state[judge_table_key] = {
            "selection": {"cells": [[0, "Wertungsrichter"]]}
        }
        app.run()
        self.assertEqual(app.exception, [])
        self.assertTrue(any(judge in item.value for item in app.subheader))
        meetings = next(
            table.value for table in app.dataframe if "Ort" in table.value.columns
        )
        self.assertEqual(list(meetings["Turnier"]), ["01.03.2026 Hgr. D Standard"])
        self.assertEqual(list(meetings["Ort"]), ["Oldenburg"])

    def test_location_quality_and_club_drilldown_pages(self):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/locations.py").run()
        self.assertEqual(app.exception, [])
        location_table = next(
            table for table in app.dataframe if "Ort" in table.value.columns
        )
        self.assertIn("Oldenburg", list(location_table.value["Ort"]))

        app.switch_page("dashboard_pages/clubs.py").run()
        self.assertEqual(app.exception, [])
        club_table = next(
            table
            for table in app.dataframe
            if table.key and table.key.startswith("club_selection_")
        )
        self.assertIn("TSC Beispiel", list(club_table.value["name"]))
        assert club_table.key is not None
        app.session_state[club_table.key] = {"selection": {"cells": [[0, "name"]]}}
        app.run()
        self.assertEqual(app.exception, [])
        pair_table = next(
            table
            for table in app.dataframe
            if table.key
            and table.key.startswith("club_selection_")
            and "Letzte Begegnung" in table.value.columns
        )
        assert pair_table.key is not None
        app.session_state[pair_table.key] = {"selection": {"cells": [[0, "name"]]}}
        app.run()
        self.assertEqual(app.exception, [])
        meetings = next(
            table.value
            for table in app.dataframe
            if "Gegnerplatz" in table.value.columns
        )
        self.assertEqual(list(meetings["Turnier"]), ["01.03.2026 Hgr. D Standard"])

        app.switch_page("dashboard_pages/data_quality.py").run()
        self.assertEqual(app.exception, [])
        self.assertTrue(
            any("Abdeckung nach Datenart" in item.value for item in app.subheader)
        )

        app.switch_page("dashboard_pages/opponents.py").run()
        opponent_table = next(
            table
            for table in app.dataframe
            if table.key and table.key.startswith("opponent_table_selection_")
        )
        opponent = opponent_table.value.iloc[0]["Paar"]
        opponent_table_key = opponent_table.key
        assert opponent_table_key is not None
        app.session_state[opponent_table_key] = {"selection": {"cells": [[0, "Paar"]]}}
        app.run()
        self.assertEqual(app.exception, [])
        self.assertTrue(any(opponent in item.value for item in app.subheader))
        meetings = next(
            table.value
            for table in app.dataframe
            if "Gegnerplatz" in table.value.columns
        )
        self.assertEqual(list(meetings["Turnier"]), ["01.03.2026 Hgr. D Standard"])
        self.assertEqual(list(meetings["Ort"]), ["Oldenburg"])

    def test_changing_filters_clears_selection_when_opponents_change(self):
        pair = "Ada Muster / Ben Beispiel"
        archive_pages(
            self.database,
            "https://example.test/other/index.htm",
            [
                {
                    "url": "https://example.test/other/ergwert.htm",
                    "titel": "02.03.2026 Hgr. C Standard",
                    "paare": [
                        {"name": pair, "platz_von": 1, "platz_bis": 1},
                        {
                            "name": "Zoe Muster / Max Beispiel",
                            "platz_von": 2,
                            "platz_bis": 2,
                        },
                    ],
                    "paar_ergebnisse": [],
                }
            ],
        )
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py",
            default_timeout=15,
        ).run()
        app.switch_page("dashboard_pages/opponents.py").run()
        group_filter = next(
            widget for widget in app.selectbox if widget.label == "Startgruppe"
        )
        group_filter.select("Hgr. D").run()
        table = next(
            table
            for table in app.dataframe
            if table.key and table.key.startswith("opponent_table_selection_")
        )
        table_key = table.key
        assert table_key is not None
        app.session_state[table_key] = {"selection": {"cells": [[0, "Paar"]]}}
        app.run()
        self.assertTrue(any("Turniere mit " in item.value for item in app.subheader))
        group_filter = next(
            widget for widget in app.selectbox if widget.label == "Startgruppe"
        )
        group_filter.select("Hgr. C").run()
        self.assertEqual(app.exception, [])
        self.assertFalse(any("Turniere mit " in item.value for item in app.subheader))

    def test_import_page_requires_pair_selection(self):
        entrypoint = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(entrypoint).run()
        app.switch_page("dashboard_pages/fetch_results.py").run()

        pair_input = next(
            widget
            for widget in app.text_input
            if widget.label == "Paar für die Auswertung"
        )
        submit_button = next(
            widget
            for widget in app.button
            if widget.label == "Ergebnisse abrufen und speichern"
        )
        pair_input.set_value("")
        submit_button.click().run()

        self.assertEqual(app.exception, [])
        self.assertTrue(
            any("Bitte gib das Paar an" in item.value for item in app.error)
        )


if __name__ == "__main__":
    unittest.main()
