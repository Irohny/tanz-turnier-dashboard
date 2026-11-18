#!/usr/bin/env python3
"""
TopTurnier-Ergebnis-Crawler
===========================
Liest die von TopTurnier (Windows, V9.x) exportierten HTML-Ergebnisseiten aus:

  * pro Runde alle Kreuze eines Paares (Paar wird per Namen angegeben)
  * Platzierungen / Summen des Paares je Runde (alle Spalten der Zeile)
  * Liste der Wertungsrichter
  * Liste der gestarteten Paare

Aufruf:
    uv sync
    uv run python -m etl.crawler https://www.1scn.de/turnierergebnisse_tanzen_2026/index.htm \
        --paar "Mustermann Musterfrau" --out ergebnis.json

    --paar     Namensteile (Reihenfolge egal, Gross-/Kleinschreibung egal, Umlaute egal)
    --debug    zeigt alle erkannten Tabellen mit Spaltenkoepfen -> hilfreich zum Nachjustieren
    --cache    Ordner, in dem die geladenen HTML-Seiten abgelegt werden
"""

import argparse
import csv
import ipaddress
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from etl.archiv import archive_pages, clean_judge_name
from etl.domain import ROUND_BY_CODE, canonical_round, competition_key, place_range

UA = {"User-Agent": "Mozilla/5.0 (TopTurnier-Ergebnis-Crawler; privat)"}
ROUND_RE = re.compile(
    r"(vor|zwischen|end|halb|viertel|vorschluss|qualifikations?)\s*runde|finale?|\d+\.\s*runde|runde\s*\d+",
    re.IGNORECASE,
)
CROSS_VALUES = {"X", "x", "\u00d7", "\u2717", "\u2715", "+"}
PARSER_VERSION = 6


# --------------------------------------------------------------------------- Helfer
def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def norm(s: str) -> str:
    """klein, ohne Akzente/Umlaute, ohne Satzzeichen -> robuster Namensvergleich"""
    s = unicodedata.normalize("NFKD", s.lower().replace("\u00df", "ss"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def name_matches(query: str, text: str) -> bool:
    hay = norm(text)
    return all(tok in hay for tok in norm(query).split())


def table_cell_grid(table: Tag):
    """HTML-Tabelle -> Zellraster mit aufgelösten colspan-/rowspan-Zellen."""
    cells, trs = {}, table.find_all("tr")
    for r, tr in enumerate(trs):
        c = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in cells:
                c += 1
            try:
                rs, cs = int(str(cell.get("rowspan", "1"))), int(
                    str(cell.get("colspan", "1"))
                )
            except ValueError:
                rs = cs = 1
            for dr in range(rs):
                for dc in range(cs):
                    cells[(r + dr, c + dc)] = cell
            c += cs
    ncols = max((c for _, c in cells), default=-1) + 1
    return [[cells.get((r, c), "") for c in range(ncols)] for r in range(len(trs))]


def table_grid(table: Tag):
    """HTML-Tabelle -> Textmatrix (colspan/rowspan werden aufgeloest)."""
    return [
        [
            clean(cell.get_text(" ", strip=True)) if isinstance(cell, Tag) else ""
            for cell in row
        ]
        for row in table_cell_grid(table)
    ]


def _pair_cell_details(cell: Tag | str, fallback_name: str) -> tuple[str, str]:
    if not isinstance(cell, Tag):
        return fallback_name, ""
    club_node = cell.find(["i", "em"])
    if club_node is None:
        return fallback_name, ""
    club = clean(club_node.get_text(" ", strip=True))
    full_text = clean(cell.get_text(" ", strip=True))
    if club and full_text.endswith(club):
        return full_text[: -len(club)].strip(), club
    return fallback_name, club


def _row_club(row: list[str], labels: list[str], pair_index: int) -> str:
    for index, label in enumerate(labels):
        if (
            index != pair_index
            and re.search(r"\b(?:club|verein)\b", label, re.IGNORECASE)
            and index < len(row)
            and row[index]
        ):
            return clean(row[index])
    return ""


def looks_like_couple(text: str) -> bool:
    if not text or len(text) < 6:
        return False
    if re.fullmatch(
        r"\s*(?:teilnehmer|paar)\s*/\s*(?:club|verein)\s*", text, re.IGNORECASE
    ):
        return False
    if re.search(r"[A-Za-z\u00c0-\u017f].*/.*[A-Za-z\u00c0-\u017f]", text):
        return True
    if re.match(r"\s*[A-Z]{1,2}\s+(?:Dr\.?\s+)?[A-Z\u00c4\u00d6\u00dc]", text):
        return False
    if re.search(
        r"\b(?:wertungsrichter|platzierung|platz|summe|teilnehmer|paar|nr)\b",
        text,
        re.IGNORECASE,
    ):
        return False
    words = re.findall(r"[A-Za-z\u00c0-\u017f][\w\-']+", text)
    return len(words) >= 3 and not re.search(r"\d", text)


def leaf_tables(soup):
    return [t for t in soup.find_all("table") if not t.find("table")]


def validate_start_url(start_url: str) -> str:
    url = start_url.strip()
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError as error:
        raise ValueError(
            "Bitte eine gültige öffentliche HTTP(S)-URL eingeben."
        ) from error

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or hostname.lower().rstrip(".") == "localhost"
        or hostname.lower().endswith((".localhost", ".local"))
    ):
        raise ValueError("Bitte eine gültige öffentliche HTTP(S)-URL eingeben.")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError(
                "Lokale oder private IP-Adressen können nicht gecrawlt werden."
            )
    return url


def _directory_prefix(path: str) -> str:
    return path.rsplit("/", 1)[0] + "/"


def _same_site(host_a: str | None, host_b: str | None) -> bool:
    if not host_a or not host_b:
        return False
    return host_a.lower().removeprefix("www.") == host_b.lower().removeprefix("www.")


# --------------------------------------------------------------------------- Crawling
def crawl(
    start_url: str,
    delay: float,
    max_pages: int,
    cache: Path | None,
    errors: list[str] | None = None,
):
    start_url = validate_start_url(start_url)
    base = urlparse(start_url)
    root_url = urldefrag(start_url)[0]
    scopes = {(base.netloc.lower(), _directory_prefix(base.path))}
    seen, queue, pages = set(), [root_url], {}
    s = requests.Session()
    s.headers.update(UA)
    while queue and len(pages) < max_pages:
        url = urldefrag(queue.pop(0))[0]
        if url in seen:
            continue
        seen.add(url)
        try:
            r = s.get(url, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            message = f"{url}: {e}"
            if errors is not None:
                errors.append(message)
            print(f"[warn] {message}", file=sys.stderr)
            continue
        if "html" not in r.headers.get("content-type", "html"):
            continue
        soup = BeautifulSoup(r.content, "html.parser")  # erkennt <meta charset> selbst
        pages[url] = soup
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            (
                cache
                / (
                    re.sub(r"[^\w.]+", "_", urlparse(url).path.strip("/"))
                    or "index.htm"
                )
            ).write_bytes(r.content)
        for link in soup.find_all(["a", "frame", "iframe"]):
            reference = link.get("href") if link.name == "a" else link.get("src")
            if not isinstance(reference, str) or not reference:
                continue
            nxt = urldefrag(urljoin(url, reference))[0]
            p = urlparse(nxt)
            in_scope = any(
                p.netloc.lower() == host and p.path.startswith(prefix)
                for host, prefix in scopes
            )
            external_turnier_link = link.name == "a" and p.path.lower().startswith(
                "/wp-external/turnier/"
            )
            embedded_results_index = link.name in {
                "frame",
                "iframe",
            } and p.path.lower().endswith(("/index.htm", "/index.html"))
            if (
                not in_scope
                and url == root_url
                and _same_site(p.hostname, base.hostname)
                and (external_turnier_link or embedded_results_index)
            ):
                validate_start_url(nxt)
                scopes.add((p.netloc.lower(), _directory_prefix(p.path)))
                in_scope = True
            if (
                in_scope
                and p.path.lower().endswith((".htm", ".html", "/"))
                and nxt not in seen
            ):
                queue.append(nxt)
        time.sleep(delay)
    if queue and len(pages) >= max_pages:
        message = (
            f"Seitenlimit ({max_pages}) erreicht; weitere Links wurden nicht geladen."
        )
        if errors is not None:
            errors.append(message)
        print(f"[warn] {message}", file=sys.stderr)
    s.close()
    return pages


# --------------------------------------------------------------------------- Parser
def page_title(soup) -> str:
    for tag in ("h1", "h2", "title"):
        t = soup.find(tag)
        if t and clean(t.get_text()):
            return clean(t.get_text())
    return ""


def page_city(soup) -> str:
    for node in (soup.find(class_="comphead"), soup.find("title")):
        if node is None:
            continue
        text = clean(node.get_text())
        match = re.search(r"\bin\s+(.+?)\s*\.?$", text, re.IGNORECASE)
        if match:
            city = match.group(1).strip().rstrip(".")
            if city:
                return city
    return ""


def _page_directory(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    origin = (
        f"{parsed.scheme.lower()}://" f"{parsed.netloc.lower().removeprefix('www.')}"
    )
    directory = parsed.path.rsplit("/", 1)[0] or "/"
    return origin, directory.rstrip("/") + "/" if directory != "/" else "/"


def _ancestor_city(url: str, cities: dict[tuple[str, str], str]) -> str:
    origin, directory = _page_directory(url)
    while True:
        city = cities.get((origin, directory))
        if city:
            return city
        parent = directory.rstrip("/").rsplit("/", 1)[0] or "/"
        if parent == directory:
            return ""
        directory = parent.rstrip("/") + "/" if parent != "/" else "/"


def extract_judges(soup):
    """Wertungsrichter: Tabellenzeilen 'A | Name | Verein' oder Textzeilen 'A  Name'."""
    judges = {}
    for node in soup.find_all(string=re.compile("Wertungsrichter", re.IGNORECASE)):
        parent = node.parent
        if not isinstance(parent, Tag):
            continue
        for tbl in parent.find_all_next("table", limit=2):
            if tbl.find("table"):
                continue
            for row in table_grid(tbl):
                row = [c for c in row if c]
                if (
                    len(row) >= 2
                    and re.fullmatch(r"[A-Z]{1,2}", row[0])
                    and "/" not in row[1]
                    and len(row[1]) > 3
                ):
                    judges.setdefault(
                        row[0], clean_judge_name(row[0], " ".join(row[1:]))
                    )
        for txt in parent.find_all_next(string=True, limit=80):
            m = re.match(
                r"^\s*([A-Z]{1,2})\s*[:=\-\u2013]?\s+([A-Z\u00c4\u00d6\u00dc][^/]{4,})$",
                txt.strip(),
            )
            if m and not ROUND_RE.search(m.group(2)):
                judges.setdefault(
                    m.group(1), clean_judge_name(m.group(1), clean(m.group(2)))
                )
    return [{"kuerzel": k, "name": v} for k, v in sorted(judges.items())]


def split_header_body(grid):
    """Kopfzeilen = alle Zeilen vor der ersten Zeile mit einer Paar-Zelle."""
    for i, row in enumerate(grid):
        if any(
            clean(cell).casefold()
            in {"platz", "paar", "teilnehmer", "teilnehmer club", "teilnehmer/club"}
            for cell in row
        ):
            continue
        if any(looks_like_couple(c) for c in row):
            return grid[:i], grid[i:]
    return grid, []


def column_labels(header_rows, ncols):
    labels = []
    for j in range(ncols):
        parts = []
        for hr in header_rows:
            v = hr[j] if j < len(hr) else ""
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        labels.append(" | ".join(parts) or f"Spalte{j + 1}")
    return labels


def _ergwert_column_labels(header_rows, ncols):
    """Aligns judge columns when the result header has dance abbreviation cells."""
    labels = column_labels(header_rows, ncols)
    judge_row = next(
        (
            row
            for row in header_rows
            if sum(bool(re.match(r"^[A-Z]{1,2}\s+.+$", clean(value))) for value in row)
            >= 2
            and any(clean(value).casefold() == "su" for value in row)
        ),
        None,
    )
    if judge_row is None:
        return labels

    group_ends = [
        index
        for index, value in enumerate(judge_row)
        if clean(value).casefold() == "su"
    ]
    if not group_ends:
        return labels

    first_group_start = next(
        (
            index
            for index, value in enumerate(judge_row)
            if re.match(r"^[A-Z]{1,2}\s+.+$", clean(value))
        ),
        None,
    )
    if first_group_start is None:
        return labels

    ignored = {
        "platz",
        "paar",
        "teilnehmer club",
        "teilnehmer",
        "nr",
        "r",
        "summe",
        "ausrechnung",
    }
    dance_names = []
    for row in header_rows[: header_rows.index(judge_row)]:
        for value in row:
            value = clean(value)
            if (
                not value
                or value.casefold() in ignored
                or value.casefold() == "su"
                or re.fullmatch(r"[A-Z]{1,3}", value)
                or value in dance_names
            ):
                continue
            dance_names.append(value)
    if len(dance_names) < len(group_ends):
        return labels

    previous_end = first_group_start - 1
    for dance, end in zip(dance_names, group_ends, strict=False):
        start = previous_end + 1
        for index in range(start, end + 1):
            if index < len(judge_row) and clean(judge_row[index]):
                labels[index] = f"{dance} | {clean(judge_row[index])}"
        previous_end = end
    return labels


def table_section_heading(rows):
    heading = ""
    ignored = {
        "ausrechnung",
        "platz",
        "summe",
        "nr",
        "teilnehmer club",
        "wertungsrichter",
    }
    for row in rows:
        values = {clean(cell) for cell in row if clean(cell)}
        if len(values) != 1:
            continue
        candidate = next(iter(values))
        if (
            candidate.lower() not in ignored
            and len(candidate) < 60
            and not re.fullmatch(r"\d+(?:[.,]\d+)?", candidate)
            and not ROUND_RE.search(candidate)
        ):
            heading = candidate
    return heading


def _round_stage_from_text(value: str) -> str | None:
    return canonical_round(value)


def _round_stage_from_code(value: str) -> str | None:
    for token in clean(value).upper().split():
        if token in ROUND_BY_CODE:
            return ROUND_BY_CODE[token]
    return None


def _round_heading_from_row(row: list[str]) -> str | None:
    values = {clean(cell) for cell in row if clean(cell)}
    if len(values) != 1:
        return None
    heading = next(iter(values))
    return _round_stage_from_text(heading) if ROUND_RE.search(heading) else None


def _cell_lines(cell: Tag | str) -> list[str]:
    if isinstance(cell, Tag):
        return [clean(value) for value in cell.stripped_strings if clean(value)]
    value = clean(str(cell))
    return [value] if value else []


def _integer_value(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,4})\s*", clean(value))
    return int(match.group(1)) if match else None


def _tabges_pair_header(
    cell_grid: list[list[Tag | str]],
) -> tuple[int, dict[int, dict[str, str]]]:
    best_row = -1
    best_pairs: dict[int, dict[str, str]] = {}
    for row_index, row in enumerate(cell_grid):
        pairs = {}
        for column, cell in enumerate(row):
            if not isinstance(cell, Tag):
                continue
            tooltip = cell.find("span", class_=re.compile(r"tooltip"))
            name = clean(tooltip.get_text(" ", strip=True)) if tooltip else ""
            if not looks_like_couple(name):
                continue
            visible = clean(
                " ".join(
                    str(child)
                    for child in cell.children
                    if isinstance(child, NavigableString)
                )
            )
            match = re.search(r"\b(\d{1,4})\b", visible)
            startnr = match.group(1) if match else ""
            pairs[column] = {
                "startnr": startnr,
                "name": name,
                "paar_id": f"startnr:{startnr}" if startnr else f"name:{norm(name)}",
            }
        if len(pairs) > len(best_pairs):
            best_row, best_pairs = row_index, pairs
    return best_row, best_pairs


def _tabges_judges(cell: Tag | str) -> list[dict[str, str]]:
    judges = []
    for line in _cell_lines(cell):
        match = re.match(r"^([A-Z]{1,2})\s*[.)]?\s+(.+)$", line)
        if match:
            code, name = match.groups()
            judges.append({"kuerzel": code, "name": clean_judge_name(code, name)})
    return judges


def _dance_count_from_soup(soup) -> int:
    dances = set()
    for _, table in iter_tables_with_round(soup):
        grid = table_grid(table)
        if not grid:
            continue
        header, _ = split_header_body(grid)
        labels = column_labels(header, max(map(len, grid)))
        dances.update(
            label.rsplit("|", 1)[0].strip()
            for label in labels
            if label.rsplit("|", 1)[-1].strip().lower() == "su"
        )
    return len(dances)


def _result_dance_counts(soup) -> set[int]:
    abbreviations = {
        "LW",
        "TG",
        "WW",
        "SF",
        "QU",
        "QS",
        "SB",
        "SA",
        "CC",
        "CCC",
        "RB",
        "RU",
        "PD",
        "JV",
        "JI",
    }
    counts = set()
    for table in leaf_tables(soup):
        for row in table.find_all("tr"):
            cells = [
                clean(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            if not cells or cells[0].casefold() != "platz":
                continue
            if len(cells) < 4 or "teilnehmer" not in cells[1].casefold():
                continue
            if cells[-1].casefold() != "pz":
                continue
            dances = [value.upper() for value in cells[2:-1]]
            if (
                dances
                and len(set(dances)) == len(dances)
                and set(dances) <= abbreviations
            ):
                counts.add(len(dances))
    return counts


def _parse_tabges_page(soup, query, include_all, dance_count):
    pairs_by_id: dict[str, dict[str, str]] = {}
    round_results: list[dict] = []
    summary_fields: dict[str, dict[str, str]] = {}

    for table in leaf_tables(soup):
        cell_grid = table_cell_grid(table)
        grid = table_grid(table)
        if not grid:
            continue
        pair_header_row, pair_columns = _tabges_pair_header(cell_grid)
        if not pair_columns:
            continue

        for pair in pair_columns.values():
            pairs_by_id.setdefault(pair["paar_id"], pair)

        judges: list[dict[str, str]] = []
        judge_cross_values: dict[str, list[str]] = {}
        latest_stage = ""
        expected_participants: int | None = len(pair_columns)
        latest_results: dict[str, dict] = {}
        for row_index, row in enumerate(grid):
            if row_index >= len(cell_grid) or not row:
                continue
            label_cell = cell_grid[row_index][0] if cell_grid[row_index] else ""
            label_lines = _cell_lines(label_cell)
            label = clean(" ".join(label_lines))
            if not label:
                continue

            parsed_judges = _tabges_judges(label_cell)
            if parsed_judges:
                judges = parsed_judges
                judge_cross_values = {
                    pair["paar_id"]: (
                        _cell_lines(cell_grid[row_index][column])
                        if column < len(cell_grid[row_index])
                        else []
                    )
                    for column, pair in pair_columns.items()
                }
                continue

            result_match = re.search(
                r"\bErgebnis\s+(?:der|des)\s+(.+)", label, re.IGNORECASE
            )
            stage = (
                _round_stage_from_text(result_match.group(1)) if result_match else None
            )
            if stage:
                latest_stage = stage
                latest_results = {}
                round_dance_count = dance_count
                if dance_count and any(
                    count is not None and count > dance_count
                    for values in judge_cross_values.values()
                    for value in values
                    if (count := _integer_value(value)) is not None
                ):
                    round_dance_count = None
                field_size = sum(
                    _integer_value(row[column]) is not None
                    for column in pair_columns
                    if column < len(row)
                )
                round_complete = (
                    expected_participants is not None
                    and field_size == expected_participants
                )
                for column, pair in pair_columns.items():
                    if column >= len(row):
                        continue
                    crosses = _integer_value(row[column])
                    if crosses is None:
                        continue
                    judge_crosses = []
                    for judge, raw_count in zip(
                        judges, judge_cross_values.get(pair["paar_id"], [])
                    ):
                        count = _integer_value(raw_count)
                        if count is not None:
                            judge_crosses.append(
                                {
                                    **judge,
                                    "kreuze": count,
                                    "max_kreuze": round_dance_count or None,
                                }
                            )
                    result = {
                        "runde": stage,
                        "paar": pair["name"],
                        "paar_id": pair["paar_id"],
                        "startnr": pair["startnr"],
                        "feldgroesse": expected_participants,
                        "rundendaten_vollstaendig": round_complete,
                        "richteranzahl": len(judges),
                        "kreuze_anzahl": crosses,
                        "moegliche_kreuzstimmen": (
                            len(judges) * round_dance_count
                            if judges and round_dance_count
                            else None
                        ),
                        "richter_kreuze": judge_crosses,
                        "qualifiziert": None,
                        "qualifiziert_fuer": "",
                        "kreuze": {},
                        "platzierung_spalten": {},
                        "alle_weiteren_spalten": {label: row[column]},
                        "richter_wertungen": [],
                    }
                    latest_results[pair["paar_id"]] = result
                    round_results.append(result)
                expected_participants = None
                judge_cross_values = {}
                continue

            qualification_match = re.search(
                r"\bQualifiziert\s+f(?:ü|ue)r\s+(?:die\s+)?(.+)",
                label,
                re.IGNORECASE,
            )
            if qualification_match and latest_stage:
                target_stage = _round_stage_from_text(qualification_match.group(1))
                for column, pair in pair_columns.items():
                    result = latest_results.get(pair["paar_id"])
                    if result is None or column >= len(row):
                        continue
                    value = clean(row[column])
                    cell = cell_grid[row_index][column]
                    result["qualifiziert"] = (
                        True
                        if is_cross_value(value)
                        else (
                            False
                            if isinstance(cell, Tag) and value in {"", "-", "–"}
                            else None
                        )
                    )
                    result["qualifiziert_fuer"] = target_stage or clean(
                        qualification_match.group(1)
                    )
                if (
                    latest_results
                    and all(
                        isinstance(result.get("qualifiziert"), bool)
                        for result in latest_results.values()
                    )
                    and all(
                        result["rundendaten_vollstaendig"]
                        for result in latest_results.values()
                    )
                ):
                    expected_participants = sum(
                        result["qualifiziert"] for result in latest_results.values()
                    )
                else:
                    expected_participants = None
                continue

            if row_index <= pair_header_row or re.match(
                r"^(?:Anzahl Teilnehmer|Startnummer|Wertungsrichter)\b",
                label,
                re.IGNORECASE,
            ):
                continue

            for column, pair in pair_columns.items():
                if column >= len(row):
                    continue
                value_lines = (
                    _cell_lines(cell_grid[row_index][column])
                    if column < len(cell_grid[row_index])
                    else []
                )
                if not value_lines:
                    continue
                fields = summary_fields.setdefault(pair["paar_id"], {})
                labels = label_lines or [label]
                cell = cell_grid[row_index][column]
                place_lines = (
                    [clean(line) for line in cell.get_text("\n").split("\n")]
                    if labels == ["Platz von", "Platz bis"] and isinstance(cell, Tag)
                    else []
                )
                if len(place_lines) == 2:
                    fields.update(
                        {
                            field_label: value
                            for field_label, value in zip(labels, place_lines)
                            if value
                        }
                    )
                elif len(labels) == len(value_lines):
                    fields.update(
                        {
                            clean(field_label): value
                            for field_label, value in zip(labels, value_lines)
                            if clean(field_label) and value
                        }
                    )
                else:
                    fields[label] = " / ".join(value_lines)

    selected_pairs = [
        pair
        for pair in pairs_by_id.values()
        if include_all or (query and name_matches(query, pair["name"]))
    ]
    selected_ids = {pair["paar_id"] for pair in selected_pairs}
    couples = [
        {
            "startnr": pair["startnr"],
            "name": pair["name"],
            "verein": "",
        }
        for pair in selected_pairs
    ]
    results = [result for result in round_results if result["paar_id"] in selected_ids]
    for pair_id, fields in summary_fields.items():
        if pair_id not in selected_ids or not fields:
            continue
        pair = pairs_by_id[pair_id]
        results.append(
            {
                "runde": "Gesamtwertung",
                "paar": pair["name"],
                "paar_id": pair_id,
                "startnr": pair["startnr"],
                "feldgroesse": None,
                "richteranzahl": 0,
                "kreuze_anzahl": 0,
                "kreuze": {},
                "platzierung_spalten": {},
                "alle_weiteren_spalten": fields,
                "richter_wertungen": [],
            }
        )
    return couples, results


def labels_for_section(labels, section):
    if not section:
        return labels
    updated = []
    for label in labels:
        parts = label.split(" | ")
        if len(parts) >= 3 and parts[0].lower() == "wertungsrichter":
            parts[-1] = section
            updated.append(" | ".join(parts))
        else:
            updated.append(label)
    return updated


def is_cross_value(value):
    value = clean(value)
    return value in CROSS_VALUES or bool(
        re.search(r"(?<![A-Za-z])x(?![A-Za-z])", value, re.IGNORECASE)
    )


def row_start_number(row, labels, couple_index, name):
    for index, label in enumerate(labels):
        if (
            index < len(row)
            and re.search(r"\b(?:start)?nr\.?\b", label, re.IGNORECASE)
            and re.fullmatch(r"\d{1,4}", row[index].strip())
        ):
            return row[index].strip()
    match = re.search(r"\((\d{1,4})\)\s*$", name)
    if match:
        return match.group(1)
    for cell in row[:couple_index]:
        if re.fullmatch(r"\d{1,4}", cell.strip()):
            return cell.strip()
    match = re.match(r"\s*(\d{1,4})\b", name)
    return match.group(1) if match else ""


def parse_judge_label(label, section):
    parts = [part.strip() for part in label.split("|")]
    if len(parts) >= 3 and parts[0].lower() == "wertungsrichter":
        judge_part, dance = parts[1], " | ".join(parts[2:])
    elif len(parts) == 2:
        dance, judge_part = parts
    else:
        return None
    match = re.match(r"^([A-Z]{1,2})\s+(.+)$", judge_part)
    if not match:
        return None
    return {
        "kuerzel": match.group(1),
        "name": clean_judge_name(match.group(1), match.group(2)),
        "tanz": section or dance,
    }


def iter_tables_with_round(soup):
    """Liefert (Rundenueberschrift, Tabelle) in Dokumentreihenfolge."""
    current = ""
    leaves = {id(t) for t in leaf_tables(soup)}
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            t = clean(str(node))
            parent = node.parent
            if parent is None:
                continue
            heading_context = parent.name in (
                "th",
                "caption",
                "b",
                "strong",
                "h1",
                "h2",
                "h3",
                "h4",
            )
            if parent.name in ("td", "th"):
                row = parent.find_parent("tr")
                if row:
                    nonempty_cells = [
                        cell
                        for cell in row.find_all(["td", "th"], recursive=False)
                        if clean(cell.get_text(" ", strip=True))
                    ]
                    heading_context = len(nonempty_cells) == 1
            if (
                t
                and len(t) < 90
                and ROUND_RE.search(t)
                and (not node.find_parent("table", recursive=True) or heading_context)
            ):
                current = t
        elif isinstance(node, Tag) and node.name == "table" and id(node) in leaves:
            yield current, node


def parse_page(url, soup, query, debug=False, include_all=False, dance_count=None):
    if Path(urlparse(url).path).name.lower() == "tabges.htm":
        return _parse_tabges_page(soup, query, include_all, dance_count)

    couples, results = {}, []
    for rnd, tbl in iter_tables_with_round(soup):
        grid = table_grid(tbl)
        cell_grid = table_cell_grid(tbl)
        if not grid:
            continue
        header, body = split_header_body(grid)
        if not body:
            continue
        ncols = max(len(r) for r in grid)
        labels = (
            _ergwert_column_labels(header, ncols)
            if Path(urlparse(url).path).name.lower().endswith("ergwert.htm")
            else column_labels(header, ncols)
        )
        section = table_section_heading(header)
        current_round = _round_stage_from_text(rnd) or next(
            (stage for row in header if (stage := _round_heading_from_row(row))),
            "",
        )
        if debug:
            print(
                f"\n[debug] {url} | Runde: {rnd or '?'} | {len(body)} Zeilen\n        Spalten: {labels}"
            )
        parsed_rows = []
        section_pairs = {}
        for body_index, row in enumerate(body):
            ci = next((j for j, c in enumerate(row) if looks_like_couple(c)), None)
            if ci is None:
                row_round = _round_heading_from_row(row)
                if row_round:
                    current_round = row_round
                    continue
                section = table_section_heading([row]) or section
                continue
            row_index = len(header) + body_index
            cell = cell_grid[row_index][ci] if ci < len(cell_grid[row_index]) else ""
            name, club = _pair_cell_details(cell, row[ci])
            if not club:
                club = _row_club(row, labels, ci)
            current_labels = labels_for_section(labels, section)
            startnr = row_start_number(row, current_labels, ci, name)
            name = re.sub(r"\s*\(\d{1,4}\)\s*$", "", name)
            pair_id = f"startnr:{startnr}" if startnr else f"name:{norm(name).strip()}"
            round_code = next(
                (
                    value
                    for index, value in enumerate(row)
                    if index < len(labels)
                    and labels[index].strip().lower() in {"r", "runde"}
                ),
                "",
            )
            row_round = (
                current_round or _round_stage_from_code(round_code) or "(unbekannt)"
            )
            parsed_rows.append(
                (
                    row,
                    row_index,
                    ci,
                    name,
                    club,
                    startnr,
                    section,
                    current_labels,
                    pair_id,
                    row_round,
                    round_code,
                )
            )
            section_pairs.setdefault((row_round, section), set()).add(pair_id)
            current_labels = labels_for_section(labels, section)
            has_place_col = any(
                re.search(r"platz|pl\.", label, re.IGNORECASE) for label in labels
            )
            if has_place_col or any(
                re.search(r"start|nr", label, re.IGNORECASE) for label in labels
            ):
                couple = couples.setdefault(
                    norm(name).strip(),
                    {"startnr": startnr, "name": name, "verein": club},
                )
                if club and not couple["verein"]:
                    couple["verein"] = club
                for index, label in enumerate(current_labels):
                    if label.strip().lower() == "platz" and index < len(row):
                        bounds = place_range(row[index])
                        if bounds:
                            couple["platz_von"], couple["platz_bis"] = bounds
        for (
            row,
            row_index,
            ci,
            name,
            club,
            startnr,
            row_section,
            current_labels,
            pair_id,
            row_round,
            round_code,
        ) in parsed_rows:
            if not (include_all or (query and name_matches(query, name))):
                continue
            kreuze = {
                current_labels[index]: value
                for index, value in enumerate(row)
                if index != ci and is_cross_value(value)
            }
            sonst = {
                current_labels[index]: value
                for index, value in enumerate(row)
                if index != ci
                and value
                and (not is_cross_value(value) or clean(value) not in CROSS_VALUES)
            }
            platz = {
                label: value
                for label, value in sonst.items()
                if re.search(r"platz|pl\.|ergebnis", label, re.IGNORECASE)
            }
            richter_wertungen = []
            for label, value in {**sonst, **kreuze}.items():
                judge = parse_judge_label(label, row_section)
                if judge:
                    richter_wertungen.append(
                        {
                            **judge,
                            "rohwert": value,
                            "kreuz": is_cross_value(value),
                        }
                    )
            expected_judges = {
                judge["kuerzel"]
                for label in current_labels
                if (judge := parse_judge_label(label, row_section))
            }
            expected_dances = {
                judge["tanz"]
                for label in current_labels
                if (judge := parse_judge_label(label, row_section))
            }
            for index, label in enumerate(current_labels):
                judge = parse_judge_label(label, row_section)
                if judge and index < len(cell_grid[row_index]):
                    raw_cell = cell_grid[row_index][index]
                    if not row[index] and isinstance(raw_cell, Tag):
                        richter_wertungen.append(
                            {**judge, "rohwert": "-", "kreuz": False}
                        )
            result = {
                "runde": row_round,
                "paar": name,
                "verein": club,
                "paar_id": pair_id,
                "startnr": startnr,
                "feldgroesse": len(section_pairs[(row_round, row_section)]),
                "richteranzahl": len(expected_judges),
                "tanzanzahl": len(expected_dances),
                "wertungen_vollstaendig": bool(expected_judges and expected_dances)
                and len(richter_wertungen)
                == len(expected_judges) * len(expected_dances),
                "kreuze_anzahl": len(kreuze),
                "kreuze": kreuze,
                "platzierung_spalten": platz,
                "alle_weiteren_spalten": sonst,
                "richter_wertungen": richter_wertungen,
            }
            if round_code:
                result["rundencode"] = round_code
            if row_section:
                result["tanz"] = row_section
            results.append(result)
    return list(couples.values()), results


def process_pages(pages, query="", debug=False, include_all=False):
    output = []
    cities = {
        _page_directory(url): city
        for url, soup in pages.items()
        if (city := page_city(soup))
    }
    counts_by_competition = {}
    for url, soup in pages.items():
        source = Path(urlparse(url).path).name.lower()
        if source == "ergwert.htm":
            count = _dance_count_from_soup(soup)
            counts = {count} if count else set()
        elif source == "erg.htm":
            counts = _result_dance_counts(soup)
        else:
            continue
        if counts:
            counts_by_competition.setdefault(
                competition_key({"url": url}), set()
            ).update(counts)
    dance_counts = {
        key: next(iter(counts))
        for key, counts in counts_by_competition.items()
        if len(counts) == 1
    }
    for url, soup in pages.items():
        if not urlparse(url).path.lower().endswith((".htm", ".html")):
            continue
        judges = extract_judges(soup)
        couples, results = parse_page(
            url,
            soup,
            query,
            debug,
            include_all=include_all,
            dance_count=dance_counts.get(competition_key({"url": url})),
        )
        if judges or couples or results:
            output.append(
                {
                    "schema_version": 3,
                    "parser_version": PARSER_VERSION,
                    "alle_paare_erfasst": include_all,
                    "url": url,
                    "titel": page_title(soup),
                    "stadt": _ancestor_city(url, cities),
                    "wertungsrichter": judges,
                    "paare": couples,
                    "paar_ergebnisse": results,
                }
            )
    return output


# --------------------------------------------------------------------------- main
def write_results(path: Path, results: list[dict]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(results, stream, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "url",
        type=validate_start_url,
        help="Start-URL (index.htm der TopTurnier-Ergebnisse)",
    )
    ap.add_argument("--paar", default="", help="Namensteile des gesuchten Paares")
    ap.add_argument(
        "--alle-paare",
        action="store_true",
        help="Wertungen aller Paare speichern (für normalisierte Vergleiche erforderlich)",
    )
    ap.add_argument("--out", default="ergebnis.json")
    ap.add_argument(
        "--db", help="Ergebnisse zusätzlich dauerhaft in SQLite archivieren"
    )
    ap.add_argument("--csv", help="Kreuze des Paares zusaetzlich als CSV speichern")
    ap.add_argument("--cache", help="Ordner zum Ablegen der HTML-Seiten")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--max-pages", type=int, default=500)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    if a.delay < 0 or a.max_pages < 1:
        ap.error("--delay muss mindestens 0 und --max-pages mindestens 1 sein.")
    errors: list[str] = []
    try:
        pages = crawl(
            a.url,
            a.delay,
            a.max_pages,
            Path(a.cache) if a.cache else None,
            errors=errors,
        )
    except (OSError, ValueError) as error:
        print(f"[error] Abruf fehlgeschlagen: {error}", file=sys.stderr)
        return 1
    print(f"{len(pages)} Seiten geladen")
    if not pages:
        print(
            "[error] Keine HTML-Seiten geladen. Start-URL und Netzwerkzugriff prüfen.",
            file=sys.stderr,
        )
        return 1

    save_all_pairs = a.alle_paare or bool(a.db)
    out = process_pages(pages, a.paar, a.debug, save_all_pairs)
    if not any(page.get("paare") or page.get("paar_ergebnisse") for page in out):
        print(
            "[error] Keine erkennbaren Ergebnisdaten; Ausgaben bleiben unverändert.",
            file=sys.stderr,
        )
        return 1
    try:
        write_results(Path(a.out), out)
    except OSError as error:
        print(f"[error] JSON konnte nicht geschrieben werden: {error}", file=sys.stderr)
        return 1
    if errors:
        print(
            f"[warn] Unvollständiger Import: {len(errors)} Abrufproblem(e).",
            file=sys.stderr,
        )
    print(f"-> {a.out}")
    if a.db:
        try:
            inserted, updated, unchanged = archive_pages(a.db, a.url, out)
        except (OSError, sqlite3.Error, ValueError) as error:
            print(
                f"[error] SQLite-Archiv konnte nicht aktualisiert werden: {error}",
                file=sys.stderr,
            )
            return 1
        print(
            f"-> {a.db} ({inserted} neu, {updated} aktualisiert, "
            f"{unchanged} unverändert)"
        )

    for t in out:
        print(f"\n== {t['titel']}  ({t['url']})")
        if t["wertungsrichter"]:
            print(
                "  Wertungsrichter:",
                "; ".join(f"{j['kuerzel']}={j['name']}" for j in t["wertungsrichter"]),
            )
        if t["paare"]:
            print(f"  {len(t['paare'])} Paare")
        for r in t["paar_ergebnisse"]:
            if a.paar and not name_matches(a.paar, r["paar"]):
                continue
            if not a.paar and save_all_pairs:
                continue
            print(
                f"  [{r['runde']}] {r['paar']}: {r['kreuze_anzahl']} Kreuze, {r['platzierung_spalten']}"
            )

    if a.csv and (a.paar or save_all_pairs):
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["turnier", "runde", "paar", "spalte", "wert"])
            for t in out:
                for r in t["paar_ergebnisse"]:
                    if a.paar and not name_matches(a.paar, r["paar"]):
                        continue
                    for k, v in {**r["kreuze"], **r["alle_weiteren_spalten"]}.items():
                        w.writerow([t["titel"], r["runde"], r["paar"], k, v])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
