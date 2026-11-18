import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from etl.archiv import (
    SCHEMA_VERSION,
    archive_json_file,
    archive_pages,
    clean_archived_judge_names,
    clean_judge_name,
    load_pages,
)


class TurnierArchivTests(unittest.TestCase):
    def test_partial_and_json_reimports_preserve_origin_and_city(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "stadt": "Bremen",
            "paare": [],
            "paar_ergebnisse": [],
            "parser_version": 4,
        }
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "new.sqlite"
            origin = "https://example.test/index.htm"
            archive_pages(database, origin, [page])
            partial = {**page, "stadt": ""}
            self.assertEqual(archive_pages(database, page["url"], [partial]), (0, 0, 1))
            json_file = Path(temporary) / "results.json"
            json_file.write_text(json.dumps([partial]), encoding="utf-8")
            self.assertEqual(archive_json_file(database, json_file), (0, 0, 1))
            stored = load_pages(database)[0]
            self.assertEqual(stored["stadt"], "Bremen")
            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute("SELECT start_url FROM source_pages").fetchone()[
                        0
                    ],
                    origin,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT last_start_url FROM source_imports"
                    ).fetchone()[0],
                    json_file.resolve().as_uri(),
                )

    def test_invalid_page_rolls_back_whole_batch(self):
        page = {"url": "https://example.test/event/erg.htm", "paare": []}
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "new.sqlite"
            archive_pages(database, "https://example.test/", [page])
            for invalid in (
                [None],
                [{"runde": "Finale"}],
                [{"paar": "A / B", "kreuze_anzahl": -1}],
            ):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    archive_pages(
                        database,
                        "https://example.test/",
                        [
                            {**page, "stadt": "Bremen"},
                            {
                                "url": "https://example.test/bad.htm",
                                "paar_ergebnisse": invalid,
                            },
                        ],
                    )
                self.assertNotIn("stadt", load_pages(database)[0])

    def test_reading_does_not_upgrade_archive_and_rejects_future_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "new.sqlite"
            archive_pages(
                database,
                "https://example.test/",
                [{"url": "https://example.test/erg.htm"}],
            )
            for version in (1, SCHEMA_VERSION + 1):
                with sqlite3.connect(database) as connection:
                    connection.execute(f"PRAGMA user_version = {version}")
                before = database.read_bytes()
                if version > SCHEMA_VERSION:
                    with self.assertRaises(ValueError):
                        load_pages(database)
                else:
                    self.assertEqual(len(load_pages(database)), 1)
                self.assertEqual(database.read_bytes(), before)

    def test_version_one_database_migrates_pair_club_and_round_columns(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "titel": "Hauptgruppe Standard",
            "paare": [{"name": "Ada Muster / Ben Beispiel", "verein": "TTC Example"}],
            "paar_ergebnisse": [
                {
                    "paar": "Ada Muster / Ben Beispiel",
                    "verein": "TTC Example",
                    "runde": "Finale",
                    "tanz": "Langsamer Walzer",
                    "kreuze_anzahl": 0,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "turniere.sqlite"
            with sqlite3.connect(database) as connection:
                connection.executescript("""
                    CREATE TABLE source_pages (
                        url TEXT PRIMARY KEY,
                        start_url TEXT NOT NULL,
                        category_key TEXT NOT NULL,
                        title TEXT NOT NULL,
                        imported_at TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE ranked_pairs (
                        page_url TEXT NOT NULL,
                        rank_index INTEGER NOT NULL,
                        pair_key TEXT NOT NULL,
                        pair_name TEXT NOT NULL,
                        start_number TEXT NOT NULL,
                        PRIMARY KEY (page_url, rank_index)
                    );
                    CREATE TABLE pair_results (
                        page_url TEXT NOT NULL,
                        result_index INTEGER NOT NULL,
                        pair_key TEXT NOT NULL,
                        pair_id TEXT NOT NULL,
                        pair_name TEXT NOT NULL,
                        start_number TEXT NOT NULL,
                        round_name TEXT NOT NULL,
                        dance TEXT NOT NULL,
                        field_size INTEGER,
                        cross_count INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        PRIMARY KEY (page_url, result_index)
                    );
                    PRAGMA user_version = 1;
                    """)

            archive_pages(database, "https://example.test/event/", [page])

            with sqlite3.connect(database) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                rank_club = connection.execute(
                    "SELECT pair_club FROM ranked_pairs"
                ).fetchone()[0]
                result_club = connection.execute(
                    "SELECT pair_club FROM pair_results"
                ).fetchone()[0]
                round_columns = connection.execute(
                    "SELECT round_code, cross_votes, qualified, qualification_round "
                    "FROM pair_results"
                ).fetchone()

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(rank_club, "TTC Example")
        self.assertEqual(result_club, "TTC Example")
        self.assertEqual(round_columns, ("", None, None, ""))

    def test_import_is_idempotent_and_updates_changed_page(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "titel": "Hauptgruppe Standard",
            "paare": [
                {
                    "startnr": "57",
                    "name": "Ada Muster / Ben Beispiel",
                    "verein": "TTC Example",
                },
            ],
            "paar_ergebnisse": [
                {
                    "paar": "Ada Muster / Ben Beispiel",
                    "verein": "TTC Example",
                    "paar_id": "startnr:57",
                    "startnr": "57",
                    "runde": "Finale",
                    "tanz": "Langsamer Walzer",
                    "feldgroesse": 2,
                    "kreuze_anzahl": 1,
                    "rundencode": "F 1",
                    "moegliche_kreuzstimmen": 20,
                    "qualifiziert": True,
                    "qualifiziert_fuer": "Finale/Endrunde",
                    "richter_wertungen": [
                        {
                            "kuerzel": "A",
                            "name": "Alex Richter",
                            "tanz": "Langsamer Walzer",
                            "rohwert": "1 x",
                            "kreuz": True,
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "turniere.sqlite"
            first = archive_pages(database, "https://example.test/event/", [page])
            repeated = archive_pages(database, "https://example.test/event/", [page])

            changed_page = {
                **page,
                "paar_ergebnisse": [{**page["paar_ergebnisse"][0], "kreuze_anzahl": 2}],
            }
            updated = archive_pages(
                database, "https://example.test/event/", [changed_page]
            )
            stored_pages = load_pages(database)
            with sqlite3.connect(database) as connection:
                page_count = connection.execute(
                    "SELECT COUNT(*) FROM source_pages"
                ).fetchone()[0]
                result_count = connection.execute(
                    "SELECT COUNT(*) FROM pair_results"
                ).fetchone()[0]
                judge_count = connection.execute(
                    "SELECT COUNT(*) FROM judge_marks"
                ).fetchone()[0]
                rank_count = connection.execute(
                    "SELECT COUNT(*) FROM ranked_pairs"
                ).fetchone()[0]
                ranked_club = connection.execute(
                    "SELECT pair_club FROM ranked_pairs"
                ).fetchone()[0]
                result_club = connection.execute(
                    "SELECT pair_club FROM pair_results"
                ).fetchone()[0]
                round_data = connection.execute(
                    "SELECT round_code, cross_votes, qualified, qualification_round "
                    "FROM pair_results"
                ).fetchone()

        self.assertEqual(first, (1, 0, 0))
        self.assertEqual(repeated, (0, 0, 1))
        self.assertEqual(updated, (0, 1, 0))
        self.assertEqual(len(stored_pages), 1)
        self.assertEqual(stored_pages[0]["paar_ergebnisse"][0]["kreuze_anzahl"], 2)
        self.assertEqual(
            (page_count, result_count, judge_count, rank_count), (1, 1, 1, 1)
        )
        self.assertEqual(ranked_club, "TTC Example")
        self.assertEqual(result_club, "TTC Example")
        self.assertEqual(round_data, ("F 1", 20, 1, "Finale/Endrunde"))

    def test_load_missing_database_reports_error_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "missing.sqlite"
            with self.assertRaises(FileNotFoundError):
                load_pages(database)
            self.assertFalse(database.exists())

    def test_judge_names_are_cleaned_on_import_and_in_existing_archive(self):
        page = {
            "url": "https://example.test/event/wert_er.htm",
            "titel": "Hauptgruppe Standard",
            "paare": [],
            "wertungsrichter": [
                {"kuerzel": "A", "name": "Kison, Werner"},
                {"kuerzel": "B", "name": "Werner Kison"},
            ],
            "paar_ergebnisse": [
                {
                    "paar": "Ada Muster / Ben Beispiel",
                    "richter_wertungen": [
                        {
                            "kuerzel": "A",
                            "name": "A Kison, Werner",
                            "tanz": "Langsamer Walzer",
                            "rohwert": "1",
                            "kreuz": False,
                        },
                        {
                            "kuerzel": "B",
                            "name": "Werner Kison",
                            "tanz": "Langsamer Walzer",
                            "rohwert": "2",
                            "kreuz": False,
                        },
                    ],
                    "richter_kreuze": [
                        {
                            "kuerzel": "C",
                            "name": "Kison, Werner",
                            "kreuze": 1,
                            "max_kreuze": 2,
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "turniere.sqlite"
            archive_pages(database, "https://example.test/event/", [page])
            self.assertEqual(
                load_pages(database)[0]["paar_ergebnisse"][0]["richter_wertungen"][0][
                    "name"
                ],
                "Werner Kison",
            )
            self.assertEqual(
                [judge["name"] for judge in load_pages(database)[0]["wertungsrichter"]],
                ["Werner Kison", "Werner Kison"],
            )

            with sqlite3.connect(database) as connection:
                page_json = connection.execute(
                    "SELECT payload_json FROM source_pages WHERE url = ?",
                    (page["url"],),
                ).fetchone()[0]
                result_json = connection.execute(
                    "SELECT payload_json FROM pair_results WHERE page_url = ?",
                    (page["url"],),
                ).fetchone()[0]
                page_payload = json.loads(page_json)
                result_payload = json.loads(result_json)
                page_payload["paar_ergebnisse"][0]["richter_wertungen"][0][
                    "name"
                ] = "A Kison, Werner"
                page_payload["paar_ergebnisse"][0]["richter_kreuze"][0][
                    "name"
                ] = "Kison, Werner"
                result_payload["richter_wertungen"][0]["name"] = "A Kison, Werner"
                result_payload["richter_kreuze"][0]["name"] = "Kison, Werner"
                page_json = json.dumps(
                    page_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    "UPDATE source_pages SET payload_json = ? WHERE url = ?",
                    (page_json, page["url"]),
                )
                connection.execute(
                    "UPDATE pair_results SET payload_json = ? WHERE page_url = ?",
                    (
                        json.dumps(
                            result_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        page["url"],
                    ),
                )
                connection.execute(
                    "UPDATE judge_marks SET judge_name = ? WHERE page_url = ?",
                    ("A Kison, Werner", page["url"]),
                )

            self.assertEqual(clean_archived_judge_names(database), 2)
            self.assertEqual(clean_archived_judge_names(database), 0)
            stored = load_pages(database)[0]["paar_ergebnisse"][0]["richter_wertungen"][
                0
            ]["name"]
            stored_cross_name = load_pages(database)[0]["paar_ergebnisse"][0][
                "richter_kreuze"
            ][0]["name"]
            with sqlite3.connect(database) as connection:
                judge_name = connection.execute(
                    "SELECT judge_name FROM judge_marks WHERE page_url = ?",
                    (page["url"],),
                ).fetchone()[0]
                payload_json, content_hash = connection.execute(
                    "SELECT payload_json, content_hash FROM source_pages WHERE url = ?",
                    (page["url"],),
                ).fetchone()

        self.assertEqual(stored, "Werner Kison")
        self.assertEqual(stored_cross_name, "Werner Kison")
        self.assertEqual(judge_name, "Werner Kison")
        self.assertEqual(
            hashlib.sha256(payload_json.encode("utf-8")).hexdigest(), content_hash
        )

    def test_judge_names_with_comma_share_canonical_order(self):
        self.assertEqual(clean_judge_name("A", "A Kison, Werner"), "Werner Kison")
        self.assertEqual(clean_judge_name("", "Kison, Werner"), "Werner Kison")
        self.assertEqual(clean_judge_name("B", "Werner Kison"), "Werner Kison")

    def test_existing_json_can_be_imported(self):
        page = {
            "url": "https://example.test/event/ergwert.htm",
            "titel": "Hauptgruppe Standard",
            "paare": [],
            "paar_ergebnisse": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            json_file = Path(temp_dir) / "ergebnis.json"
            database = Path(temp_dir) / "turniere.sqlite"
            json_file.write_text(json.dumps([page]), encoding="utf-8")

            imported = archive_json_file(database, json_file)

            self.assertEqual(imported, (1, 0, 0))
            self.assertEqual(load_pages(database), [page])


if __name__ == "__main__":
    unittest.main()
