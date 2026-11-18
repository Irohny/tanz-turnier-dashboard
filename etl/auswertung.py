#!/usr/bin/env python3
"""Stellt die für ein Paar gespeicherten TopTurnier-Ergebnisse lesbar dar."""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import TypedDict
from urllib.parse import urlsplit

from etl.archiv import clean_judge_name, load_pages
from etl.domain import (
    ROUND_BY_CODE,
    ROUND_ORDER,
    PlacementOutcome,
    RoundStage,
    canonical_round,
    compare_places,
    competition_key,
    integer_value,
    normalize,
    normalized_rank,
    pair_identity,
    pair_place,
    qualification_cutoff,
    round_sort_key,
    round_type,
)

EventKey = tuple[str, str]
RoundKey = tuple[EventKey, str]


class _DanceCrossSummary(TypedDict):
    judges: set[str]
    crosses: int


def pair_matches(query: str, pair: dict) -> bool:
    name = pair.get("paar") or pair.get("name") or ""
    if "/" in query:
        return pair_identity(query) == pair_identity(name)
    candidate = normalize(f"{name} {pair.get('startnr', '')}")
    parts = normalize(query).split()
    return bool(parts) and all(part in candidate for part in parts)


def source_name(page: dict) -> str:
    return Path(urlsplit(page.get("url", "")).path).name or "unbekannte Quelle"


def round_name(page: dict, result: dict) -> str:
    raw_round = result.get("runde", "")
    if raw_round and raw_round != "(unbekannt)":
        return canonical_round(raw_round) or raw_round

    fields = result.get("alle_weiteren_spalten", {})
    round_codes = [result.get("rundencode", "")]
    round_codes.extend(
        value for key, value in fields.items() if key.strip().lower() in {"r", "runde"}
    )
    for raw_code in round_codes:
        for code in str(raw_code).strip().upper().split():
            if code in ROUND_BY_CODE:
                return ROUND_BY_CODE[code]

    if any("endrunde" in key.lower() for key in fields):
        return RoundStage.FINAL

    filename = source_name(page).lower()
    if filename == "wert_er.htm":
        return RoundStage.FINAL
    if filename == "starter.htm":
        return "Startliste"
    if filename == "ergwert.htm":
        return "Wertung (Runde nicht angegeben)"
    return "Ergebnis (Runde nicht angegeben)"


def judge_cell(key: str) -> tuple[str, str, str] | None:
    parts = [part.strip() for part in key.split("|")]
    if len(parts) >= 3 and parts[0].lower() == "wertungsrichter":
        judge_part = parts[1]
        dance = " | ".join(parts[2:])
    elif len(parts) == 2:
        dance, judge_part = parts
    else:
        return None

    match = re.match(r"^([A-Z]{1,2})\s+(.+)$", judge_part)
    if not match:
        return None
    code = match.group(1)
    return dance, code, clean_judge_name(code, match.group(2))


def cross_count(value: str) -> int:
    return len(
        re.findall(r"(?<![A-Za-z])x(?![A-Za-z])|[×✗✕+]", str(value), re.IGNORECASE)
    )


def cross_vote(value: str, stage: str) -> int | None:
    # Endrundenzellen können zusätzlich Kreuze früherer Runden enthalten.
    if round_type(stage) is RoundStage.FINAL:
        return None
    crosses = cross_count(value)
    if crosses == 1:
        return 1
    if not crosses and re.fullmatch(r"(?:\d+\s+)?[-–]", value.strip()):
        return 0
    return None


def result_fields(result: dict) -> dict[str, str]:
    fields = dict(result.get("alle_weiteren_spalten", {}))
    fields.update(result.get("platzierung_spalten", {}))
    return {str(key): str(value) for key, value in fields.items()}


def result_judges(
    result: dict, missing_dance_label: str | None = None
) -> list[tuple[str, str, str, str]]:
    fields = result_fields(result)
    crosses = result.get("kreuze", {})
    for key, value in crosses.items():
        fields.setdefault(str(key), str(value))

    judges = []
    for key, value in fields.items():
        parsed = judge_cell(key)
        if parsed:
            dance, code, name = parsed
            dance = result.get("tanz") or missing_dance_label or dance
            judges.append((dance, code, name, value))
    return judges


def scalar_fields(result: dict) -> list[tuple[str, str]]:
    fields = result_fields(result)
    selected = []
    for key, value in fields.items():
        if judge_cell(key):
            continue
        lower = key.lower()
        if (
            lower in {"platz", "summe", "r", "runde", "endrunde"}
            or lower.startswith("ausrechnung")
            or lower.endswith(("| su", "| summe"))
            or ("|" not in key and lower not in {"nr", "club"})
        ):
            selected.append((key, value))
    return selected


def find_rank_page(pages: list[dict]) -> dict | None:
    return next(
        (
            page
            for page in pages
            if source_name(page).lower() == "ergwert.htm" and page.get("paare")
        ),
        None,
    )


def display_pair(pair: dict) -> str:
    name = pair.get("name") or pair.get("paar") or "(unbekanntes Paar)"
    startnr = str(pair.get("startnr", "")).strip()
    if startnr and startnr not in name:
        return f"{startnr} {name}"
    return name


def explicit_place(results: list[tuple[dict, dict]]) -> str | None:
    for page, result in results:
        if source_name(page).lower() != "ergwert.htm":
            continue
        for key, value in result.get("platzierung_spalten", {}).items():
            if "platz" in key.lower():
                return str(value)
        for key, value in result_fields(result).items():
            if key.strip().lower() == "platz":
                return value
    return None


def report_event(event: dict, query: str) -> list[str]:
    pages = event["pages"]
    results = event["results"]
    lines = [f"\nTurnier: {event['title'] or event['folder']}"]

    startnr = next(
        (
            str(pair.get("startnr", "")).strip()
            for page in pages
            for pair in page.get("paare", [])
            if pair_matches(query, pair) and str(pair.get("startnr", "")).strip()
        ),
        "",
    )
    if startnr:
        lines.append(f"Startnummer: {startnr}")

    rank_page = find_rank_page(pages)
    rank_pairs = rank_page.get("paare", []) if rank_page else []
    rank_index = next(
        (index for index, pair in enumerate(rank_pairs) if pair_matches(query, pair)),
        None,
    )
    place = explicit_place(results)
    if place:
        lines.append(f"Platzierung laut Ergebniswertung: {place}")
    if rank_index is not None:
        lines.append(
            f"Rangfolge im Ergebnisblatt: {rank_index + 1} von {len(rank_pairs)}"
        )
        own_place = pair_place(pages, rank_pairs[rank_index])
        for outcome, label in (
            (PlacementOutcome.LOSSES, "Besser platziert"),
            (PlacementOutcome.WINS, "Schlechter platziert"),
            (PlacementOutcome.TIES, "Gleich platziert"),
            (PlacementOutcome.UNKNOWN, "Platzvergleich unbekannt"),
        ):
            matches = [
                pair
                for index, pair in enumerate(rank_pairs)
                if index != rank_index
                and compare_places(own_place, pair_place(pages, pair)) == outcome
            ]
            lines.append(f"{label}:")
            lines.extend(f"  - {display_pair(pair)}" for pair in matches)
            if not matches:
                lines.append("  - niemand")
        lines.append("(Vergleich nur anhand belegter Platzierungen.)")
    elif rank_page:
        lines.append(
            "Rangliste vorhanden, das Paar ließ sich darin nicht eindeutig finden."
        )
    else:
        lines.append(
            "Keine Rangliste in ergwert.htm gespeichert; bessere/schlechtere Paare unbekannt."
        )

    grouped_results: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for page, result in results:
        label = round_name(page, result)
        if label != "Startliste":
            grouped_results[label].append((page, result))

    for label in sorted(grouped_results, key=round_sort_key):
        lines.append(f"\n{label}")
        source_groups: dict[str, list[dict]] = defaultdict(list)
        for page, result in grouped_results[label]:
            source_groups[source_name(page)].append(result)

        for source, source_results in source_groups.items():
            lines.append(f"  Quelle: {source}")
            missing_dance_label = None
            if source.lower() == "wert_er.htm" and any(
                not result.get("tanz") for result in source_results
            ):
                missing_dance_label = "Tanz im JSON nicht gespeichert"
                lines.append(
                    "  Hinweis: Diese JSON-Version enthält die Tanzüberschrift "
                    "der Einzelwertung nicht."
                )
            all_judges = []
            for result in source_results:
                all_judges.extend(result_judges(result, missing_dance_label))

            if all_judges:
                judge_names = sorted({(code, name) for _, code, name, _ in all_judges})
                lines.append(
                    "  Gewertete durch: "
                    + ", ".join(f"{code} {name}" for code, name in judge_names)
                )

            for result in source_results:
                judge_crosses = result.get("richter_kreuze", [])
                if judge_crosses:
                    lines.append(
                        "  Kreuze je Wertungsrichter: "
                        + "; ".join(
                            f"{mark.get('kuerzel', '')} {mark.get('name', '')}: "
                            f"{mark.get('kreuze', 0)}"
                            for mark in judge_crosses
                        )
                    )
                crosses = result.get("kreuze_anzahl")
                votes = result.get("moegliche_kreuzstimmen")
                if crosses is not None and votes:
                    lines.append(
                        f"  Rundenkreuze: {crosses}/{votes} "
                        f"({int(crosses) / int(votes):.0%})"
                    )
                if result.get("qualifiziert") is not None:
                    status = (
                        "weitergekommen"
                        if result["qualifiziert"]
                        else "nicht weitergekommen"
                    )
                    target = result.get("qualifiziert_fuer", "")
                    lines.append(
                        f"  Qualifikation: {status}"
                        + (f" für {target}" if target else "")
                    )
                judges_by_dance: dict[str, list[tuple[str, str, str]]] = defaultdict(
                    list
                )
                for dance, code, name, value in result_judges(
                    result, missing_dance_label
                ):
                    judges_by_dance[dance].append((code, name, value))

                for dance, marks in judges_by_dance.items():
                    crosses = sum(cross_count(value) for _, _, value in marks)
                    cross_text = (
                        f"{crosses} X-Markierungen"
                        if crosses
                        else "keine X-Markierungen"
                    )
                    lines.append(f"  Tanz: {dance} — Kreuze: {cross_text}")
                    lines.append(
                        "    Wertungen: "
                        + "; ".join(
                            f"{code} {name}: {value}" for code, name, value in marks
                        )
                    )

                summaries = scalar_fields(result)
                if summaries:
                    lines.append(
                        "  Ergebnis-/Platzierungsspalten: "
                        + "; ".join(f"{key}: {value}" for key, value in summaries)
                    )
                elif not judges_by_dance and result.get("kreuze_anzahl"):
                    lines.append(f"  Kreuze: {result['kreuze_anzahl']}")

    if not results:
        lines.append(
            "\nFür dieses Paar sind keine Einzelwertungen gespeichert. "
            "Für Richter- und Tanzdaten den Crawler mit --paar erneut ausführen."
        )
    return lines


def numeric_value(value: str) -> float | None:
    if re.match(r"^\s*\d+\.?\s*[-–]\s*\d", str(value)):
        return None
    match = re.match(r"^\s*(-?\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def result_pair_id(result: dict) -> str:
    if result.get("paar_id"):
        return str(result["paar_id"])
    if result.get("startnr"):
        return f"startnr:{result['startnr']}"
    for key, value in result_fields(result).items():
        if key.strip().lower() in {"nr", "startnr", "start-nr"} and re.fullmatch(
            r"\d{1,4}", value.strip()
        ):
            return f"startnr:{value.strip()}"
    match = re.match(r"\s*(\d{1,4})\b", result.get("paar", ""))
    if match:
        return f"startnr:{match.group(1)}"
    return f"name:{normalize(result.get('paar', ''))}"


def _integer_value(value) -> int | None:
    return integer_value(value)


def judge_cross_maximum(result: dict, judge_mark: dict) -> int | None:
    maximum = _integer_value(judge_mark.get("max_kreuze"))
    if maximum is None:
        possible_votes = _integer_value(result.get("moegliche_kreuzstimmen"))
        judge_count = _integer_value(result.get("richteranzahl"))
        if judge_count is None or judge_count <= 0:
            judge_count = len(result.get("richter_kreuze") or [])
        if (
            possible_votes is None
            or possible_votes <= 0
            or judge_count <= 0
            or possible_votes % judge_count
        ):
            return None
        maximum = possible_votes // judge_count
    return maximum


def normalized_judge_cross_rate(result: dict, judge_mark: dict) -> float | None:
    crosses = _integer_value(judge_mark.get("kreuze"))
    maximum = judge_cross_maximum(result, judge_mark)
    if (
        crosses is None
        or maximum is None
        or maximum <= 0
        or not 0 <= crosses <= maximum
    ):
        return None
    return crosses / maximum


def normalized_tendency_lines(data: list[dict], query: str) -> list[str]:
    lines = ["\nRunden-normalisierte Auswertung (1 = bestes Ergebnis, 0 = letztes):"]
    event_titles = {competition_key(page): page.get("titel", "") for page in data}
    rank_field_sizes: dict[tuple[str, str], int] = {}
    for page in data:
        if source_name(page).lower() == "ergwert.htm" and page.get("paare"):
            event_key = competition_key(page)
            rank_field_sizes[event_key] = max(
                rank_field_sizes.get(event_key, 0), len(page["paare"])
            )

    dance_marks: dict[
        tuple[tuple[str, str], str, str], dict[str, tuple[float, int, bool]]
    ] = defaultdict(dict)
    overall_marks: dict[
        tuple[tuple[str, str], str], dict[str, tuple[float, int, bool]]
    ] = defaultdict(dict)
    cross_marks: dict[
        tuple[tuple[str, str], str, str], dict[str, tuple[int, int, bool]]
    ] = defaultdict(dict)
    round_participants: dict[RoundKey, set[str]] = defaultdict(set)
    round_field_sizes: dict[RoundKey, int] = {}
    cross_totals: dict[tuple[tuple[str, str], str], dict[str, tuple[int, bool]]] = (
        defaultdict(dict)
    )
    explicit_qualifiers: dict[tuple[tuple[str, str], str], set[str]] = defaultdict(set)
    stages_with_explicit_qualification: set[tuple[tuple[str, str], str]] = set()
    tabges_cross_rates: list[tuple[tuple[str, str], str, int, int]] = []
    judge_rows: dict[
        tuple[tuple[str, str], str, str],
        dict[str, dict[str, list[tuple[float, int, bool]]]],
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    judge_cross_rows: dict[
        tuple[tuple[str, str], str],
        dict[str, dict[str, list[tuple[float, bool]]]],
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    judge_names: dict[str, str] = {}
    qualification_records: dict[tuple[tuple[str, str], str], dict[str, dict]] = (
        defaultdict(dict)
    )
    complete_rounds: dict[tuple[tuple[str, str], str], bool] = {}

    for page in data:
        event_key = competition_key(page)
        source = source_name(page).lower()
        for result in page.get("paar_ergebnisse", []):
            stage = round_name(page, result)
            pair_id = result_pair_id(result)
            try:
                stored_field_size = int(result.get("feldgroesse", 0))
            except (TypeError, ValueError):
                stored_field_size = 0
            field_size = stored_field_size or rank_field_sizes.get(event_key, 0)
            is_target = pair_matches(query, result)
            fields = result_fields(result)
            round_key = (event_key, stage)
            if source in {"ergwert.htm", "tabges.htm"} and "kreuze_anzahl" in result:
                complete_rounds[round_key] = complete_rounds.get(
                    round_key, True
                ) and bool(page.get("alle_paare_erfasst"))
                if (
                    source == "tabges.htm"
                    or pair_id not in qualification_records[round_key]
                ):
                    qualification_records[round_key][pair_id] = result

            if source == "ergwert.htm":
                round_participants[(event_key, stage)].add(pair_id)
                round_field_sizes[(event_key, stage)] = max(
                    round_field_sizes.get((event_key, stage), 0), field_size
                )
                total_crosses = int(result.get("kreuze_anzahl", 0) or 0)
                cross_totals[(event_key, stage)].setdefault(
                    pair_id, (total_crosses, is_target)
                )
                for key, value in fields.items():
                    if key.strip().lower() != "platz":
                        continue
                    place = numeric_value(value)
                    if place is not None:
                        overall_marks[(event_key, stage)].setdefault(
                            pair_id, (place, field_size, is_target)
                        )
                for key, value in fields.items():
                    if key.rsplit("|", 1)[-1].strip().lower() != "su":
                        continue
                    place = numeric_value(value)
                    if place is None:
                        continue
                    dance = key.rsplit("|", 1)[0].strip()
                    dance_marks[(event_key, stage, dance)].setdefault(
                        pair_id, (place, field_size, is_target)
                    )

                per_dance: dict[str, _DanceCrossSummary] = defaultdict(
                    lambda: {"judges": set(), "crosses": 0}
                )
                for dance, code, name, raw_value in result_judges(result):
                    vote = cross_vote(raw_value, stage)
                    if vote is None:
                        continue
                    entry = per_dance[dance]
                    identity = normalize(clean_judge_name(code, name))
                    entry["judges"].add(identity or f"code:{code.casefold()}")
                    entry["crosses"] += vote
                for dance, entry in per_dance.items():
                    judge_count = _integer_value(result.get("richteranzahl"))
                    if not judge_count or len(entry["judges"]) != judge_count:
                        continue
                    cross_marks[(event_key, stage, dance)].setdefault(
                        pair_id,
                        (
                            int(entry["crosses"]),
                            len(entry["judges"]),
                            is_target,
                        ),
                    )

            if (
                source == "tabges.htm"
                and result.get("runde") != "Gesamtwertung"
                and "moegliche_kreuzstimmen" in result
            ):
                round_key = (event_key, stage)
                round_participants[round_key].add(pair_id)
                round_field_sizes[round_key] = max(
                    round_field_sizes.get(round_key, 0), field_size
                )
                total_crosses = int(result.get("kreuze_anzahl", 0) or 0)
                cross_totals[(event_key, stage)][pair_id] = (
                    total_crosses,
                    is_target,
                )
                if result.get("qualifiziert") is not None:
                    stages_with_explicit_qualification.add(round_key)
                    if result.get("qualifiziert") is True:
                        explicit_qualifiers[round_key].add(pair_id)
                try:
                    possible_votes = int(result.get("moegliche_kreuzstimmen"))
                except (TypeError, ValueError):
                    possible_votes = 0
                if (
                    is_target
                    and possible_votes > 0
                    and 0 <= total_crosses <= possible_votes
                ):
                    tabges_cross_rates.append(
                        (event_key, stage, total_crosses, possible_votes)
                    )

            if source == "tabges.htm" and result.get("runde") != "Gesamtwertung":
                for mark in result.get("richter_kreuze", []):
                    score = normalized_judge_cross_rate(result, mark)
                    if score is None:
                        continue
                    code = str(mark.get("kuerzel", "")).strip()
                    canonical_name = clean_judge_name(code, str(mark.get("name", "")))
                    judge_identity = normalize(canonical_name)
                    if not judge_identity:
                        continue
                    judge_names.setdefault(judge_identity, canonical_name)
                    judge_cross_rows[(event_key, stage)][pair_id][
                        judge_identity
                    ].append((score, is_target))

            if source == "wert_er.htm":
                for dance, code, name, raw_mark in result_judges(result):
                    mark = numeric_value(raw_mark)
                    if mark is not None:
                        canonical_name = clean_judge_name(code, name)
                        judge_identity = normalize(canonical_name)
                        if not judge_identity:
                            continue
                        judge_names.setdefault(judge_identity, canonical_name)
                        judge_rows[(event_key, stage, dance)][pair_id][
                            judge_identity
                        ].append((mark, field_size, is_target))

    target_dance_scores = []
    for (event_key, stage, dance), entries in dance_marks.items():
        target_entries = [
            (pair_id, value) for pair_id, value in entries.items() if value[2]
        ]
        if not target_entries:
            continue
        inferred_size = max((value[1] for value in entries.values()), default=0) or len(
            entries
        )
        for _, (rank, stored_size, _) in target_entries:
            score = normalized_rank(rank, stored_size or inferred_size)
            if score is not None:
                target_dance_scores.append((event_key, stage, dance, score))

    if target_dance_scores:
        lines.append("Tanzplatzierungen nach Feldgröße:")
        for event_key, stage, dance, score in sorted(target_dance_scores):
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}, {dance}: "
                f"{score:.0%} (feldnormalisiert)"
            )
    else:
        lines.append(
            "Keine feldgrößen-normalisierten Tanzplatzierungen. Dafür müssen "
            "Ergebniszeilen mit Su-Feldern und Feldgröße vorliegen."
        )

    normalized_overall = []
    for (event_key, stage), entries in overall_marks.items():
        for rank, stored_size, is_target in entries.values():
            if not is_target:
                continue
            score = normalized_rank(rank, stored_size or len(entries))
            if score is not None:
                normalized_overall.append((event_key, stage, rank, score))
    if normalized_overall:
        lines.append("Gesamtplatzierung nach Feldgröße:")
        for event_key, stage, rank, score in sorted(normalized_overall):
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}: "
                f"Platz {rank:g}, {score:.0%} (feldnormalisiert)"
            )

    target_crosses = []
    for (event_key, stage, dance), entries in cross_marks.items():
        for crosses, judges, is_target in entries.values():
            if is_target and judges:
                target_crosses.append((event_key, stage, dance, crosses, judges))
    if target_crosses:
        lines.append("Kreuzrate je Tanz (Kreuze / erfasste Richterstimmen):")
        for event_key, stage, dance, crosses, judges in sorted(target_crosses):
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}, {dance}: "
                f"{crosses}/{judges} = {crosses / judges:.0%}"
            )
    else:
        lines.append(
            "Keine normalisierte Kreuzrate: Es fehlen Richterzellen oder "
            "eindeutig zuordenbare Tanzspalten."
        )
    if tabges_cross_rates:
        lines.append("Runden-Kreuzrate aus der Gesamttabelle:")
        for event_key, stage, crosses, possible_votes in sorted(tabges_cross_rates):
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}: "
                f"{crosses}/{possible_votes} = "
                f"{crosses / possible_votes:.0%}"
            )

    complete_pair_data = bool(data) and all(
        page.get("alle_paare_erfasst", False)
        for page in data
        if page.get("paar_ergebnisse")
    )
    cutoff_lines = []
    if complete_pair_data:
        stages_by_event: dict[tuple[str, str], set[str]] = defaultdict(set)
        for event_key, stage in round_participants:
            if round_type(stage) in ROUND_ORDER:
                stages_by_event[event_key].add(stage)
        for event_key, stages in stages_by_event.items():
            ordered = sorted(stages, key=round_sort_key)
            for index, current in enumerate(ordered):
                current_pairs = round_participants[(event_key, current)]
                next_pairs = (
                    round_participants[(event_key, ordered[index + 1])]
                    if index + 1 < len(ordered)
                    else set()
                )
                round_key = (event_key, current)
                expected_size = round_field_sizes.get(round_key, 0)
                if expected_size and len(current_pairs) != expected_size:
                    continue
                next_key = (
                    (event_key, ordered[index + 1])
                    if index + 1 < len(ordered)
                    else None
                )
                next_complete = (
                    next_key is not None
                    and complete_rounds.get(next_key, False)
                    and round_field_sizes.get(next_key) == len(next_pairs)
                )
                cutoff = qualification_cutoff(
                    qualification_records[round_key],
                    complete_rounds.get(round_key, False),
                    next_pairs if next_complete else None,
                )
                if cutoff is None:
                    continue
                for pair_id in current_pairs.intersection(
                    cross_totals[(event_key, current)]
                ):
                    crosses, is_target = cross_totals[(event_key, current)][pair_id]
                    if is_target:
                        cutoff_lines.append(
                            (
                                event_key,
                                current,
                                crosses,
                                cutoff,
                                crosses - cutoff,
                                pair_id
                                in (
                                    explicit_qualifiers[round_key]
                                    if round_key in stages_with_explicit_qualification
                                    else next_pairs
                                ),
                            )
                        )
    if cutoff_lines:
        lines.append("Abstand zur beobachteten Weiterkommensgrenze:")
        for event_key, stage, crosses, cutoff, margin, advanced in sorted(cutoff_lines):
            status = "weitergekommen" if advanced else "nicht weitergekommen"
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}: "
                f"{crosses} Kreuze, Grenze {cutoff}, Abstand {margin:+d} "
                f"({status})"
            )
    else:
        lines.append(
            "Keine Weiterkommensgrenze berechnet: Es fehlen vollständige "
            "Paardaten oder eine eindeutig erkennbare Folgerunde."
        )

    judge_deviations: dict[str, list[float]] = defaultdict(list)
    judge_observations: dict[str, int] = defaultdict(int)
    for (event_key, stage, dance), pair_entries in judge_rows.items():
        inferred_size = max(
            (
                size
                for judge_values in pair_entries.values()
                for values in judge_values.values()
                for _, size, _ in values
            ),
            default=0,
        ) or len(pair_entries)
        for pair_id, judge_values in pair_entries.items():
            normalized_by_judge = {}
            target_pair = False
            for judge, values in judge_values.items():
                normalized_values = []
                for rank, size, is_target in values:
                    target_pair = target_pair or is_target
                    score = normalized_rank(rank, size or inferred_size)
                    if score is not None:
                        normalized_values.append(score)
                if normalized_values:
                    normalized_by_judge[judge] = mean(normalized_values)
            if not target_pair or len(normalized_by_judge) < 2:
                continue
            for judge, score in normalized_by_judge.items():
                other_scores = [
                    other_score
                    for other_judge, other_score in normalized_by_judge.items()
                    if other_judge != judge
                ]
                judge_deviations[judge].append(score - median(other_scores))
                judge_observations[judge] += 1

    for pair_entries in judge_cross_rows.values():
        for judge_values in pair_entries.values():
            normalized_by_judge = {}
            target_pair = False
            for judge, observations in judge_values.items():
                normalized_values = []
                for score, is_target in observations:
                    target_pair = target_pair or is_target
                    normalized_values.append(score)
                if normalized_values:
                    normalized_by_judge[judge] = mean(normalized_values)
            if not target_pair or len(normalized_by_judge) < 2:
                continue
            for judge, score in normalized_by_judge.items():
                other_scores = [
                    other_score
                    for other_judge, other_score in normalized_by_judge.items()
                    if other_judge != judge
                ]
                judge_deviations[judge].append(score - median(other_scores))
                judge_observations[judge] += 1

    if judge_deviations:
        lines.append(
            "Richtertendenz relativ zum Median der übrigen Richter "
            "(feldnormalisierte Platzierungen und runden-normalisierte "
            "Kreuzraten; + = günstiger):"
        )
        lines.append(
            "Vor-/Zwischenrunden-Kreuzraten = Kreuze / max_kreuze; "
            "fehlende Nenner werden nicht geschätzt."
        )
        for judge, deviations in sorted(
            judge_deviations.items(), key=lambda item: mean(item[1]), reverse=True
        ):
            lines.append(
                f"  {judge_names[judge]}: "
                f"{mean(deviations) * 100:+.1f} Prozentpunkte "
                f"(n={judge_observations[judge]})"
            )
    else:
        lines.append(
            "Keine normalisierte Richtertendenz: Pro Paar, Runde und Tanz werden "
            "mindestens zwei eindeutig zuordenbare Richterwertungen benötigt."
        )

    opponent_strength = []
    for (event_key, stage, dance), entries in dance_marks.items():
        if round_type(stage) not in ROUND_ORDER:
            continue
        previous_stages = [
            candidate
            for candidate in {key[1] for key in dance_marks if key[0] == event_key}
            if round_sort_key(candidate) < round_sort_key(stage)
            and (event_key, candidate, dance) in dance_marks
        ]
        if not previous_stages:
            continue
        previous_stage = max(previous_stages, key=round_sort_key)
        previous_entries = dance_marks[(event_key, previous_stage, dance)]
        target_ids = {pair_id for pair_id, (_, _, target) in entries.items() if target}
        for target_id in target_ids:
            opponent_scores = [
                normalized_rank(rank, size or len(previous_entries))
                for pair_id, (rank, size, _) in previous_entries.items()
                if pair_id != target_id and pair_id in entries
            ]
            valid_scores = [score for score in opponent_scores if score is not None]
            if valid_scores:
                opponent_strength.append(
                    (
                        event_key,
                        stage,
                        previous_stage,
                        dance,
                        mean(valid_scores),
                        len(valid_scores),
                    )
                )
    if opponent_strength:
        lines.append(
            "Vorleistung der aktuellen Gegner (Mittelwert ihrer "
            "feldnormalisierten Platzierung in der vorherigen Runde):"
        )
        for event_key, stage, previous_stage, dance, score, count in sorted(
            opponent_strength
        ):
            lines.append(
                f"  {event_titles.get(event_key) or event_key[1]} — {stage}, {dance}: "
                f"{score:.0%} aus {previous_stage} (n={count})"
            )
    elif complete_pair_data:
        lines.append(
            "Gegner-Vorleistung nicht bestimmbar: Im JSON fehlen vergleichbare "
            "Ergebnisse der Gegner aus einer vorherigen Runde."
        )
    else:
        lines.append(
            "Gegnerstärke nicht bestimmbar: Für Rundenvergleiche den Crawler mit "
            "--alle-paare erneut ausführen; Vorleistungen der Gegner fehlen."
        )

    lines.append(
        "Hinweis: Die Prozentwerte normalisieren Platzierungen nach Feldgröße. "
        "Die Gegner-Vorleistung ist ein deskriptiver Vergleich, kein Elo- oder "
        "Erwartungswertmodell. Die Weiterkommensgrenze wird nur bei vollständigen "
        "Paardaten aus der Folgerunde abgeleitet."
    )
    return lines


def tendency_lines(data: list[dict], query: str) -> list[str]:
    dance_by_event: dict[
        tuple[tuple[str, str], str], dict[str, list[tuple[float, str]]]
    ] = defaultdict(lambda: defaultdict(list))
    dance_overall: dict[tuple[str, str], list[float]] = defaultdict(list)
    judge_by_event: dict[RoundKey, dict[tuple[str, str], list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    judge_overall: dict[tuple[str, str], list[float]] = defaultdict(list)
    titles: dict[tuple[str, str], str] = {}
    rounds = set()

    for page in data:
        event_key = competition_key(page)
        title = page.get("titel", event_key[1])
        titles[event_key] = title
        for result in page.get("paar_ergebnisse", []):
            if not pair_matches(query, result):
                continue
            stage = round_name(page, result)
            if source_name(page).lower() != "starter.htm":
                rounds.add(stage)
            if source_name(page).lower() == "ergwert.htm":
                for key, value in result_fields(result).items():
                    if key.rsplit("|", 1)[-1].strip().lower() != "su":
                        continue
                    place = numeric_value(value)
                    if place is None:
                        continue
                    dance = key.rsplit("|", 1)[0].strip()
                    dance_by_event[(event_key, stage)][dance].append((place, value))
                    dance_overall[(stage, dance)].append(place)

            if source_name(page).lower() == "wert_er.htm":
                for _, code, name, raw_mark in result_judges(result):
                    mark = numeric_value(raw_mark)
                    if mark is None:
                        continue
                    judge = (code, name)
                    judge_by_event[(event_key, title)][judge].append(mark)
                    judge_overall[judge].append(mark)

    lines = ["\nTendenzen aus den gespeicherten Wertungen:"]
    if dance_by_event:
        lines.append("Tanz-Rohplatzierungen aus den Su-Feldern (kleiner = besser):")
        for (event_key, stage), dances in sorted(
            dance_by_event.items(),
            key=lambda item: (titles.get(item[0][0], ""), item[0][1]),
        ):
            lines.append(f"  {titles.get(event_key, event_key[1])} — {stage}:")
            for dance, observations in sorted(dances.items()):
                average = mean([place for place, _ in observations])
                raw_values = ", ".join(dict.fromkeys(raw for _, raw in observations))
                lines.append(
                    f"    {dance}: Ø Platz {average:.2f} (n={len(observations)}); "
                    f"Su={raw_values}"
                )

        lines.append(
            "Tanzvergleich über alle gespeicherten Klassen (grobe Orientierung):"
        )
        for (stage, dance), places in sorted(
            dance_overall.items(), key=lambda item: (mean(item[1]), item[0][1])
        ):
            lines.append(
                f"  {dance} ({stage}): Ø Platz {mean(places):.2f} (n={len(places)})"
            )
    else:
        lines.append("Keine Tanz-Summen (Su-Felder) für dieses Paar gespeichert.")

    if judge_overall:
        lines.append("Richter-Rohplatznoten (Ø; kleinere Zahl = günstigere Wertung):")
        for judge, marks in sorted(
            judge_overall.items(), key=lambda item: (mean(item[1]), item[0][1])
        ):
            by_event = []
            for (event_key, _), judge_marks in sorted(
                judge_by_event.items(), key=lambda item: titles.get(item[0][0], "")
            ):
                if judge in judge_marks:
                    by_event.append(
                        f"{titles.get(event_key, event_key[1])}: "
                        f"{mean(judge_marks[judge]):.2f} (n={len(judge_marks[judge])})"
                    )
            lines.append(
                f"  {judge[0]} {judge[1]}: Ø {mean(marks):.2f} (n={len(marks)}); "
                + "; ".join(by_event)
            )
    else:
        lines.append("Keine Einzelrichter-Platznoten für dieses Paar gespeichert.")

    if rounds and rounds <= {"Finale/Endrunde"}:
        lines.append(
            "Hinweis: Im JSON sind nur Finale/Endrunde, keine Vor- oder Zwischenrunden."
        )
    lines.append(
        "Rohmittelwerte sind nicht runden-normalisiert und belegen keine Bevorzugung durch Richter."
    )
    lines.extend(normalized_tendency_lines(data, query))
    return lines


def build_report(data: list[dict], query: str) -> str:
    events: dict[tuple[str, str], dict] = {}
    for page in data:
        key = competition_key(page)
        matching_results = [
            result
            for result in page.get("paar_ergebnisse", [])
            if pair_matches(query, result)
        ]
        matching_pairs = [
            pair for pair in page.get("paare", []) if pair_matches(query, pair)
        ]
        if not matching_results and not matching_pairs:
            continue
        event = events.setdefault(
            key,
            {
                "folder": key[1],
                "title": page.get("titel", ""),
                "pages": [],
                "results": [],
            },
        )
        event["pages"].append(page)
        event["results"].extend((page, result) for result in matching_results)

    if not events:
        raise ValueError(
            f"Kein passendes Paar für {query!r} in den gespeicherten Daten gefunden."
        )

    output = [f"Paar-Auswertung: {query}"]
    output.extend(tendency_lines(data, query))
    for event in events.values():
        output.extend(report_event(event, query))
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paar", required=True, help="Name oder Namensteile des Paares"
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--datei",
        default="ergebnis.json",
        help="Crawler-JSON (Standard: ergebnis.json)",
    )
    input_group.add_argument("--db", help="SQLite-Archiv statt JSON-Datei verwenden")
    args = parser.parse_args()

    try:
        if args.db:
            data = load_pages(args.db)
        else:
            data = json.loads(Path(args.datei).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise TypeError("Die JSON-Wurzel muss eine Liste von Turnierseiten sein.")
        if not data:
            raise ValueError("Keine Ergebnisse in der gewählten Quelle gefunden.")
        print(build_report(data, args.paar))
    except (
        OSError,
        sqlite3.Error,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        print(f"[Fehler] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
