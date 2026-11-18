import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

from etl import crawler
from etl.archiv import archive_pages, load_pages
from etl.data import build_pair_dashboard, filter_tournaments_for_pair


class CrawlerTests(unittest.TestCase):
    def test_loaded_html_without_results_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "results.json"
            output.write_text("existing output", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    ["crawler", "https://example.test/index.htm", "--out", str(output)],
                ),
                patch.object(
                    crawler,
                    "crawl",
                    return_value={
                        "https://example.test/index.htm": BeautifulSoup(
                            "<h1>Login</h1>", "html.parser"
                        )
                    },
                ),
                redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(crawler.main(), 1)
            self.assertIn("Keine erkennbaren Ergebnisdaten", errors.getvalue())
            self.assertEqual(output.read_text(), "existing output")

    def test_blank_judge_cells_are_known_but_missing_cells_are_not(self):
        header = (
            '<tr><th rowspan="2">Nr</th><th rowspan="2">Paar</th><th colspan="2">Tango</th></tr>'
            "<tr><th>A Ada Richter</th><th>B Ben Richter</th></tr>"
        )
        for last_cell, complete in (("<td></td>", True), ("", False)):
            html = f"<table>{header}<tr><td>1</td><td>Ada Muster / Ben Beispiel</td><td>X</td>{last_cell}</tr></table>"
            _, results = crawler.parse_page(
                "https://example.test/event/ergwert.htm",
                BeautifulSoup(html, "html.parser"),
                "",
                include_all=True,
            )
            self.assertEqual(results[0]["wertungen_vollstaendig"], complete)
            self.assertEqual(results[0]["richteranzahl"], 2)
            if complete:
                self.assertEqual(results[0]["richter_wertungen"][1]["rohwert"], "-")

    def test_validate_start_url_rejects_non_http_and_local_addresses(self):
        for url in (
            "file:///etc/passwd",
            "http://localhost/event/index.htm",
            "http://127.0.0.1/event/index.htm",
            "https://user:password@example.test/event/index.htm",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                crawler.validate_start_url(url)

    def test_crawl_reports_failed_pages_to_caller(self):
        errors = []
        with (
            patch.object(crawler.requests, "Session") as make_session,
            redirect_stderr(io.StringIO()),
        ):
            make_session.return_value.get.side_effect = (
                crawler.requests.ConnectionError("connection failed")
            )
            pages = crawler.crawl(
                "https://example.test/event/index.htm",
                delay=0,
                max_pages=10,
                cache=None,
                errors=errors,
            )

        self.assertEqual(pages, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("connection failed", errors[0])

    def test_crawl_follows_frames_and_iframes(self):
        start_url = "https://example.test/event/index.htm"
        frame_url = "https://example.test/event/category/index.htm"
        menu_url = "https://example.test/event/category/menu.htm"
        result_url = "https://example.test/event/category/result.htm"
        bodies = {
            start_url: '<frame src="category/index.htm">',
            frame_url: '<iframe src="menu.htm#round=1">',
            menu_url: '<a href="result.htm">Results</a>',
            result_url: "<p>Results</p>",
        }

        def response_for(url, timeout):
            self.assertEqual(timeout, 20)
            return SimpleNamespace(
                content=bodies[url].encode(),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

        with patch.object(crawler.requests, "Session") as make_session:
            make_session.return_value.get.side_effect = response_for
            pages = crawler.crawl(start_url, delay=0, max_pages=10, cache=None)

        self.assertEqual(set(pages), set(bodies))

    def test_crawl_follows_same_site_embedded_result_indexes_across_paths(self):
        start_url = "https://1scn.de/hauptgruppentag/"
        index_2026 = "https://www.1scn.de/turnierergebnisse_tanzen_2026/index.htm"
        index_2025 = "https://www.1scn.de/turnierergebnisse_tanzen_2025/index.htm"
        result_2026 = (
            "https://www.1scn.de/turnierergebnisse_tanzen_2026/event/ergwert.htm"
        )
        result_2025 = (
            "https://www.1scn.de/turnierergebnisse_tanzen_2025/event/ergwert.htm"
        )
        bodies = {
            start_url: (
                f'<iframe src="{index_2026}"></iframe>'
                f'<iframe src="{index_2025}"></iframe>'
            ),
            index_2026: '<a href="event/ergwert.htm">2026</a>',
            index_2025: '<a href="event/ergwert.htm">2025</a>',
            result_2026: "<p>Results 2026</p>",
            result_2025: "<p>Results 2025</p>",
        }

        def response_for(url, timeout):
            self.assertEqual(timeout, 20)
            return SimpleNamespace(
                content=bodies[url].encode(),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

        with patch.object(crawler.requests, "Session") as make_session:
            make_session.return_value.get.side_effect = response_for
            pages = crawler.crawl(start_url, delay=0, max_pages=10, cache=None)

        self.assertEqual(set(pages), set(bodies))

    def test_crawl_follows_atsv_topturnier_fallback_link(self):
        start_url = "https://www.atsv-tanzen.de/turniere/turnier-ergebnisse-glm-2026/"
        turnier_url = (
            "https://www.atsv-tanzen.de/wp-external/turnier/20260502-glm/"
            "?nocache=202309031450"
        )
        category_url = (
            "https://www.atsv-tanzen.de/wp-external/turnier/20260502-glm/"
            "0-lm_hgrdstd/index.htm"
        )
        menu_url = (
            "https://www.atsv-tanzen.de/wp-external/turnier/20260502-glm/"
            "0-lm_hgrdstd/menu.htm"
        )
        results_url = (
            "https://www.atsv-tanzen.de/wp-external/turnier/20260502-glm/"
            "0-lm_hgrdstd/ergwert.htm"
        )
        unrelated_url = "https://www.atsv-tanzen.de/wp-external/other/index.htm"
        bodies = {
            start_url: (
                f'<a href="{turnier_url}">Ergebnisse</a>'
                f'<a href="{unrelated_url}">Andere Seite</a>'
            ),
            turnier_url: '<a href="0-lm_hgrdstd/index.htm">Hgr D Standard</a>',
            category_url: '<iframe src="menu.htm"></iframe>',
            menu_url: '<a href="ergwert.htm">Wertung</a>',
            results_url: "<p>Results</p>",
        }

        def response_for(url, timeout):
            self.assertEqual(timeout, 20)
            return SimpleNamespace(
                content=bodies[url].encode(),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

        with patch.object(crawler.requests, "Session") as make_session:
            make_session.return_value.get.side_effect = response_for
            pages = crawler.crawl(start_url, delay=0, max_pages=10, cache=None)

        self.assertEqual(
            set(pages), {start_url, turnier_url, category_url, menu_url, results_url}
        )

    def test_parse_page_preserves_dance_section_labels(self):
        html = """
        <table>
          <tr><th>Nr</th><th>Wertungsrichter</th><th>Platz</th></tr>
          <tr><td></td><td>A Ada Richter</td><td></td></tr>
          <tr><td></td><td colspan="1">Langsamer Walzer</td><td></td></tr>
          <tr><td>57 Ada Muster / Ben Beispiel</td><td>1 x</td><td>1.</td></tr>
          <tr><td></td><td colspan="1">Tango</td><td></td></tr>
          <tr><td>57 Ada Muster / Ben Beispiel</td><td>2 x</td><td>2.</td></tr>
        </table>
        """
        _, results = crawler.parse_page(
            "https://example.test/event/wert_er.htm",
            BeautifulSoup(html, "html.parser"),
            "Ada Muster",
        )

        self.assertEqual(
            [result["tanz"] for result in results], ["Langsamer Walzer", "Tango"]
        )
        self.assertIn(
            "Wertungsrichter | A Ada Richter | Tango",
            results[1]["alle_weiteren_spalten"],
        )

    def test_parse_ergwert_ignores_dance_abbreviation_columns(self):
        html = """
        <table>
          <tr>
            <th rowspan="2">Platz</th><th rowspan="2">Paar</th>
            <th rowspan="2">Nr</th><th rowspan="2">R</th>
            <th colspan="3">Langsamer Walzer</th><th>LW</th>
            <th colspan="3">Tango</th><th>TG</th><th rowspan="2">Summe</th>
          </tr>
          <tr>
            <th>A<span class="tooltip2w">Ada Richter</span></th>
            <th>B<span class="tooltip2w">Ben Richter</span></th><th>Su</th>
            <th>A<span class="tooltip2w">Ada Richter</span></th>
            <th>B<span class="tooltip2w">Ben Richter</span></th><th>Su</th>
          </tr>
          <tr>
            <td>1.</td><td>Ada Muster / Ben Beispiel</td><td>57</td><td>F<br>1</td>
            <td>1<br>x</td><td>2<br>-</td><td>1,0<br>1</td>
            <td>1<br>-</td><td>2<br>x</td><td>1,0<br>1</td>
            <td>2.0<br>2</td>
          </tr>
        </table>
        """

        _, results = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )

        result = results[0]
        self.assertEqual(result["kreuze_anzahl"], 2)
        self.assertEqual(
            [
                (mark["tanz"], mark["kuerzel"], mark["kreuz"])
                for mark in result["richter_wertungen"]
            ],
            [
                ("Langsamer Walzer", "A", True),
                ("Langsamer Walzer", "B", False),
                ("Tango", "A", False),
                ("Tango", "B", True),
            ],
        )

    def test_judge_name_with_code_is_not_parsed_as_a_pair(self):
        html = """
        <table>
          <tr><th>Nr.</th><th>Paar</th><th>Wertungsrichter</th><th>Platz</th></tr>
          <tr><td></td><td></td><td>C Dr. Caroline Fried</td><td></td></tr>
          <tr><td>59</td><td>Ada Muster / Ben Beispiel</td><td>1</td><td>1.</td></tr>
        </table>
        """
        couples, results = crawler.parse_page(
            "https://example.test/event/wert_er.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )

        self.assertEqual(
            [couple["name"] for couple in couples], ["Ada Muster / Ben Beispiel"]
        )
        self.assertEqual(
            [result["paar"] for result in results], ["Ada Muster / Ben Beispiel"]
        )

    def test_tabges_matrix_parses_round_crosses_judges_and_qualification(self):
        html = """
        <table>
          <tr><td>Anzahl Teilnehmer: 3</td><td colspan="3">Startnummer</td></tr>
          <tr>
            <td>Wertungsrichter</td>
            <td>11<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td>
            <td>12<span class="tooltip2gc">Eva Beispiel / Tom Muster</span></td>
            <td>13<span class="tooltip2gc">Mia Beispiel / Leo Muster</span></td>
          </tr>
          <tr>
            <td>A) Alex Richter<br>B) Bea Richter</td>
            <td>3<br>2</td><td>1<br>1</td><td>2<br>2</td>
          </tr>
          <tr><td>Ergebnis der Vorrunde</td><td>5</td><td>2</td><td>4</td></tr>
          <tr>
            <td>Qualifiziert für die Zwischenrunde</td>
            <td>X</td><td></td><td>X</td>
          </tr>
          <tr><td>Ergebnis der Zwischenrunde</td><td>4</td><td></td><td>3</td></tr>
          <tr>
            <td>Qualifiziert für die Endrunde</td>
            <td>X</td><td></td><td></td>
          </tr>
          <tr><td>Addition Endrunde</td><td>1,0</td><td></td><td>2,0</td></tr>
          <tr>
            <td>Platz von<br>Platz bis</td>
            <td>1<br>1</td><td></td><td>2<br>2</td>
          </tr>
          <tr><td>Aufstiegspunkte</td><td>12</td><td></td><td>8</td></tr>
        </table>
        """

        couples, results = crawler.parse_page(
            "https://example.test/event/tabges.htm",
            BeautifulSoup(html, "html.parser"),
            "Ada Muster",
            include_all=True,
            dance_count=3,
        )

        self.assertEqual(len(couples), 3)
        ada_results = [result for result in results if result["startnr"] == "11"]
        rounds = {result["runde"]: result for result in ada_results}
        self.assertEqual(rounds["Vorrunde"]["kreuze_anzahl"], 5)
        self.assertEqual(rounds["Vorrunde"]["feldgroesse"], 3)
        self.assertEqual(rounds["Vorrunde"]["moegliche_kreuzstimmen"], 6)
        self.assertEqual(
            [judge["name"] for judge in rounds["Vorrunde"]["richter_kreuze"]],
            ["Alex Richter", "Bea Richter"],
        )
        self.assertEqual(rounds["Vorrunde"]["qualifiziert"], True)
        self.assertEqual(rounds["Vorrunde"]["qualifiziert_fuer"], "Zwischenrunde")
        self.assertEqual(rounds["Zwischenrunde"]["kreuze_anzahl"], 4)
        self.assertEqual(rounds["Zwischenrunde"]["qualifiziert"], True)
        summary = next(
            result for result in ada_results if result["runde"] == "Gesamtwertung"
        )
        self.assertEqual(summary["alle_weiteren_spalten"]["Aufstiegspunkte"], "12")
        self.assertEqual(summary["alle_weiteren_spalten"]["Platz von"], "1")
        self.assertEqual(summary["alle_weiteren_spalten"]["Platz bis"], "1")

    def test_process_pages_derives_round_vote_total_from_sibling_dance_columns(self):
        tabges_html = """
        <table>
          <tr><td>Wertungsrichter</td>
            <td>11<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td>
          </tr>
          <tr><td>A) Alex Richter<br>B) Bea Richter</td><td>2<br>1</td></tr>
          <tr><td>Ergebnis der Vorrunde</td><td>3</td></tr>
          <tr><td>Qualifiziert für die Endrunde</td><td>X</td></tr>
        </table>
        """
        ergwert_html = """
        <table>
          <tr><th>Nr</th><th>Paar</th><th>Langsamer Walzer</th><th>Tango</th></tr>
          <tr><th></th><th></th><th>Su</th><th>Su</th></tr>
          <tr><td>11</td><td>Ada Muster / Ben Beispiel</td><td>1</td><td>1</td></tr>
        </table>
        """
        base_url = "https://example.test/event/"

        pages = crawler.process_pages(
            {
                base_url + "tabges.htm": BeautifulSoup(tabges_html, "html.parser"),
                base_url + "ergwert.htm": BeautifulSoup(ergwert_html, "html.parser"),
            },
            include_all=True,
        )

        tabges = next(page for page in pages if page["url"].endswith("tabges.htm"))
        preliminary = next(
            result
            for result in tabges["paar_ergebnisse"]
            if result["runde"] == "Vorrunde"
        )
        self.assertEqual(preliminary["moegliche_kreuzstimmen"], 4)
        self.assertEqual(tabges["schema_version"], 3)

    def test_round_votes_use_dances_from_compact_result_page(self):
        tabges = """
        <table>
          <tr><td>Wertungsrichter</td>
            <td>4<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td>
          </tr>
          <tr><td>A) Alex Richter<br>B) Bea Richter</td><td>4<br>3</td></tr>
          <tr><td>Ergebnis der Vorrunde</td><td>7</td></tr>
        </table>
        """
        result = """
        <table><tr><td colspan="7">Endrunde</td></tr>
          <tr><td>Platz</td><td>Teilnehmer/Club</td>
              <td>LW</td><td>TG</td><td>SF</td><td>QU</td><td>PZ</td></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel (4)</td>
              <td>1</td><td>1</td><td>1</td><td>1</td><td>4</td></tr>
        </table>
        """
        base = "https://example.test/event/"
        pages = crawler.process_pages(
            {
                base + "erg.htm": BeautifulSoup(result, "html.parser"),
                base + "tabges.htm": BeautifulSoup(tabges, "html.parser"),
            },
            include_all=True,
        )
        round_result = next(
            result
            for page in pages
            for result in page["paar_ergebnisse"]
            if result["runde"] == "Vorrunde"
        )
        self.assertEqual(round_result["moegliche_kreuzstimmen"], 8)
        self.assertEqual(
            [judge["max_kreuze"] for judge in round_result["richter_kreuze"]],
            [4, 4],
        )
        analysis = build_pair_dashboard(pages, "Ada Muster / Ben Beispiel")
        rounds = analysis["rounds_by_event"][analysis["events"][0]["id"]]
        self.assertEqual(
            next(row for row in rounds if row["stage"] == "Vorrunde")["cross_rate"],
            7 / 8,
        )

    def test_round_votes_are_unknown_when_dance_sources_conflict(self):
        base = "https://example.test/event/"
        result = """
        <table><tr><td>Platz</td><td>Teilnehmer/Club</td>
          <td>LW</td><td>TG</td><td>PZ</td></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>1</td><td>1</td><td>2</td></tr>
        </table>
        """
        detailed = """
        <table><tr><td>Nr</td><td>Paar</td><td>Langsamer Walzer</td></tr>
          <tr><td></td><td></td><td>Su</td></tr>
          <tr><td>4</td><td>Ada Muster / Ben Beispiel</td><td>1</td></tr>
        </table>
        """
        tabges = """
        <table><tr><td>Wertungsrichter</td>
          <td>4<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td></tr>
          <tr><td>A) Alex Richter</td><td>1</td></tr>
          <tr><td>Ergebnis der Vorrunde</td><td>1</td></tr>
        </table>
        """
        pages = crawler.process_pages(
            {
                base + name: BeautifulSoup(html, "html.parser")
                for name, html in (
                    ("erg.htm", result),
                    ("ergwert.htm", detailed),
                    ("tabges.htm", tabges),
                )
            },
            include_all=True,
        )
        round_result = next(
            result
            for page in pages
            for result in page["paar_ergebnisse"]
            if result["runde"] == "Vorrunde"
        )
        self.assertIsNone(round_result["moegliche_kreuzstimmen"])

    def test_round_votes_are_unknown_if_judge_crosses_exceed_dance_count(self):
        base = "https://example.test/event/"
        html = {
            "erg.htm": """
              <table><tr><td>Platz</td><td>Teilnehmer/Club</td>
                <td>LW</td><td>TG</td><td>PZ</td></tr>
                <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>1</td><td>1</td><td>2</td></tr>
              </table>
            """,
            "tabges.htm": """
              <table><tr><td>Wertungsrichter</td>
                <td>4<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td></tr>
                <tr><td>A) Alex Richter</td><td>3</td></tr>
                <tr><td>Ergebnis der Vorrunde</td><td>3</td></tr>
              </table>
            """,
        }
        pages = crawler.process_pages(
            {
                base + name: BeautifulSoup(body, "html.parser")
                for name, body in html.items()
            },
            include_all=True,
        )
        result = next(
            result
            for page in pages
            for result in page["paar_ergebnisse"]
            if result["runde"] == "Vorrunde"
        )
        self.assertIsNone(result["moegliche_kreuzstimmen"])
        self.assertIsNone(result["richter_kreuze"][0]["max_kreuze"])

    def test_parse_page_uses_round_heading_rows_and_round_code(self):
        html = """
        <table>
          <tr><th>R</th><th>Paar</th><th>Platz</th></tr>
          <tr><td colspan="3">Vorrunde</td></tr>
          <tr><td>1</td><td>Ada Muster / Ben Beispiel</td><td>2.</td></tr>
          <tr><td>2</td><td>Eva Beispiel / Tom Muster</td><td>1.</td></tr>
        </table>
        """

        _, results = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )

        self.assertEqual({result["runde"] for result in results}, {"Vorrunde"})
        self.assertTrue(all(result["feldgroesse"] == 2 for result in results))

    def test_judge_label_does_not_store_list_letter_in_name(self):
        parsed = crawler.parse_judge_label(
            "Wertungsrichter | A A Max Mustermann | Langsamer Walzer", ""
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["kuerzel"], "A")
        self.assertEqual(parsed["name"], "Max Mustermann")

    def test_parse_page_can_store_all_pairs_and_field_metadata(self):
        html = """
        <table>
          <tr><th>Platz</th><th>Paar</th><th>Nr.</th><th>Wertungsrichter | A Ada Richter</th></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>57</td><td>1 x</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster</td><td>58</td><td>2 -</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        _, selected = crawler.parse_page(
            "https://example.test/event/ergwert.htm", soup, "Ada Muster"
        )
        _, all_pairs = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            soup,
            "Ada Muster",
            include_all=True,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(all_pairs), 2)
        self.assertEqual(all_pairs[0]["feldgroesse"], 2)
        self.assertEqual(all_pairs[0]["startnr"], "57")
        self.assertEqual(all_pairs[0]["kreuze_anzahl"], 1)
        self.assertEqual(all_pairs[0]["richteranzahl"], 1)
        self.assertTrue(all_pairs[0]["richter_wertungen"][0]["kreuz"])

    def test_parse_page_splits_inline_and_separate_club_columns(self):
        html = """
        <table>
          <tr><th>Platz</th><th>Teilnehmer<br>Club</th><th>Nr</th></tr>
          <tr>
            <td>1.</td>
            <td>Ada Muster / Ben Beispiel<br><i>TTC Example</i></td>
            <td>57</td>
          </tr>
        </table>
        <table>
          <tr><th>Nr.</th><th>Teilnehmer</th><th>Club</th></tr>
          <tr>
            <td>58</td>
            <td>Eva Beispiel / Tom Muster</td>
            <td>TSC Beispiel</td>
          </tr>
        </table>
        """

        couples, results = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )

        self.assertEqual(
            {pair["name"]: pair["verein"] for pair in couples},
            {
                "Ada Muster / Ben Beispiel": "TTC Example",
                "Eva Beispiel / Tom Muster": "TSC Beispiel",
            },
        )
        self.assertEqual(
            {result["paar"]: result["verein"] for result in results},
            {
                "Ada Muster / Ben Beispiel": "TTC Example",
                "Eva Beispiel / Tom Muster": "TSC Beispiel",
            },
        )

    def test_result_header_and_parenthesized_start_numbers(self):
        html = """
        <table>
          <tr><td>Platz</td><td>Teilnehmer/Club</td><td>R</td></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel (4)<br><i>TTC Example</i></td><td>F</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster (3)<br><i>TSC Beispiel</i></td><td>1</td></tr>
        </table>
        """
        couples, results = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )
        self.assertEqual(
            [(pair["name"], pair["startnr"], pair["platz_von"]) for pair in couples],
            [
                ("Ada Muster / Ben Beispiel", "4", 1),
                ("Eva Beispiel / Tom Muster", "3", 2),
            ],
        )
        self.assertEqual(
            [result["paar_id"] for result in results], ["startnr:4", "startnr:3"]
        )

    def test_dance_name_in_result_header_is_not_a_couple(self):
        html = """
        <table>
          <tr><td rowspan="2">Platz</td><td rowspan="2">Teilnehmer<br>Club</td>
              <td rowspan="2">Nr</td><td colspan="2">Cha Cha Cha</td></tr>
          <tr><td>A Ada Richter</td><td>Su</td></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel<br><i>TTC Example</i></td>
              <td>14</td><td>1</td><td>1,0</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster<br><i>TSC Beispiel</i></td>
              <td>15</td><td>2</td><td>2,0</td></tr>
        </table>
        """
        couples, results = crawler.parse_page(
            "https://example.test/event/ergwert.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )
        self.assertEqual([pair["startnr"] for pair in couples], ["14", "15"])
        self.assertEqual([pair["platz_von"] for pair in couples], [1, 2])
        self.assertEqual(len(results), 2)

    def test_tabges_single_and_shared_places_preserve_empty_lines(self):
        html = """
        <table>
          <tr><td>Startnummer</td>
            <td>1<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td>
            <td>2<span class="tooltip2gc">Eva Beispiel / Tom Muster</span></td>
            <td>3<span class="tooltip2gc">Mia Beispiel / Leo Muster</span></td>
          </tr>
          <tr><td>Platz von<br>Platz bis</td><td>1<br>&nbsp;</td><td>2<br>3</td><td>&nbsp;<br>3</td></tr>
        </table>
        """
        _, results = crawler.parse_page(
            "https://example.test/event/tabges.htm",
            BeautifulSoup(html, "html.parser"),
            "",
            include_all=True,
        )
        fields = {
            result["startnr"]: result["alle_weiteren_spalten"] for result in results
        }
        self.assertEqual(fields["1"], {"Platz von": "1"})
        self.assertEqual(fields["2"], {"Platz von": "2", "Platz bis": "3"})
        self.assertEqual(fields["3"], {"Platz bis": "3"})

    def test_result_import_provides_placements_and_opponents(self):
        base = "https://example.test/event/"
        html = {
            "ergwert.htm": """
              <table>
                <tr><td>Platz</td><td>Teilnehmer/Club</td><td>R</td></tr>
                <tr><td>1.</td><td>Ada Muster / Ben Beispiel (4)<br><i>TTC Example</i></td><td>F</td></tr>
                <tr><td>2.</td><td>Eva Beispiel / Tom Muster (3)<br><i>TSC Beispiel</i></td><td>F</td></tr>
                <tr><td>3.</td><td>Mia Beispiel / Leo Muster (7)<br><i>TSC Beispiel</i></td><td>1</td></tr>
              </table>
            """,
            "tabges.htm": """
              <table>
                <tr><td>Startnummer</td>
                  <td>4<span class="tooltip2gc">Ada Muster / Ben Beispiel</span></td>
                  <td>3<span class="tooltip2gc">Eva Beispiel / Tom Muster</span></td>
                  <td>7<span class="tooltip2gc">Mia Beispiel / Leo Muster</span></td>
                </tr>
                <tr><td>Platz von<br>Platz bis</td><td>1<br>&nbsp;</td><td>2<br>&nbsp;</td><td>3<br>&nbsp;</td></tr>
              </table>
            """,
        }
        pages = crawler.process_pages(
            {
                base + name: BeautifulSoup(body, "html.parser")
                for name, body in html.items()
            },
            include_all=True,
        )
        selected = filter_tournaments_for_pair(pages, "Ada Muster / Ben Beispiel")
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "results.sqlite"
            archive_pages(database, base, selected)
            analysis = build_pair_dashboard(
                load_pages(database), "Ada Muster / Ben Beispiel"
            )
        self.assertEqual(analysis["events"][0]["place"], 1)
        self.assertEqual(analysis["events"][0]["field_size"], 3)
        self.assertEqual(len(analysis["opponent_rows"]), 2)
        self.assertTrue(all(row["wins"] == 1 for row in analysis["opponent_rows"]))

    def test_process_pages_builds_archive_payload_with_all_pair_results(self):
        html = """
        <table>
          <tr><th>Platz</th><th>Paar</th><th>Nr.</th><th>Wertungsrichter | A Ada Richter</th></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>57</td><td>1 x</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster</td><td>58</td><td>2 -</td></tr>
        </table>
        """
        url = "https://example.test/event/ergwert.htm"

        processed = crawler.process_pages(
            {url: BeautifulSoup(html, "html.parser")},
            include_all=True,
        )

        self.assertEqual(len(processed), 1)
        self.assertTrue(processed[0]["alle_paare_erfasst"])
        self.assertEqual(len(processed[0]["paare"]), 2)
        self.assertEqual(len(processed[0]["paar_ergebnisse"]), 2)

    def test_process_pages_adds_city_from_ancestor_tournament_index(self):
        index_url = "https://example.test/event/index.htm"
        results_url = "https://example.test/event/category/ergwert.htm"
        index_html = """
        <html>
          <head><title>Hauptgruppentag 2026 in Norderstedt</title></head>
          <body><div class="comphead">Am 17.10.2026 in Norderstedt.</div></body>
        </html>
        """
        results_html = """
        <table>
          <tr><th>Platz</th><th>Paar</th></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td></tr>
        </table>
        """

        processed = crawler.process_pages(
            {
                index_url: BeautifulSoup(index_html, "html.parser"),
                results_url: BeautifulSoup(results_html, "html.parser"),
            },
            include_all=True,
        )

        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["stadt"], "Norderstedt")

    def test_process_pages_ignores_non_results_wordpress_landing_page(self):
        html = """
        <table>
          <tr><th>Startzeit</th></tr>
          <tr><td>Der Turniertag ist beendet.</td></tr>
        </table>
        """

        processed = crawler.process_pages(
            {"https://1scn.de/hauptgruppentag/": BeautifulSoup(html, "html.parser")},
            include_all=True,
        )

        self.assertEqual(processed, [])

    def test_all_pairs_option_keeps_other_pairs_in_json_with_pair_filter(self):
        html = """
        <table>
          <tr><th>Platz</th><th>Paar</th><th>Nr.</th><th>Wertungsrichter | A Ada Richter</th></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>57</td><td>1 x</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster</td><td>58</td><td>2 -</td></tr>
        </table>
        """
        url = "https://example.test/event/ergwert.htm"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "results.json"
            argv = [
                "etl.crawler",
                "https://example.test/event/index.htm",
                "--paar",
                "Ada Muster",
                "--alle-paare",
                "--out",
                str(output_path),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    crawler,
                    "crawl",
                    return_value={url: BeautifulSoup(html, "html.parser")},
                ),
            ):
                result = crawler.main()

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertTrue(payload[0]["alle_paare_erfasst"])
        self.assertEqual(len(payload[0]["paar_ergebnisse"]), 2)

    def test_database_option_archives_all_pairs(self):
        html = """
        <table>
          <tr><th>Platz</th><th>Paar</th><th>Nr.</th><th>Wertungsrichter | A Ada Richter</th></tr>
          <tr><td>1.</td><td>Ada Muster / Ben Beispiel</td><td>57</td><td>1 x</td></tr>
          <tr><td>2.</td><td>Eva Beispiel / Tom Muster</td><td>58</td><td>2 -</td></tr>
        </table>
        """
        url = "https://example.test/event/ergwert.htm"
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "turniere.sqlite"
            output_path = Path(temp_dir) / "results.json"
            argv = [
                "etl.crawler",
                "https://example.test/event/index.htm",
                "--paar",
                "Ada Muster",
                "--db",
                str(database),
                "--out",
                str(output_path),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    crawler,
                    "crawl",
                    return_value={url: BeautifulSoup(html, "html.parser")},
                ),
            ):
                result = crawler.main()

            archived = load_pages(database)

        self.assertEqual(result, 0)
        self.assertTrue(archived[0]["alle_paare_erfasst"])
        self.assertEqual(len(archived[0]["paar_ergebnisse"]), 2)

    def test_no_loaded_pages_returns_error_without_writing_empty_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "empty.json"
            stderr = io.StringIO()
            argv = [
                "etl.crawler",
                "https://example.test/index.htm",
                "--out",
                str(output_path),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(crawler, "crawl", return_value={}),
                redirect_stderr(stderr),
            ):
                result = crawler.main()

            self.assertEqual(result, 1)
            self.assertIn("Keine HTML-Seiten geladen", stderr.getvalue())
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
