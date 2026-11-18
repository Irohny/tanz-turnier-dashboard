import unittest
from datetime import date

from etl.common import summary_rows
from etl.data import (
    build_pair_dashboard,
    filter_events,
    filter_tournaments_for_pair,
    judge_meetings,
    normalize_quality_issue,
    pair_options,
)

PAIR = "Ada Muster / Ben Beispiel"
OTHER_A = "Eva Beispiel / Tom Muster"
OTHER_B = "Mia Beispiel / Leo Muster"


def event_pages(folder, title, ranked_pairs, result_pages=None, starter_pairs=None):
    base = f"https://example.test/{folder}/"
    pages = [
        {
            "url": f"{base}starter.htm",
            "titel": title,
            "paare": [
                {"startnr": str(index + 1), "name": name}
                for index, name in enumerate(starter_pairs or ranked_pairs)
            ],
            "paar_ergebnisse": [],
        },
        {
            "url": f"{base}ergwert.htm",
            "titel": title,
            "paare": [
                {"name": name, "platz_von": index, "platz_bis": index}
                for index, name in enumerate(ranked_pairs, start=1)
            ],
            "paar_ergebnisse": [],
        },
    ]
    for source, results in result_pages or []:
        pages.append(
            {
                "url": f"{base}{source}",
                "titel": title,
                "paare": [],
                "paar_ergebnisse": results,
            }
        )
    return pages


def sample_pages():
    first = event_pages(
        "event-one",
        "01.03.2026 Hgr. D Standard",
        [PAIR, OTHER_A, OTHER_B],
        [
            (
                "ergwert.htm",
                [
                    {
                        "paar": PAIR,
                        "runde": "Endrundentabelle",
                        "feldgroesse": 3,
                        "richteranzahl": 2,
                        "tanzanzahl": 2,
                        "kreuze_anzahl": 1,
                        "platzierung_spalten": {"Platz": "1."},
                        "alle_weiteren_spalten": {
                            "Langsamer Walzer | Su": "1,0",
                            "Tango | Su": "2,0",
                            "Langsamer Walzer | A Richter A": "1 x",
                            "Langsamer Walzer | B Richter B": "2 -",
                            "Tango | A Richter A": "1 x",
                            "Tango | B Richter B": "2 -",
                        },
                    }
                ],
            ),
            (
                "wert_er.htm",
                [
                    {
                        "paar": PAIR,
                        "runde": "Endrundentabelle",
                        "feldgroesse": 3,
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | A Richter A | Langsamer Walzer": "1",
                            "Wertungsrichter | B Richter B | Langsamer Walzer": "3",
                            "Wertungsrichter | C Richter C | Langsamer Walzer": "2",
                        },
                    }
                ],
            ),
            (
                "tabges.htm",
                [
                    {
                        "paar": PAIR,
                        "alle_weiteren_spalten": {"Aufstiegspunkte": "12"},
                    }
                ],
            ),
        ],
    )
    second = event_pages(
        "event-two",
        "15.03.2026 Hgr. D Standard",
        [OTHER_B, PAIR, OTHER_A],
    )
    return [*first, *second]


class DashboardDataTests(unittest.TestCase):
    def test_quality_issue_normalization_accepts_legacy_snake_case_fields(self):
        issue = {
            "event_id": "event-1",
            "code": "legacy_issue",
            "severity": "unvollständig",
            "tournament": "Testturnier",
            "round": "Vorrunde",
            "note": "Testhinweis",
            "source": "https://example.test/",
            "action": "Quelldaten prüfen.",
        }

        normalized = normalize_quality_issue(issue)

        self.assertEqual(normalized["event_id"], "event-1")
        self.assertEqual(normalized["code"], "legacy_issue")
        self.assertEqual(normalized["note"], "Testhinweis")

    def test_pair_options_include_events_without_starter_page(self):
        pages = sample_pages()
        missing = "Neue Taenzerin / Neuer Taenzer"
        pages.append(
            {
                "url": "https://other.test/event/ergwert.htm",
                "titel": "01.05.2026 Hgr. D Standard",
                "paare": [{"name": missing}],
            }
        )
        self.assertIn(missing, pair_options(pages))

    def test_tied_opponents_are_not_wins_and_unknown_ranks_stay_unknown(self):
        pages = event_pages(
            "ties", "01.03.2026 Hgr. D Standard", [PAIR, OTHER_A, OTHER_B]
        )
        rank = pages[1]
        for pair in rank["paare"]:
            pair.pop("platz_von")
            pair.pop("platz_bis")
        rank["paar_ergebnisse"] = [
            {
                "paar": name,
                "runde": "Finale",
                "platzierung_spalten": {"Platz": "2.-3."},
            }
            for name in (PAIR, OTHER_A)
        ]
        analysis = build_pair_dashboard(pages, PAIR)
        rows = {row["name"]: row for row in analysis["opponent_rows"]}
        self.assertEqual(rows[OTHER_A]["ties"], 1)
        self.assertEqual(rows[OTHER_A]["wins"], 0)
        self.assertEqual(rows[OTHER_B]["unknown"], 1)
        self.assertIsNone(analysis["events"][0]["normalized_place"])

    def test_incomplete_panel_does_not_invent_full_round_rate(self):
        pages = event_pages(
            "incomplete",
            "01.03.2026 Hgr. D Standard",
            [PAIR, OTHER_A],
            [
                (
                    "ergwert.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Vorrunde",
                            "richteranzahl": 3,
                            "richter_wertungen": [
                                {
                                    "kuerzel": "A",
                                    "name": "Ada Richter",
                                    "tanz": "Tango",
                                    "rohwert": "X",
                                    "kreuz": True,
                                }
                            ],
                        }
                    ],
                )
            ],
        )
        analysis = build_pair_dashboard(pages, PAIR)
        self.assertEqual(analysis["round_cross_rows"], [])
        row = analysis["rounds_by_event"][analysis["events"][0]["id"]][0]
        self.assertIsNone(row["cross_rate"])
        self.assertTrue(row["quality_issues"])

    def test_pair_dashboard_normalizes_places_and_tracks_opponents(self):
        pages = sample_pages()

        analysis = build_pair_dashboard(pages, PAIR)

        self.assertEqual(len(analysis["events"]), 2)
        first_event = analysis["events"][0]
        self.assertEqual(first_event["date"], date(2026, 3, 1))
        self.assertEqual(first_event["group"], "Hgr. D")
        self.assertEqual(first_event["discipline"], "Standard")
        self.assertEqual(first_event["field_size"], 3)
        self.assertEqual(first_event["normalized_place"], 1)
        self.assertEqual(analysis["events"][1]["normalized_place"], 0.5)

        opponents = {row["name"]: row for row in analysis["opponent_rows"]}
        self.assertEqual(opponents[OTHER_A]["starts"], 2)
        self.assertEqual(opponents[OTHER_A]["wins"], 2)
        self.assertEqual(opponents[OTHER_A]["losses"], 0)
        self.assertEqual(opponents[OTHER_B]["wins"], 1)
        self.assertEqual(opponents[OTHER_B]["losses"], 1)
        evidence = [
            row for row in analysis["opponent_evidence"] if row["name"] == OTHER_A
        ]
        self.assertEqual(len({row["event_id"] for row in evidence}), 2)
        self.assertEqual({row["group"] for row in evidence}, {"Hgr. D"})
        self.assertEqual({row["discipline"] for row in evidence}, {"Standard"})

    def test_opponents_merge_by_pair_name_and_include_clubs(self):
        pages = sample_pages()
        rank_pages = [
            page
            for page in pages
            if page["url"].endswith("ergwert.htm")
            and any(pair["name"] == OTHER_A for pair in page["paare"])
        ]
        for index, page in enumerate(rank_pages):
            opponent = next(pair for pair in page["paare"] if pair["name"] == OTHER_A)
            opponent["verein"] = f"Club {index + 1}"

        analysis = build_pair_dashboard(pages, PAIR)

        opponents = {row["name"]: row for row in analysis["opponent_rows"]}
        self.assertEqual(opponents[OTHER_A]["starts"], 2)
        self.assertEqual(opponents[OTHER_A]["club"], "Club 1; Club 2")
        evidence = [
            row for row in analysis["opponent_evidence"] if row["name"] == OTHER_A
        ]
        self.assertEqual({row["club"] for row in evidence}, {"Club 1", "Club 2"})

    def test_duplicate_ranked_pair_counts_once_and_conflicts_become_unknown(self):
        pages = event_pages(
            "duplicate-opponent",
            "01.03.2026 Hgr. D Standard",
            [PAIR, OTHER_A],
        )
        duplicate = dict(pages[1]["paare"][1])
        pages[1]["paare"][1]["verein"] = "Doppelter Verein"
        duplicate["verein"] = "Anderer Verein"
        duplicate["platz_von"] = 3
        duplicate["platz_bis"] = 3
        pages[1]["paare"].append(duplicate)

        analysis = build_pair_dashboard(pages, PAIR)

        evidence = [
            row for row in analysis["opponent_evidence"] if row["name"] == OTHER_A
        ]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["outcome"], "unknown")
        self.assertEqual(evidence[0]["opponent_place"], None)

    def test_quality_checks_are_event_scoped_and_actionable(self):
        pages = event_pages(
            "incomplete",
            "01.03.2026 Hgr. D Standard",
            [PAIR, OTHER_A],
        )

        analysis = build_pair_dashboard(pages, PAIR)

        issues = analysis["event_quality"]
        self.assertTrue(any(row["code"] == "missing_city" for row in issues))
        self.assertTrue(any(row["code"] == "missing_judge_data" for row in issues))
        self.assertTrue(all(row["event_id"] for row in issues))
        self.assertTrue(all(row["action"] for row in issues))

    def test_judge_meetings_include_panels_without_comparable_marks(self):
        pages = sample_pages()
        second = next(
            page for page in pages if page["url"].endswith("event-two/ergwert.htm")
        )
        second["wertungsrichter"] = [{"kuerzel": "X", "name": "Richter A"}]
        events = build_pair_dashboard(pages, PAIR)["events"]

        meetings = judge_meetings(events, "richter a")

        self.assertEqual(
            {event["title"] for event in meetings},
            {
                "01.03.2026 Hgr. D Standard",
                "15.03.2026 Hgr. D Standard",
            },
        )
        self.assertEqual(judge_meetings(events, "Unbekannt"), [])

    def test_dance_and_judge_views_use_normalized_values(self):
        analysis = build_pair_dashboard(sample_pages(), PAIR)

        dances = {row["dance"]: row for row in analysis["dance_rows"]}
        self.assertEqual(dances["Langsamer Walzer"]["normalized_place"], 1)
        self.assertEqual(dances["Tango"]["normalized_place"], 0.5)

    def test_dance_placements_can_be_compared_by_start_class(self):
        pages = sample_pages()
        second_pages = [page for page in pages if "/event-two/" in page["url"]]
        second_rank_page = next(
            page for page in second_pages if page["url"].endswith("ergwert.htm")
        )
        for page in second_pages:
            page["titel"] = "15.03.2026 Hgr. C Standard"
        second_rank_page["paar_ergebnisse"] = [
            {
                "paar": PAIR,
                "runde": "Endrundentabelle",
                "feldgroesse": 3,
                "platzierung_spalten": {"Platz": "2."},
                "alle_weiteren_spalten": {"Langsamer Walzer | Su": "2,0"},
            }
        ]

        analysis = build_pair_dashboard(pages, PAIR)

        by_dance_and_class = {
            (row["dance"], row["start_class"]): row
            for row in analysis["dance_class_rows"]
        }
        self.assertEqual(
            by_dance_and_class[("Langsamer Walzer", "D")]["normalized_place"], 1
        )
        self.assertEqual(
            by_dance_and_class[("Langsamer Walzer", "C")]["normalized_place"], 0.5
        )
        self.assertEqual(
            by_dance_and_class[("Langsamer Walzer", "C")]["observations"], 1
        )
        history = [
            row
            for row in analysis["dance_history_rows"]
            if row["dance"] == "Langsamer Walzer"
        ]
        self.assertEqual(len(history), 2)
        self.assertEqual(
            {row["start_class"] for row in history},
            {"C", "D"},
        )
        self.assertEqual(
            {row["date"] for row in history},
            {date(2026, 3, 1), date(2026, 3, 15)},
        )

        judges = {row["name"]: row for row in analysis["judge_rows"]}
        self.assertEqual(judges["Richter A"]["deviation_pp"], 75)
        self.assertEqual(judges["Richter B"]["deviation_pp"], -75)
        self.assertEqual(judges["Richter C"]["deviation_pp"], 0)

    def test_tournament_field_size_prefers_starter_list(self):
        pages = sample_pages()
        starter_page = next(
            page for page in pages if page["url"].endswith("event-one/starter.htm")
        )
        starter_page["paare"].append(
            {"startnr": "4", "name": "Lea Beispiel / Max Muster"}
        )

        event = build_pair_dashboard(pages, PAIR)["events"][0]

        self.assertEqual(event["field_size"], 4)
        self.assertEqual(summary_rows([event])[0]["Feldgröße"], 4)

    def test_judge_trends_include_normalized_preliminary_round_crosses(self):
        pages = sample_pages()
        tabges_page = next(
            page for page in pages if page["url"].endswith("event-one/tabges.htm")
        )
        pair_crosses = {
            PAIR: (3, 0, 1),
            OTHER_A: (0, 0, 1),
            OTHER_B: (0, 0, 0),
        }
        judges = ("Richter A", "Richter B", "Richter C")
        tabges_page["paar_ergebnisse"] = [
            {
                "paar": pair,
                "runde": "Vorrunde",
                "richteranzahl": 3,
                "moegliche_kreuzstimmen": 9,
                "richter_kreuze": [
                    {"kuerzel": chr(65 + index), "name": judge, "kreuze": crosses}
                    for index, (judge, crosses) in enumerate(
                        zip(judges, pair_crosses[pair], strict=True)
                    )
                ],
            }
            for pair in (PAIR, OTHER_A, OTHER_B)
        ]
        tabges_page["paar_ergebnisse"].append(
            {
                "paar": PAIR,
                "runde": "Zwischenrunde",
                "richter_kreuze": [
                    {"kuerzel": "X", "name": "Richter Ohne Nenner", "kreuze": 2}
                ],
            }
        )

        analysis = build_pair_dashboard(pages, PAIR)

        judge_rows = {row["name"]: row for row in analysis["judge_rows"]}
        self.assertAlmostEqual(judge_rows["Richter A"]["deviation_pp"], 19 / 24 * 100)
        self.assertAlmostEqual(judge_rows["Richter B"]["deviation_pp"], -17 / 24 * 100)
        self.assertEqual(judge_rows["Richter A"]["observations"], 2)
        self.assertEqual(judge_rows["Richter A"]["marks"], 4)
        self.assertNotIn("Richter Ohne Nenner", judge_rows)

    def test_tournament_details_and_explicit_points_are_extracted(self):
        analysis = build_pair_dashboard(sample_pages(), PAIR)
        first_event = analysis["events"][0]
        rounds = analysis["rounds_by_event"][first_event["id"]]

        self.assertEqual(rounds[0]["stage"], "Finale/Endrunde")
        self.assertEqual(rounds[0]["dance_places"]["Langsamer Walzer"], 1)
        self.assertIsNone(rounds[0]["crosses"])
        self.assertIsNone(rounds[0]["votes"])
        self.assertEqual(rounds[0]["field_size"], 3)
        self.assertEqual(rounds[0]["place"], 1)
        self.assertEqual(rounds[0]["normalized_place"], 1)
        self.assertEqual(rounds[0]["judges"], ["Richter A", "Richter B", "Richter C"])
        self.assertEqual(len(rounds[0]["individual_marks"]), 3)
        self.assertEqual(rounds[0]["dance_crosses"], [])
        self.assertIsNone(rounds[0]["cross_rate"])
        self.assertEqual(analysis["quality_issues"], [])
        self.assertNotIn(
            "A Richter A", [mark["judge"] for mark in rounds[0]["individual_marks"]]
        )
        self.assertEqual(analysis["point_records"][0]["points"], 12)

    def test_round_details_recover_complete_crosses_and_later_qualification(self):
        pages = event_pages(
            "round-recovery",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "ergwert.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Endrundentabelle",
                            "feldgroesse": 3,
                            "platzierung_spalten": {"Platz": "2."},
                        }
                    ],
                ),
                (
                    "tabges.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Vorrunde",
                            "feldgroesse": 3,
                            "richteranzahl": 2,
                            "kreuze_anzahl": None,
                            "moegliche_kreuzstimmen": None,
                            "richter_kreuze": [
                                {
                                    "kuerzel": "A",
                                    "name": "Richter A",
                                    "kreuze": 2,
                                    "max_kreuze": 3,
                                },
                                {
                                    "kuerzel": "B",
                                    "name": "Richter B",
                                    "kreuze": 1,
                                    "max_kreuze": 3,
                                },
                            ],
                        }
                    ],
                ),
            ],
        )

        analysis = build_pair_dashboard(pages, PAIR)
        rounds = analysis["rounds_by_event"][analysis["events"][0]["id"]]
        preliminary = next(row for row in rounds if row["stage"] == "Vorrunde")
        final = next(row for row in rounds if row["stage"] == "Finale/Endrunde")

        self.assertEqual(preliminary["crosses"], 3)
        self.assertEqual(preliminary["votes"], 6)
        self.assertEqual(preliminary["cross_rate"], 0.5)
        self.assertTrue(preliminary["cross_totals_derived"])
        self.assertTrue(preliminary["qualified"])
        self.assertTrue(preliminary["qualification_inferred"])
        self.assertEqual(preliminary["qualified_for"], "Finale/Endrunde")
        self.assertEqual(final["field_size"], 3)
        self.assertEqual(final["place"], 2)
        self.assertEqual(final["normalized_place"], 0.5)

    def test_numbered_intermediate_rounds_remain_separate(self):
        pages = event_pages(
            "numbered-rounds",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "tabges.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": stage,
                            "feldgroesse": 3,
                            "kreuze_anzahl": crosses,
                            "moegliche_kreuzstimmen": 6,
                        }
                        for stage, crosses in (
                            ("2. Zwischenrunde", 4),
                            ("1. Zwischenrunde", 3),
                        )
                    ],
                )
            ],
        )
        analysis = build_pair_dashboard(pages, PAIR)
        rounds = analysis["rounds_by_event"][analysis["events"][0]["id"]]
        self.assertEqual(
            [(row["stage"], row["crosses"]) for row in rounds],
            [("1. Zwischenrunde", 3), ("2. Zwischenrunde", 4)],
        )

    def test_final_judge_places_are_not_negative_cross_votes(self):
        pages = event_pages(
            "final-marks",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "ergwert.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Endrunde",
                            "feldgroesse": 3,
                            "richteranzahl": 2,
                            "tanzanzahl": 1,
                            "wertungen_vollstaendig": True,
                            "richter_wertungen": [
                                {
                                    "kuerzel": code,
                                    "name": name,
                                    "tanz": "Tango",
                                    "rohwert": value,
                                    "kreuz": False,
                                }
                                for code, name, value in (
                                    ("A", "Richter A", "1"),
                                    ("B", "Richter B", "3"),
                                )
                            ],
                        }
                    ],
                )
            ],
        )
        analysis = build_pair_dashboard(pages, PAIR)
        final = analysis["rounds_by_event"][analysis["events"][0]["id"]][0]
        self.assertIsNone(final["cross_rate"])
        self.assertEqual(final["dance_crosses"], [])
        self.assertEqual(analysis["quality_issues"], [])

    def test_round_details_omit_empty_unclassified_results(self):
        pages = event_pages(
            "empty-round",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "erg.htm",
                    [{"paar": PAIR, "runde": "Ergebnis (Runde nicht angegeben)"}],
                )
            ],
        )

        analysis = build_pair_dashboard(pages, PAIR)

        self.assertEqual(analysis["rounds_by_event"][analysis["events"][0]["id"]], [])

    def test_round_details_do_not_attach_overall_rank_to_unrelated_round(self):
        pages = event_pages(
            "round-rank-scope",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "ergwert.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Vorrunde",
                            "feldgroesse": 4,
                            "platzierung_spalten": {"Platz": "8."},
                        }
                    ],
                ),
                (
                    "erg.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Finale/Endrunde",
                            "feldgroesse": 4,
                        }
                    ],
                ),
                (
                    "tabges.htm",
                    [
                        {
                            "paar": PAIR,
                            "runde": "Vorrunde",
                            "feldgroesse": 10,
                            "kreuze_anzahl": 7,
                            "moegliche_kreuzstimmen": 20,
                        }
                    ],
                ),
            ],
        )

        analysis = build_pair_dashboard(pages, PAIR)
        rounds = analysis["rounds_by_event"][analysis["events"][0]["id"]]

        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["stage"], "Vorrunde")
        self.assertEqual(rounds[0]["field_size"], 10)
        self.assertEqual(rounds[0]["place"], 8)
        self.assertAlmostEqual(rounds[0]["normalized_place"], 2 / 9)

    def test_tabges_round_crosses_include_judges_and_complete_qualification_cutoff(
        self,
    ):
        pages = event_pages(
            "round-crosses",
            "01.04.2026 Hgr. D Standard",
            [PAIR, OTHER_A, OTHER_B],
            [
                (
                    "tabges.htm",
                    [
                        {
                            "paar": PAIR,
                            "paar_id": "startnr:1",
                            "startnr": "1",
                            "runde": "Vorrunde",
                            "feldgroesse": 3,
                            "kreuze_anzahl": 5,
                            "moegliche_kreuzstimmen": 6,
                            "qualifiziert": True,
                            "qualifiziert_fuer": "Finale/Endrunde",
                            "richter_kreuze": [
                                {"kuerzel": "A", "name": "Richter A", "kreuze": 3},
                                {"kuerzel": "B", "name": "Richter B", "kreuze": 2},
                            ],
                        },
                        {
                            "paar": OTHER_A,
                            "paar_id": "startnr:2",
                            "startnr": "2",
                            "runde": "Vorrunde",
                            "feldgroesse": 3,
                            "kreuze_anzahl": 2,
                            "moegliche_kreuzstimmen": 6,
                            "qualifiziert": False,
                            "qualifiziert_fuer": "Finale/Endrunde",
                        },
                        {
                            "paar": OTHER_B,
                            "paar_id": "startnr:3",
                            "startnr": "3",
                            "runde": "Vorrunde",
                            "feldgroesse": 3,
                            "kreuze_anzahl": 4,
                            "moegliche_kreuzstimmen": 6,
                            "qualifiziert": True,
                            "qualifiziert_fuer": "Finale/Endrunde",
                        },
                        {
                            "paar": PAIR,
                            "paar_id": "startnr:1",
                            "startnr": "1",
                            "runde": "Zwischenrunde",
                            "kreuze_anzahl": 3,
                            "moegliche_kreuzstimmen": None,
                        },
                    ],
                )
            ],
        )
        tabges_page = next(page for page in pages if page["url"].endswith("tabges.htm"))
        tabges_page["alle_paare_erfasst"] = True

        analysis = build_pair_dashboard(pages, PAIR)
        event = analysis["events"][0]
        round_data = analysis["rounds_by_event"][event["id"]][0]

        self.assertEqual(round_data["crosses"], 5)
        self.assertEqual(round_data["votes"], 6)
        self.assertAlmostEqual(round_data["cross_rate"], 5 / 6)
        self.assertTrue(round_data["qualified"])
        self.assertEqual(round_data["qualified_for"], "Finale/Endrunde")
        self.assertEqual(round_data["cross_cutoff"], 4)
        self.assertEqual(round_data["cross_margin"], 1)
        self.assertEqual(
            [mark["judge"] for mark in round_data["judge_crosses"]],
            ["Richter A", "Richter B"],
        )
        self.assertEqual(
            analysis["round_cross_rows"],
            [
                {
                    "stage": "Vorrunde",
                    "cross_rate": 5 / 6,
                    "observations": 1,
                    "events": 1,
                }
            ],
        )

        tabges_page["alle_paare_erfasst"] = False
        incomplete = build_pair_dashboard(pages, PAIR)
        incomplete_round = incomplete["rounds_by_event"][incomplete["events"][0]["id"]][
            0
        ]
        self.assertIsNone(incomplete_round["cross_cutoff"])

    def test_judge_trends_aggregate_by_name_when_panel_letter_changes(self):
        pages = sample_pages()
        first_judge_page = next(
            page for page in pages if page["url"].endswith("event-one/wert_er.htm")
        )
        first_judge_page["paar_ergebnisse"].append(
            {
                "paar": PAIR,
                "runde": "Endrundentabelle",
                "feldgroesse": 3,
                "alle_weiteren_spalten": {
                    "Wertungsrichter | A Richter A | Tango": "1",
                    "Wertungsrichter | B Richter B | Tango": "3",
                    "Wertungsrichter | C Richter C | Tango": "2",
                },
            }
        )
        pages.append(
            {
                "url": "https://example.test/event-two/wert_er.htm",
                "titel": "15.03.2026 Hgr. D Standard",
                "paare": [],
                "paar_ergebnisse": [
                    {
                        "paar": PAIR,
                        "runde": "Endrundentabelle",
                        "feldgroesse": 3,
                        "alle_weiteren_spalten": {
                            "Wertungsrichter | D Richter A | Langsamer Walzer": "1",
                            "Wertungsrichter | E Richter B | Langsamer Walzer": "3",
                            "Wertungsrichter | F Richter C | Langsamer Walzer": "2",
                        },
                    }
                ],
            }
        )

        analysis = build_pair_dashboard(pages, PAIR)

        judges = {row["name"]: row for row in analysis["judge_rows"]}
        self.assertEqual(judges["Richter A"]["observations"], 3)
        self.assertEqual(judges["Richter B"]["observations"], 3)
        self.assertEqual(judges["Richter C"]["observations"], 3)
        self.assertEqual(judges["Richter A"]["tournaments"], 2)
        self.assertEqual(judges["Richter A"]["marks"], 3)

    def test_judge_trends_aggregate_comma_name_order_variants(self):
        pages = sample_pages()
        first_judge_page = next(
            page for page in pages if page["url"].endswith("event-one/wert_er.htm")
        )
        result = first_judge_page["paar_ergebnisse"][0]
        fields = result["alle_weiteren_spalten"]
        fields["Wertungsrichter | A Kison, Werner | Langsamer Walzer"] = fields.pop(
            "Wertungsrichter | A Richter A | Langsamer Walzer"
        )
        pages.append(
            {
                "url": "https://example.test/event-two/wert_er.htm",
                "titel": "15.03.2026 Hgr. D Standard",
                "paare": [],
                "paar_ergebnisse": [
                    {
                        "paar": PAIR,
                        "runde": "Endrundentabelle",
                        "feldgroesse": 3,
                        "richter_wertungen": [
                            {
                                "kuerzel": "B",
                                "name": "Werner Kison",
                                "tanz": "Langsamer Walzer",
                                "rohwert": "1",
                            }
                        ],
                    }
                ],
            }
        )

        analysis = build_pair_dashboard(pages, PAIR)

        judges = {row["name"]: row for row in analysis["judge_rows"]}
        self.assertIn("Werner Kison", judges)
        self.assertNotIn("Kison, Werner", judges)
        self.assertEqual(judges["Werner Kison"]["tournaments"], 1)
        self.assertEqual(judges["Werner Kison"]["marks"], 1)
        self.assertEqual(judges["Werner Kison"]["raw_tournaments"], 2)
        self.assertEqual(judges["Werner Kison"]["raw_marks"], 2)
        evidence = [
            row for row in analysis["judge_evidence"] if row["name"] == "Werner Kison"
        ]
        self.assertEqual(len(evidence), 1)

    def test_tournament_archive_rows_show_city_or_unknown_marker(self):
        pages = sample_pages()
        for page in pages:
            if "event-one" in page["url"]:
                page["stadt"] = "Norderstedt"

        rows = summary_rows(build_pair_dashboard(pages, PAIR)["events"])

        self.assertEqual(rows[0]["Ort"], "Norderstedt")
        self.assertEqual(rows[1]["Ort"], "—")

    def test_pair_options_and_date_filters(self):
        pages = sample_pages()

        self.assertEqual(pair_options(pages), sorted([PAIR, OTHER_A, OTHER_B]))
        analysis = build_pair_dashboard(pages, PAIR)
        filtered = filter_events(
            analysis["events"],
            group="Hgr. D",
            discipline="Standard",
            date_range=(date(2026, 3, 10), date(2026, 3, 31)),
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["date"], date(2026, 3, 15))

    def test_pair_tournament_filter_keeps_all_pages_of_matching_events(self):
        matching_pages = sample_pages()
        unrelated_pages = event_pages(
            "unrelated-event",
            "20.03.2026 Hgr. D Standard",
            [OTHER_A, OTHER_B],
        )

        filtered = filter_tournaments_for_pair(
            [*matching_pages, *unrelated_pages], PAIR
        )

        self.assertEqual(
            {page["url"] for page in filtered},
            {page["url"] for page in matching_pages},
        )
        self.assertTrue(any(page["url"].endswith("wert_er.htm") for page in filtered))

    def test_pair_tournament_filter_requires_pair_name(self):
        with self.assertRaises(ValueError):
            filter_tournaments_for_pair(sample_pages(), " ")


if __name__ == "__main__":
    unittest.main()
