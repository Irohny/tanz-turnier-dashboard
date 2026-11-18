"""SQLite-Speicher für gecrawlte Turnierergebnisse."""

import argparse
import copy
import hashlib
import json
import sqlite3
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from etl.domain import competition_key, integer_value, pair_identity

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_pages (
    url TEXT PRIMARY KEY,
    start_url TEXT NOT NULL,
    category_key TEXT NOT NULL,
    title TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ranked_pairs (
    page_url TEXT NOT NULL REFERENCES source_pages(url) ON DELETE CASCADE,
    rank_index INTEGER NOT NULL,
    pair_key TEXT NOT NULL,
    pair_name TEXT NOT NULL,
    pair_club TEXT NOT NULL DEFAULT '',
    start_number TEXT NOT NULL,
    PRIMARY KEY (page_url, rank_index)
);

CREATE TABLE IF NOT EXISTS source_imports (
    page_url TEXT PRIMARY KEY REFERENCES source_pages(url) ON DELETE CASCADE,
    last_start_url TEXT NOT NULL,
    last_imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pair_results (
    page_url TEXT NOT NULL REFERENCES source_pages(url) ON DELETE CASCADE,
    result_index INTEGER NOT NULL,
    pair_key TEXT NOT NULL,
    pair_id TEXT NOT NULL,
    pair_name TEXT NOT NULL,
    pair_club TEXT NOT NULL DEFAULT '',
    start_number TEXT NOT NULL,
    round_name TEXT NOT NULL,
    round_code TEXT NOT NULL DEFAULT '',
    dance TEXT NOT NULL,
    field_size INTEGER,
    cross_count INTEGER NOT NULL,
    cross_votes INTEGER,
    qualified INTEGER,
    qualification_round TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    PRIMARY KEY (page_url, result_index)
);

CREATE TABLE IF NOT EXISTS judge_marks (
    page_url TEXT NOT NULL,
    result_index INTEGER NOT NULL,
    mark_index INTEGER NOT NULL,
    judge_code TEXT NOT NULL,
    judge_name TEXT NOT NULL,
    dance TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    is_cross INTEGER NOT NULL,
    PRIMARY KEY (page_url, result_index, mark_index),
    FOREIGN KEY (page_url, result_index)
        REFERENCES pair_results(page_url, result_index) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pair_results_pair_key
    ON pair_results(pair_key);
CREATE INDEX IF NOT EXISTS idx_pair_results_round
    ON pair_results(round_name, dance);
CREATE INDEX IF NOT EXISTS idx_judge_marks_name
    ON judge_marks(judge_code, judge_name);
"""


def _pair_identity(name: str) -> str:
    return pair_identity(name)


def clean_judge_name(code: str, name: str) -> str:
    """Removes the panel code and canonicalizes ``Last, First`` name order."""
    code = str(code or "").strip()
    name = " ".join(str(name or "").split())
    if code and name[: len(code)].casefold() == code.casefold():
        remainder = name[len(code) :]
        if remainder and remainder[0].isspace():
            name = remainder.strip()
    parts = [part.strip() for part in name.split(",")]
    if len(parts) == 2 and all(parts):
        name = f"{parts[1]} {parts[0]}"
    return " ".join(name.split())


def _normalize_page_judge_names(page: dict) -> int:
    cleaned = 0
    for judge in page.get("wertungsrichter", []):
        if not isinstance(judge, dict):
            continue
        name = clean_judge_name(judge.get("kuerzel", ""), judge.get("name", ""))
        if name != judge.get("name", ""):
            judge["name"] = name
            cleaned += 1
    for result in page.get("paar_ergebnisse", []):
        for mark in result.get("richter_wertungen", []):
            if not isinstance(mark, dict):
                continue
            name = clean_judge_name(mark.get("kuerzel", ""), mark.get("name", ""))
            if name != mark.get("name", ""):
                mark["name"] = name
                cleaned += 1
        for mark in result.get("richter_kreuze", []):
            if not isinstance(mark, dict):
                continue
            name = clean_judge_name(mark.get("kuerzel", ""), mark.get("name", ""))
            if name != mark.get("name", ""):
                mark["name"] = name
                cleaned += 1
    return cleaned


def _category_key(page: dict) -> str:
    return "|".join(competition_key(page))


def _field_size(result: dict) -> int | None:
    value = integer_value(result.get("feldgroesse"))
    return value if value is not None and value > 0 else None


def _connect(database: str | Path) -> sqlite3.Connection:
    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        connection.close()
        raise ValueError(
            f"Datenbankversion {version} ist neuer als unterstützt "
            f"({SCHEMA_VERSION})."
        )
    connection.executescript(SCHEMA)
    if version < 2:
        for table in ("ranked_pairs", "pair_results"):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if "pair_club" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN pair_club TEXT NOT NULL DEFAULT ''"
                )
    if version < 3:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(pair_results)")
        }
        for name, definition in (
            ("round_code", "TEXT NOT NULL DEFAULT ''"),
            ("cross_votes", "INTEGER"),
            ("qualified", "INTEGER"),
            ("qualification_round", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE pair_results ADD COLUMN {name} {definition}"
                )
    if version < SCHEMA_VERSION:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return connection


@contextmanager
def _connection(database: str | Path) -> Generator[sqlite3.Connection, None, None]:
    connection = _connect(database)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def archive_pages(
    database: str | Path, start_url: str, pages: list[dict]
) -> tuple[int, int, int]:
    """Speichert Seiten idempotent und gibt (neu, aktualisiert, unverändert) zurück."""
    inserted = updated = unchanged = 0
    imported_at = datetime.now(UTC).isoformat()

    with _connection(database) as connection:
        for source_page in pages:
            _validate_page(source_page)
            page = copy.deepcopy(source_page)
            _normalize_page_judge_names(page)
            url = str(page.get("url", "")).strip()
            if not url:
                raise ValueError("Eine archivierte Ergebnisseite hat keine URL.")

            existing = connection.execute(
                "SELECT content_hash, start_url, payload_json "
                "FROM source_pages WHERE url = ?",
                (url,),
            ).fetchone()
            origin_url = start_url
            if existing:
                previous_page = json.loads(existing[2])
                if not str(page.get("stadt") or "").strip() and previous_page.get(
                    "stadt"
                ):
                    page["stadt"] = previous_page["stadt"]
                origin_url = existing[1]
                if origin_url.startswith("file:") and start_url.startswith(
                    ("http:", "https:")
                ):
                    origin_url = start_url

            payload = json.dumps(
                page, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if existing and existing[0] == content_hash:
                connection.execute(
                    "UPDATE source_pages SET start_url = ? WHERE url = ?",
                    (origin_url, url),
                )
                connection.execute(
                    "INSERT INTO source_imports VALUES (?, ?, ?) "
                    "ON CONFLICT(page_url) DO UPDATE SET "
                    "last_start_url=excluded.last_start_url, "
                    "last_imported_at=excluded.last_imported_at",
                    (url, start_url, imported_at),
                )
                unchanged += 1
                continue

            if existing:
                connection.execute("DELETE FROM source_pages WHERE url = ?", (url,))
                updated += 1
            else:
                inserted += 1

            connection.execute(
                """
                INSERT INTO source_pages
                    (url, start_url, category_key, title, imported_at,
                     content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url,
                    origin_url,
                    _category_key(page),
                    str(page.get("titel", "")),
                    imported_at,
                    content_hash,
                    payload,
                ),
            )
            connection.execute(
                "INSERT INTO source_imports VALUES (?, ?, ?)",
                (url, start_url, imported_at),
            )

            for rank_index, pair in enumerate(page.get("paare", []), start=1):
                pair_name = str(pair.get("name") or pair.get("paar") or "").strip()
                if not pair_name:
                    continue
                connection.execute(
                    """
                    INSERT INTO ranked_pairs
                        (page_url, rank_index, pair_key, pair_name, pair_club,
                         start_number)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url,
                        rank_index,
                        _pair_identity(pair_name),
                        pair_name,
                        str(pair.get("verein") or pair.get("club") or "").strip(),
                        str(pair.get("startnr", "")),
                    ),
                )

            for result_index, result in enumerate(page.get("paar_ergebnisse", [])):
                pair_name = str(result.get("paar", "")).strip()
                if not pair_name:
                    continue
                pair_id = str(result.get("paar_id") or result.get("startnr") or "")
                qualified = result.get("qualifiziert")
                if not isinstance(qualified, bool):
                    qualified = None
                try:
                    cross_votes = int(result["moegliche_kreuzstimmen"])
                except (KeyError, TypeError, ValueError):
                    cross_votes = None
                connection.execute(
                    """
                    INSERT INTO pair_results
                        (page_url, result_index, pair_key, pair_id, pair_name,
                         pair_club, start_number, round_name, round_code, dance,
                         field_size, cross_count, cross_votes, qualified,
                         qualification_round, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url,
                        result_index,
                        _pair_identity(pair_name),
                        pair_id,
                        pair_name,
                        str(result.get("verein") or result.get("club") or "").strip(),
                        str(result.get("startnr", "")),
                        str(result.get("runde", "")),
                        str(result.get("rundencode", "")),
                        str(result.get("tanz", "")),
                        _field_size(result),
                        int(result.get("kreuze_anzahl", 0) or 0),
                        cross_votes,
                        int(qualified) if qualified is not None else None,
                        str(result.get("qualifiziert_fuer", "")),
                        json.dumps(
                            result,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )

                for mark_index, mark in enumerate(result.get("richter_wertungen", [])):
                    connection.execute(
                        """
                        INSERT INTO judge_marks
                            (page_url, result_index, mark_index, judge_code,
                             judge_name, dance, raw_value, is_cross)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            url,
                            result_index,
                            mark_index,
                            str(mark.get("kuerzel", "")),
                            str(mark.get("name", "")),
                            str(mark.get("tanz") or result.get("tanz", "")),
                            str(mark.get("rohwert", "")),
                            int(bool(mark.get("kreuz"))),
                        ),
                    )

    return inserted, updated, unchanged


def load_pages(database: str | Path) -> list[dict]:
    """Lädt die zuletzt archivierte Version jeder Ergebnisseite."""
    if not Path(database).is_file():
        raise FileNotFoundError(f"Archiv nicht gefunden: {database}")
    connection = sqlite3.connect(
        Path(database).resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"Archiv-Schema {version} ist neuer als die unterstützte Version "
                f"({SCHEMA_VERSION})."
            )
        rows = connection.execute(
            "SELECT payload_json FROM source_pages ORDER BY category_key, url"
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def _validate_page(page: dict) -> None:
    if not isinstance(page, dict):
        raise ValueError(  # noqa: TRY004
            "Ungültige Ergebnisseite: erwartet wird ein Objekt."
        )
    if not isinstance(page.get("url"), str) or not page["url"].strip():
        raise ValueError("Eine archivierte Ergebnisseite hat keine URL.")
    for key in ("paare", "paar_ergebnisse", "wertungsrichter"):
        values = page.get(key, [])
        if not isinstance(values, list) or not all(
            isinstance(value, dict) for value in values
        ):
            raise ValueError(f"{page['url']}: {key} muss eine Liste von Objekten sein.")
    for result in page.get("paar_ergebnisse", []):
        if not isinstance(result.get("paar"), str) or not result["paar"].strip():
            raise ValueError(f"{page['url']}: Eine Ergebniszeile hat keinen Paarnamen.")
        for key in ("feldgroesse", "moegliche_kreuzstimmen", "kreuze_anzahl"):
            raw = result.get(key)
            if raw is not None:
                number = integer_value(raw)
                minimum = 0 if key == "kreuze_anzahl" else 1
                if number is None or number < minimum:
                    raise ValueError(
                        f"{page['url']}: Ungültiger Wert für {key}: {raw!r}"
                    )
        if result.get("qualifiziert") is not None and not isinstance(
            result["qualifiziert"], bool
        ):
            raise ValueError(
                f"{page['url']}: qualifiziert muss wahr, falsch oder unbekannt sein."
            )
        for key in ("richter_wertungen", "richter_kreuze"):
            values = result.get(key, [])
            if not isinstance(values, list) or not all(
                isinstance(value, dict) for value in values
            ):
                raise ValueError(
                    f"{page['url']}: {key} muss eine Liste von Objekten sein."
                )
        for key in ("alle_weiteren_spalten", "platzierung_spalten", "kreuze"):
            if not isinstance(result.get(key, {}), dict):
                raise ValueError(  # noqa: TRY004
                    f"{page['url']}: {key} muss ein Objekt sein."
                )


def archive_json_file(
    database: str | Path, json_file: str | Path
) -> tuple[int, int, int]:
    """Importiert eine vorhandene Crawler-JSON-Datei in das Archiv."""
    source_path = Path(json_file)
    pages = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        raise ValueError("Die JSON-Wurzel muss eine Liste von Ergebnisseiten sein.")
    if not pages:
        raise ValueError("Die JSON-Datei enthält keine Ergebnisseiten.")
    return archive_pages(database, source_path.resolve().as_uri(), pages)


def clean_archived_judge_names(database: str | Path) -> int:
    """Normalizes judge names in every stored copy."""
    if not Path(database).is_file():
        raise FileNotFoundError(f"Archiv nicht gefunden: {database}")

    cleaned = 0
    with _connection(database) as connection:
        rows = connection.execute(
            "SELECT url, payload_json FROM source_pages ORDER BY url"
        ).fetchall()
        for url, raw_page in rows:
            page = json.loads(raw_page)
            changed = _normalize_page_judge_names(page)
            if not changed:
                continue

            payload = json.dumps(
                page, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            connection.execute(
                """
                UPDATE source_pages
                SET payload_json = ?, content_hash = ?
                WHERE url = ?
                """,
                (payload, content_hash, url),
            )
            for result_index, result in enumerate(page.get("paar_ergebnisse", [])):
                result_payload = json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    """
                    UPDATE pair_results SET payload_json = ?
                    WHERE page_url = ? AND result_index = ?
                    """,
                    (result_payload, url, result_index),
                )
                for mark_index, mark in enumerate(result.get("richter_wertungen", [])):
                    connection.execute(
                        """
                        UPDATE judge_marks SET judge_name = ?
                        WHERE page_url = ? AND result_index = ? AND mark_index = ?
                        """,
                        (mark.get("name", ""), url, result_index, mark_index),
                    )
            cleaned += changed
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datei", default="ergebnis.json", help="Crawler-JSON importieren"
    )
    parser.add_argument("--db", required=True, help="SQLite-Archiv")
    args = parser.parse_args()
    try:
        inserted, updated, unchanged = archive_json_file(args.db, args.datei)
    except (OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as error:
        print(f"[Fehler] Import fehlgeschlagen: {error}", file=sys.stderr)
        return 1
    print(
        f"Archiv aktualisiert ({inserted} neu, {updated} aktualisiert, "
        f"{unchanged} unverändert)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
