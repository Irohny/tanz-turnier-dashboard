import unittest

from etl.auswertung import (
    canonical_round,
    competition_key,
    normalized_rank,
    pair_matches,
)
from etl.domain import (
    PlacementOutcome,
    RoundStage,
    compare_places,
    pair_place,
    qualification_cutoff,
)


class DomainRegressionTests(unittest.TestCase):
    def test_qualification_cutoff_rejects_partial_and_contradictory_evidence(self):
        records = {
            "a": {"feldgroesse": 2, "kreuze_anzahl": 3, "qualifiziert": True},
            "b": {"feldgroesse": 2, "kreuze_anzahl": 2, "qualifiziert": False},
        }
        self.assertEqual(qualification_cutoff(records, True), 3)
        for changes in (
            {"qualifiziert": None},
            {"kreuze_anzahl": 4},
            {"rundendaten_vollstaendig": False},
            {"feldgroesse": 3},
        ):
            with self.subTest(changes=changes):
                invalid = {**records, "b": {**records["b"], **changes}}
                self.assertIsNone(qualification_cutoff(invalid, True))

    def test_competitions_use_origin_and_full_directory_not_title(self):
        first = {"url": "https://a.test/2026/event/ergwert.htm", "titel": "Finale"}
        sibling = {"url": "https://a.test/2026/event/tabges.htm", "titel": "Gesamt"}
        self.assertEqual(competition_key(first), competition_key(sibling))
        for url in (
            "https://b.test/2026/event/ergwert.htm",
            "https://a.test/2025/event/ergwert.htm",
        ):
            with self.subTest(url=url):
                self.assertNotEqual(
                    competition_key(first), competition_key({**first, "url": url})
                )

    def test_specific_and_numbered_rounds_are_preserved(self):
        self.assertIs(canonical_round("Vorschlussrunde"), RoundStage.SEMI_FINAL)
        self.assertEqual(canonical_round("1. Zwischenrunde"), "1. Zwischenrunde")
        self.assertEqual(canonical_round("Zwischenrunde 2"), "2. Zwischenrunde")

    def test_place_comparisons_use_domain_outcomes(self):
        self.assertIs(compare_places((1, 1), (2, 2)), PlacementOutcome.WINS)
        self.assertIs(compare_places((2, 2), (1, 1)), PlacementOutcome.LOSSES)
        self.assertIs(compare_places((1, 2), (1, 2)), PlacementOutcome.TIES)
        self.assertIs(compare_places(None, (1, 1)), PlacementOutcome.UNKNOWN)

    def test_invalid_ranks_do_not_become_scores(self):
        for rank, size in ((8, 6), (0, 6), (float("nan"), 6), (float("inf"), 6)):
            with self.subTest(rank=rank, size=size):
                self.assertIsNone(normalized_rank(rank, size))

    def test_full_pair_identity_does_not_match_name_substrings(self):
        self.assertFalse(
            pair_matches(
                "Ann Muster / Ben Beispiel",
                {"name": "Joann Muster / Ben Beispiel"},
            )
        )
        self.assertTrue(
            pair_matches(
                "Ben Beispiel / Ann Muster",
                {"name": "57 Ann Muster / Ben Beispiel", "startnr": "57"},
            )
        )
        self.assertTrue(
            pair_matches(
                "Ben Beispiel / Ann Muster",
                {"name": "Ann Muster / Ben Beispiel (57)"},
            )
        )

    def test_tabges_place_with_optional_upper_bound(self):
        pair = {"name": "Ada Muster / Ben Beispiel"}
        page = {
            "url": "https://example.test/event/tabges.htm",
            "paar_ergebnisse": [
                {"paar": pair["name"], "alle_weiteren_spalten": {"Platz von": "1"}}
            ],
        }
        fields = page["paar_ergebnisse"][0]["alle_weiteren_spalten"]
        self.assertEqual(pair_place([page], pair), (1, 1))
        fields["Platz bis"] = "2"
        self.assertEqual(pair_place([page], pair), (1, 2))
        fields.pop("Platz von")
        self.assertIsNone(pair_place([page], pair))
