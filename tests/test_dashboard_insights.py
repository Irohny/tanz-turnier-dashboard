import unittest
from datetime import date

from etl.insights import (
    CLASS_ORDER,
    advancement_progress,
    location_statistics,
    placement_statistics,
    progression_ladder,
    round_statistics,
)


class DashboardInsightTests(unittest.TestCase):
    def test_recent_form_uses_only_three_latest_dated_starts(self):
        events = [
            {"id": "old", "date": date(2025, 1, 1), "normalized_place": 0.1},
            {"id": "a", "date": date(2026, 1, 1), "normalized_place": 0.5},
            {"id": "b", "date": date(2026, 2, 1), "normalized_place": None},
            {"id": "c", "date": date(2026, 3, 1), "normalized_place": 0.9},
            {"id": "undated", "date": None, "normalized_place": 1.0},
        ]

        result = placement_statistics(events)

        self.assertEqual(result["starts"], 5)
        self.assertEqual(result["recent_starts"], 3)
        self.assertEqual(result["recent_observations"], 2)
        self.assertEqual(result["recent_median"], 0.7)
        self.assertEqual(result["best"], 1.0)

    def test_round_rates_exclude_unknown_and_funnel_counts_events_once(self):
        events = [{"id": str(index)} for index in range(16)]
        rounds = {
            str(index): [
                {
                    "stage": "Vorrunde",
                    "qualified": (
                        True if index < 12 else False if index < 15 else None
                    ),
                    "cross_rate": None,
                    "cross_cutoff": None,
                    "cross_margin": None,
                }
            ]
            for index in range(16)
        }
        rounds["0"].extend(
            [
                {
                    "stage": "1. Zwischenrunde",
                    "qualified": True,
                    "cross_rate": 0.5,
                    "cross_cutoff": 10,
                    "cross_margin": 1,
                },
                {
                    "stage": "2. Zwischenrunde",
                    "qualified": False,
                    "cross_rate": 0.7,
                    "cross_cutoff": None,
                    "cross_margin": None,
                },
            ]
        )

        funnel, summary, outcomes = round_statistics(events, rounds)

        preliminary = next(row for row in summary if row["Runde"] == "Vorrunde")
        intermediate = next(row for row in summary if row["Runde"] == "Zwischenrunde")
        self.assertEqual(preliminary["Weiterkommensquote"], 12 / 15)
        self.assertEqual(preliminary["Unbekannt"], 1)
        self.assertEqual(intermediate["Teilnahmen"], 2)
        self.assertEqual(intermediate["Knapp"], 1)
        self.assertEqual(
            next(row for row in funnel if row["Runde"] == "Vorrunde")["Turniere"], 16
        )
        self.assertEqual(outcomes["unknown"], 1)

    def test_location_summary_keeps_unknown_location_separate(self):
        events = [
            {
                "id": "a",
                "city": " Hannover ",
                "normalized_place": 0.8,
                "place": 2,
                "field_size": 5,
                "date": date(2026, 1, 1),
            },
            {
                "id": "b",
                "city": "hannover",
                "normalized_place": None,
                "place": None,
                "field_size": None,
                "date": None,
            },
            {
                "id": "c",
                "city": "",
                "normalized_place": 0.4,
                "place": 4,
                "field_size": 6,
                "date": date(2026, 2, 1),
            },
        ]

        result = location_statistics(events, {})

        self.assertEqual(len(result), 2)
        hannover = next(row for row in result if row["Ort"].casefold() == "hannover")
        self.assertEqual(hannover["Turniere"], 2)
        self.assertEqual(hannover["Auswertbare Plätze"], 1)
        self.assertEqual(hannover["Ø normierter Platz"], 0.8)
        self.assertEqual(
            next(row for row in result if row["Ort"] == "Ort unbekannt")["Turniere"],
            1,
        )
        self.assertIsNone(hannover["Spannweite"])

    def test_progression_ladder_counts_all_standard_classes_until_each_limit(self):
        events = [
            {
                "id": f"event-{index}",
                "title": f"Turnier {index}",
                "date": date(2026, 1, index),
                "group": "Hgr. D" if index < 7 else "Hgr. C",
                "discipline": "Standard",
                "place_range": (1, 1),
            }
            for index in range(1, 9)
        ]
        events.extend(
            [
                {
                    "id": "latin",
                    "title": "Latein",
                    "date": date(2026, 1, 9),
                    "group": "Hgr. D",
                    "discipline": "Latein",
                    "place_range": (1, 1),
                },
                {
                    "id": "undated",
                    "title": "Ohne Datum",
                    "date": None,
                    "group": "Hgr. D",
                    "discipline": "Standard",
                    "place_range": (1, 1),
                },
            ]
        )
        records = [
            {
                "event_id": f"event-{index}",
                "label": "Aufstiegspunkte",
                "points": 15 if index < 7 else 25 if index == 7 else 5,
            }
            for index in range(1, 9)
        ]

        result = progression_ladder(events, records, "Aufstiegspunkte")

        self.assertEqual(list(result["classes"]), list(CLASS_ORDER))
        d_progress = result["classes"]["D"]
        c_progress = result["classes"]["C"]
        self.assertEqual(d_progress["points_earned"], 115)
        self.assertEqual(d_progress["counted_places"], 7)
        self.assertTrue(d_progress["complete"])
        self.assertEqual(d_progress["transition_date"], date(2026, 1, 7))
        self.assertEqual(
            [event["id"] for event in d_progress["events"]],
            [f"event-{index}" for index in range(1, 8)],
        )
        self.assertEqual(c_progress["points_earned"], 5)
        self.assertEqual(c_progress["starts"], 1)
        self.assertEqual(c_progress["events"][0]["group"], "Hgr. C")
        self.assertEqual(result["undated_events"], 1)

    def test_advancement_progress_does_not_count_overlapping_places(self):
        events = [
            {
                "id": "rank-six",
                "group": "Hgr. D",
                "discipline": "Standard",
                "place_range": (6, 6),
            },
            {
                "id": "rank-seven",
                "group": "Hgr. D",
                "discipline": "Standard",
                "place_range": (7, 7),
            },
            {
                "id": "overlap",
                "group": "Hgr. D",
                "discipline": "Standard",
                "place_range": (6, 7),
            },
        ]
        records = [
            {"event_id": "rank-six", "label": "Aufstiegspunkte", "points": 12},
            {"event_id": "rank-seven", "label": "Bonus", "points": 99},
        ]

        result = advancement_progress(
            events, records, "C", "Hgr. D", "Standard", "Aufstiegspunkte"
        )

        self.assertEqual(result["points_earned"], 12)
        self.assertEqual(result["counted_places"], 1)
        self.assertEqual(result["unknown_places"], 1)
        self.assertEqual(result["rank_max"], 6)

    def test_round_summary_keeps_final_qualification_without_result_unknown(self):
        events = [{"id": "qualified"}, {"id": "no-rounds"}]
        rounds = {
            "qualified": [
                {
                    "stage": "Vorrunde",
                    "qualified": True,
                    "qualified_for": "Finale",
                    "cross_rate": None,
                    "cross_cutoff": None,
                    "cross_margin": None,
                }
            ],
            "no-rounds": [],
        }

        _, _, result = round_statistics(events, rounds)

        self.assertEqual(result["finals"], 0)
        self.assertEqual(result["final_decisions"], 0)
        self.assertEqual(result["final_unknown"], 2)
        self.assertEqual(result["qualified_final_without_result"], 1)


if __name__ == "__main__":
    unittest.main()
