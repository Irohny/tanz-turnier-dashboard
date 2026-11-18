import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from etl import auswertung
from etl.archiv import archive_pages


class ErgebnisAuswertungTests(unittest.TestCase):
    def test_final_judge_places_do_not_become_normalized_cross_rates(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "paar_ergebnisse": [
                {
                    "paar": "Ada Muster / Ben Beispiel",
                    "runde": "Endrunde",
                    "feldgroesse": 3,
                    "richteranzahl": 2,
                    "alle_weiteren_spalten": {
                        "Tango | A Richter A": "1 x",
                        "Tango | B Richter B": "3 -",
                    },
                }
            ],
        }
        report = auswertung.build_report([page], "Ada Muster")
        self.assertNotIn("Kreuzrate je Tanz (", report)
        self.assertIn("Keine normalisierte Kreuzrate:", report)

    def test_partial_qualification_never_produces_a_cutoff(self):
        page = {
            "url": "https://example.test/event/tabges.htm",
            "titel": "01.03.2026 Hgr. D Standard",
            "alle_paare_erfasst": True,
            "paar_ergebnisse": [
                {
                    "paar": name,
                    "paar_id": str(index),
                    "runde": "Vorrunde",
                    "feldgroesse": 2,
                    "kreuze_anzahl": crosses,
                    "moegliche_kreuzstimmen": 6,
                    "qualifiziert": qualified,
                }
                for index, (name, crosses, qualified) in enumerate(
                    (
                        ("Ada Muster / Ben Beispiel", 5, True),
                        ("Eva Beispiel / Tom Muster", 4, None),
                    )
                )
            ],
        }
        report = auswertung.build_report([page], "Ada Muster")
        self.assertIn("Keine Weiterkommensgrenze berechnet", report)
        self.assertNotIn("Grenze 5", report)

    def test_build_report_shows_rank_crosses_judges_and_scores(self):
        data = [
            {
                "url": "https://example.test/event/ergwert.htm",
                "titel": "Hauptgruppe Standard",
                "paare": [
                    {"startnr": "1", "name": "Besseres Paar"},
                    {"startnr": "2", "name": "Ada Muster / Ben Beispiel"},
                    {"startnr": "3", "name": "Schlechteres Paar"},
                ],
                "paar_ergebnisse": [
                    {
                        "runde": "(unbekannt)",
                        "paar": "Ada Muster / Ben Beispiel",
                        "platzierung_spalten": {"Platz": "2."},
                        "alle_weiteren_spalten": {
                            "R": "F 1",
                            "Langsamer Walzer | A Alex Richter": "2 x",
                            "Langsamer Walzer | B Bea Richter": "1 -",
                            "Langsamer Walzer | Su": "2,0 1",
                        },
                    }
                ],
            },
            {
                "url": "https://example.test/event/wert_er.htm",
                "titel": "Hauptgruppe Standard",
                "paar_ergebnisse": [
                    {
                        "runde": "Endrundentabelle",
                        "paar": "Ada Muster / Ben Beispiel",
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | A Alex Richter | Langsamer Walzer": "1",
                            "Platz": "1,0",
                        },
                    },
                    {
                        "runde": "Endrundentabelle",
                        "paar": "Ada Muster / Ben Beispiel",
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | A Alex Richter | Tango": "3",
                            "Platz": "3,0",
                        },
                    },
                ],
            },
        ]

        report = auswertung.build_report(data, "Ada Muster Ben Beispiel")

        self.assertIn("Platzierung laut Ergebniswertung: 2.", report)
        self.assertIn("Besseres Paar", report)
        self.assertIn("Schlechteres Paar", report)
        self.assertIn("Finale/Endrunde", report)
        self.assertIn("Kreuze: 1 X-Markierungen", report)
        self.assertIn("A Alex Richter: 2 x", report)
        self.assertIn("B Bea Richter: 1 -", report)
        self.assertIn("Langsamer Walzer (Finale/Endrunde): Ø Platz 2.00 (n=1)", report)
        self.assertIn("A Alex Richter: Ø 2.00 (n=2)", report)

    def test_missing_pair_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Kein passendes Paar"):
            auswertung.build_report([], "Niemand")

    def test_numeric_round_code_is_normalized(self):
        stage = auswertung.round_name(
            {"url": "https://example.test/event/ergwert.htm"},
            {"runde": "(unbekannt)", "rundencode": "2 1"},
        )

        self.assertEqual(stage, "Zwischenrunde")

    def test_tabges_cross_rate_qualification_and_judge_counts_are_reported(self):
        pairs = (
            ("Ada Muster / Ben Beispiel", 5, True),
            ("Eva Beispiel / Tom Muster", 2, False),
            ("Mia Beispiel / Leo Muster", 4, True),
        )
        page = {
            "url": "https://example.test/event/tabges.htm",
            "titel": "Hauptgruppe Standard",
            "alle_paare_erfasst": True,
            "paar_ergebnisse": [
                {
                    "paar": pair,
                    "paar_id": f"startnr:{index}",
                    "startnr": str(index),
                    "runde": "Vorrunde",
                    "feldgroesse": 3,
                    "kreuze_anzahl": crosses,
                    "moegliche_kreuzstimmen": 6,
                    "qualifiziert": qualified,
                    "qualifiziert_fuer": "Finale/Endrunde",
                    "richter_kreuze": (
                        [
                            {
                                "kuerzel": "A",
                                "name": "Alex Richter",
                                "kreuze": 3,
                                "max_kreuze": 3,
                            },
                            {
                                "kuerzel": "B",
                                "name": "Bea Richter",
                                "kreuze": 2,
                                "max_kreuze": 3,
                            },
                        ]
                        if index == 1
                        else []
                    ),
                }
                for index, (pair, crosses, qualified) in enumerate(pairs, start=1)
            ],
        }

        report = auswertung.build_report([page], "Ada Muster")

        self.assertIn("Runden-Kreuzrate aus der Gesamttabelle:", report)
        self.assertIn("5/6 = 83%", report)
        self.assertIn("Kreuze je Wertungsrichter: A Alex Richter: 3", report)
        self.assertIn("Qualifikation: weitergekommen für Finale/Endrunde", report)
        self.assertIn("Grenze 4, Abstand +1 (weitergekommen)", report)

    def test_normalized_judge_trend_includes_preliminary_cross_rates(self):
        pairs = (
            ("Ada Muster / Ben Beispiel", (3, 0, 1)),
            ("Eva Beispiel / Tom Muster", (0, 0, 1)),
            ("Mia Beispiel / Leo Muster", (0, 0, 0)),
        )
        page = {
            "url": "https://example.test/event/tabges.htm",
            "titel": "01.03.2026 Hgr. D Standard",
            "paar_ergebnisse": [
                {
                    "paar": pair,
                    "runde": "Vorrunde",
                    "richteranzahl": 3,
                    "moegliche_kreuzstimmen": 9,
                    "richter_kreuze": [
                        {
                            "kuerzel": chr(65 + index),
                            "name": judge,
                            "kreuze": crosses,
                        }
                        for index, (judge, crosses) in enumerate(
                            zip(
                                ("Alex Richter", "Bea Richter", "Cem Richter"),
                                pair_crosses,
                                strict=True,
                            )
                        )
                    ],
                }
                for pair, pair_crosses in pairs
            ],
        }

        report = auswertung.build_report([page], "Ada Muster")

        self.assertIn("Alex Richter: +83.3 Prozentpunkte (n=1)", report)
        self.assertIn("Bea Richter: -66.7 Prozentpunkte (n=1)", report)
        self.assertIn("fehlende Nenner werden nicht geschätzt", report)

    def test_old_json_does_not_invent_missing_dance_name(self):
        data = [
            {
                "url": "https://example.test/event/wert_er.htm",
                "titel": "Hauptgruppe Standard",
                "paar_ergebnisse": [
                    {
                        "runde": "Endrundentabelle",
                        "paar": "Ada Muster / Ben Beispiel",
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | A Alex Richter | Langsamer Walzer": "2",
                            "Platz": "1,0",
                        },
                    }
                ],
            }
        ]

        report = auswertung.build_report(data, "Ada Muster")

        self.assertIn("Tanzüberschrift der Einzelwertung nicht", report)
        self.assertIn("Tanz im JSON nicht gespeichert", report)
        self.assertNotIn("Tanz: Langsamer Walzer", report)

    def test_normalization_uses_field_size_round_progression_and_panel_median(self):
        def result(pair, pair_id, round_name, rank, crosses, field_size):
            marks = {
                "Langsamer Walzer | A Alex Richter": "1 x" if crosses else "1 -",
                "Langsamer Walzer | B Bea Richter": "1 x" if crosses else "2 -",
                "Langsamer Walzer | Su": f"{rank},0",
                "Platz": f"{rank}.",
            }
            return {
                "runde": round_name,
                "paar": pair,
                "paar_id": pair_id,
                "feldgroesse": field_size,
                "richteranzahl": 2,
                "kreuze_anzahl": crosses * 2,
                "kreuze": {
                    key: value for key, value in marks.items() if value.endswith("x")
                },
                "alle_weiteren_spalten": marks,
            }

        pages = []
        for round_name, pairs in (
            (
                "Vorrundentabelle",
                [
                    ("Ada Muster / Ben Beispiel", "a", 1, 1),
                    ("Eva Beispiel / Tom Muster", "b", 2, 1),
                    ("Mia Beispiel / Leo Muster", "c", 3, 0),
                ],
            ),
            (
                "Endrundentabelle",
                [
                    ("Ada Muster / Ben Beispiel", "a", 1, 1),
                    ("Eva Beispiel / Tom Muster", "b", 2, 0),
                ],
            ),
        ):
            pages.append(
                {
                    "url": "https://example.test/event/ergwert.htm",
                    "titel": "Hauptgruppe Standard",
                    "alle_paare_erfasst": True,
                    "paar_ergebnisse": [
                        result(pair, pair_id, round_name, rank, crosses, len(pairs))
                        for pair, pair_id, rank, crosses in pairs
                    ],
                }
            )
        pages.append(
            {
                "url": "https://example.test/event/wert_er.htm",
                "titel": "Hauptgruppe Standard",
                "alle_paare_erfasst": True,
                "paar_ergebnisse": [
                    {
                        "runde": "Endrundentabelle",
                        "paar": pair,
                        "paar_id": pair_id,
                        "feldgroesse": 2,
                        "tanz": "Langsamer Walzer",
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | A Alex Richter | Langsamer Walzer": str(
                                rank_a
                            ),
                            "Wertungsrichter | B Bea Richter | Langsamer Walzer": str(
                                rank_b
                            ),
                            "Platz": str((rank_a + rank_b) / 2),
                        },
                    }
                    for pair, pair_id, rank_a, rank_b in (
                        ("Ada Muster / Ben Beispiel", "a", 1, 2),
                        ("Eva Beispiel / Tom Muster", "b", 2, 1),
                    )
                ],
            }
        )

        report = auswertung.build_report(pages, "Ada Muster")

        self.assertIn("feldnormalisiert", report)
        self.assertIn("100% (feldnormalisiert)", report)
        self.assertIn("Kreuzrate je Tanz", report)
        self.assertIn("2/2 = 100%", report)
        self.assertIn("Abstand zur beobachteten Weiterkommensgrenze", report)
        self.assertIn("Abstand +0 (weitergekommen)", report)
        self.assertIn("Gegner-Vorleistung", report)
        self.assertIn("50% aus Vorrunde", report)
        self.assertIn("Alex Richter: +100.0 Prozentpunkte", report)
        self.assertIn("Bea Richter: -100.0 Prozentpunkte", report)

    def test_cli_can_read_archived_results_from_sqlite(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "titel": "Hauptgruppe Standard",
            "paare": [
                {"startnr": "57", "name": "Ada Muster / Ben Beispiel"},
            ],
            "paar_ergebnisse": [
                {
                    "paar": "Ada Muster / Ben Beispiel",
                    "startnr": "57",
                    "runde": "Finale",
                    "platzierung_spalten": {"Platz": "1."},
                    "alle_weiteren_spalten": {},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "turniere.sqlite"
            archive_pages(database, "https://example.test/event/", [page])
            output = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "etl.auswertung",
                        "--db",
                        str(database),
                        "--paar",
                        "Ada Muster",
                    ],
                ),
                redirect_stdout(output),
            ):
                result = auswertung.main()

        self.assertEqual(result, 0)
        self.assertIn("Paar-Auswertung: Ada Muster", output.getvalue())

    def test_cli_reports_json_root_with_wrong_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_file = Path(temp_dir) / "results.json"
            json_file.write_text("{}", encoding="utf-8")
            error_output = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "etl.auswertung",
                        "--datei",
                        str(json_file),
                        "--paar",
                        "Ada Muster",
                    ],
                ),
                redirect_stderr(error_output),
            ):
                result = auswertung.main()

        self.assertEqual(result, 1)
        self.assertIn("JSON-Wurzel muss eine Liste", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
