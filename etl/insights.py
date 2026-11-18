"""Reine Zusammenfassungen für die zusätzlichen Dashboard-Auswertungen."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from statistics import median
from typing import Any

from etl.domain import PRE_FINAL_STAGES, RoundStage, round_type

ADVANCEMENT_RULES = {
    "C": {"points": 100, "places": 7, "rank_max": 6},
    "B": {"points": 100, "places": 7, "rank_max": 5},
    "A": {"points": 150, "places": 7, "rank_max": 3},
    "S": {"points": 200, "places": 10, "rank_max": 3},
}
CLASS_ORDER = ("D", "C", "B", "A", "S")
CURRENT_CLASS_RULES = {
    "D": "C",
    "C": "B",
    "B": "A",
    "A": "S",
}


def class_code(group: str) -> str | None:
    match = re.search(r"\b(?:HGR\.?\s*)?([DCBAS])\b", group.upper())
    return match.group(1) if match else None


def _quartile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def placement_statistics(events: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [
        float(event["normalized_place"])
        for event in events
        if event.get("normalized_place") is not None
    ]
    dated = sorted(
        (event for event in events if event.get("date") is not None),
        key=lambda event: event["date"],
        reverse=True,
    )[:3]
    recent_scores = [
        float(event["normalized_place"])
        for event in dated
        if event.get("normalized_place") is not None
    ]
    q1 = _quartile(scores, 0.25)
    q3 = _quartile(scores, 0.75)
    return {
        "starts": len(events),
        "observations": len(scores),
        "median": median(scores) if scores else None,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1 if q1 is not None and q3 is not None else None,
        "best": max(scores) if scores else None,
        "worst": min(scores) if scores else None,
        "recent_starts": len(dated),
        "recent_observations": len(recent_scores),
        "recent_median": median(recent_scores) if recent_scores else None,
        "recent_events": dated,
    }


def numeric_distribution(values: list[float]) -> dict[str, float | int | None]:
    q1 = _quartile(values, 0.25)
    q3 = _quartile(values, 0.75)
    return {
        "observations": len(values),
        "median": median(values) if values else None,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1 if q1 is not None and q3 is not None else None,
    }


def round_statistics(
    events: list[dict[str, Any]],
    rounds_by_event: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    event_stages: dict[str, set[str]] = defaultdict(set)
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    all_rounds: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in events:
        for round_data in rounds_by_event.get(event["id"], []):
            stage = round_type(round_data["stage"])
            stage_name = stage.value if isinstance(stage, RoundStage) else str(stage)
            event_stages[event["id"]].add(stage_name)
            grouped[stage_name].append((event, round_data))
            all_rounds.append((event, round_data))

    funnel = [
        {
            "Runde": stage,
            "Turniere": sum(stage in stages for stages in event_stages.values()),
        }
        for stage in (
            *(item.value for item in PRE_FINAL_STAGES),
            RoundStage.FINAL.value,
        )
        if any(stage in stages for stages in event_stages.values())
    ]
    summary = []
    known_advances = known_eliminations = unknown_qualifications = 0
    final_events: set[str] = set()
    eliminated_events: set[str] = set()
    qualified_for_final: set[str] = set()
    for event, item in all_rounds:
        stage = round_type(item["stage"])
        if stage == RoundStage.FINAL:
            final_events.add(event["id"])
        elif stage in PRE_FINAL_STAGES:
            qualified = item.get("qualified")
            if qualified is True:
                known_advances += 1
                if round_type(item.get("qualified_for", "")) == RoundStage.FINAL:
                    qualified_for_final.add(event["id"])
            elif qualified is False:
                known_eliminations += 1
                eliminated_events.add(event["id"])
            else:
                unknown_qualifications += 1

    for stage_name, observations in grouped.items():
        prefinal = [
            item
            for _, item in observations
            if round_type(item["stage"]) in PRE_FINAL_STAGES
        ]
        advanced = sum(item.get("qualified") is True for item in prefinal)
        eliminated = sum(item.get("qualified") is False for item in prefinal)
        unknown = len(prefinal) - advanced - eliminated
        rates = [
            item["cross_rate"]
            for _, item in observations
            if item.get("cross_rate") is not None
        ]
        with_cutoff = [
            item
            for _, item in observations
            if item.get("cross_cutoff") is not None
            and item.get("cross_margin") is not None
            and not item.get("cross_conflict")
        ]
        summary.append(
            {
                "Runde": stage_name,
                "Teilnahmen": len(observations),
                "Weiter": advanced,
                "Ausgeschieden": eliminated,
                "Unbekannt": unknown,
                "Weiterkommensquote": advanced / (advanced + eliminated)
                if advanced + eliminated
                else None,
                "Kreuzrate": sum(rates) / len(rates) if rates else None,
                "Kreuzrate Beobachtungen": len(rates),
                "Grenzen": len(with_cutoff),
                "Knapp": sum(abs(item["cross_margin"]) <= 2 for item in with_cutoff),
            }
        )
    summary.sort(
        key=lambda row: next(
            (
                index
                for index, stage in enumerate(
                    [item.value for item in PRE_FINAL_STAGES] + [RoundStage.FINAL.value]
                )
                if row["Runde"] == stage
            ),
            len(PRE_FINAL_STAGES) + 1,
        )
    )
    eliminated_events.difference_update(final_events)
    final_known = len(final_events | eliminated_events)
    unknown_final = max(0, len(events) - final_known)
    qualified_without_result = len(
        qualified_for_final - final_events - eliminated_events
    )
    return (
        funnel,
        summary,
        {
            "advances": known_advances,
            "eliminations": known_eliminations,
            "unknown": unknown_qualifications,
            "finals": len(final_events),
            "final_decisions": final_known,
            "final_eliminations": len(eliminated_events),
            "final_unknown": unknown_final,
            "qualified_final_without_result": qualified_without_result,
        },
    )


def location_statistics(
    events: list[dict[str, Any]],
    rounds_by_event: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    locations: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        city = " ".join(str(event.get("city") or "").split())
        key = city.casefold() if city else None
        locations[key].append(event)
    rows = []
    for key, group in locations.items():
        scores = [
            float(event["normalized_place"])
            for event in group
            if event.get("normalized_place") is not None
        ]
        places = [
            float(event["place"]) for event in group if event.get("place") is not None
        ]
        observed_rounds = [
            item for event in group for item in rounds_by_event.get(event["id"], [])
        ]
        finals = sum(
            any(
                round_type(item["stage"]) == RoundStage.FINAL
                for item in rounds_by_event.get(event["id"], [])
            )
            for event in group
        )
        reached_rounds = sorted(
            {str(round_type(item["stage"])) for item in observed_rounds}
        )
        decisions = [
            item
            for item in observed_rounds
            if round_type(item["stage"]) in PRE_FINAL_STAGES
            and item.get("qualified") is not None
        ]
        advanced = sum(item.get("qualified") is True for item in decisions)
        eliminated = sum(item.get("qualified") is False for item in decisions)
        rows.append(
            {
                "Ort": (
                    next(
                        (
                            " ".join(str(event.get("city") or "").split())
                            for event in group
                            if str(event.get("city") or "").strip()
                        ),
                        "Ort unbekannt",
                    )
                ),
                "Turniere": len(group),
                "Auswertbare Plätze": len(scores),
                "Ø normierter Platz": sum(scores) / len(scores) if scores else None,
                "Beste normierte Platzierung": max(scores) if scores else None,
                "Spannweite": (
                    (min(scores), max(scores)) if len(scores) >= 2 else None
                ),
                "Bester Rang": min(places) if places else None,
                "Ø Feldgröße": (
                    sum(
                        event["field_size"]
                        for event in group
                        if event.get("field_size")
                    )
                    / sum(event.get("field_size") is not None for event in group)
                    if any(event.get("field_size") is not None for event in group)
                    else None
                ),
                "Finals": finals,
                "Erreichte Runden": ", ".join(reached_rounds) or "—",
                "Weiterkommen": (
                    (advanced, advanced + eliminated) if advanced + eliminated else None
                ),
                "Von": min(
                    (event["date"] for event in group if event.get("date")),
                    default=None,
                ),
                "Bis": max(
                    (event["date"] for event in group if event.get("date")),
                    default=None,
                ),
                "_key": key,
                "_events": group,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["Turniere"],
            row["_key"] is None,
            row["Ort"].casefold(),
        ),
    )


def advancement_progress(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
    target: str,
    start_group: str,
    discipline: str,
    point_type: str,
) -> dict[str, Any]:
    rule = ADVANCEMENT_RULES[target]
    eligible_events = [
        event
        for event in events
        if event.get("group") == start_group and event.get("discipline") == discipline
    ]
    event_ids = {event["id"] for event in eligible_events}
    points = sum(
        float(record["points"])
        for record in records
        if record.get("event_id") in event_ids and record.get("label") == point_type
    )
    counted = unknown = 0
    for event in eligible_events:
        bounds = event.get("place_range")
        if not bounds:
            unknown += 1
        elif bounds[1] <= rule["rank_max"]:
            counted += 1
        elif bounds[0] <= rule["rank_max"]:
            unknown += 1
    return {
        **rule,
        "points_earned": points,
        "counted_places": counted,
        "unknown_places": unknown,
        "starts": len(eligible_events),
        "events": eligible_events,
        "point_type": point_type,
    }


def progression_ladder(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
    point_type: str,
) -> dict[str, Any]:
    """Accumulate Standard results chronologically, advancing when both limits are met."""
    summaries = {
        current_class: {
            "class": current_class,
            "target": CURRENT_CLASS_RULES.get(current_class),
            "starts": 0,
            "points_earned": None,
            "counted_places": 0,
            "unknown_places": 0,
            "rule": (
                ADVANCEMENT_RULES[CURRENT_CLASS_RULES[current_class]]
                if current_class in CURRENT_CLASS_RULES
                else None
            ),
            "complete": False,
            "transition_date": None,
            "events": [],
        }
        for current_class in CLASS_ORDER
    }
    records_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("label") == point_type:
            records_by_event[record["event_id"]].append(record)

    ordered_events = sorted(
        events,
        key=lambda event: (
            event.get("date") is None,
            event.get("date") or date.max,
            str(event.get("title", "")).casefold(),
            str(event.get("id", "")),
        ),
    )
    current_index = 0
    undated_events = 0
    processed_events = []
    for event in ordered_events:
        if event.get("discipline", "").casefold() != "standard":
            continue
        if event.get("date") is None:
            undated_events += 1
            continue

        current_class = CLASS_ORDER[current_index]
        summary = summaries[current_class]
        rule = summary["rule"]
        event_points = sum(
            float(record["points"]) for record in records_by_event.get(event["id"], [])
        )
        has_points = bool(records_by_event.get(event["id"]))
        summary["starts"] += 1
        if has_points:
            summary["points_earned"] = (summary["points_earned"] or 0) + event_points
        bounds = event.get("place_range")
        if rule:
            if not bounds:
                summary["unknown_places"] += 1
                place_status = "ungeklärt"
            elif bounds[1] <= rule["rank_max"]:
                summary["counted_places"] += 1
                place_status = "ja"
            elif bounds[0] <= rule["rank_max"]:
                summary["unknown_places"] += 1
                place_status = "ungeklärt"
            else:
                place_status = "nein"
        else:
            place_status = "keine Grenze"

        processed = {
            **event,
            "progression_class": current_class,
            "progression_points": event_points if has_points else None,
            "counted_place": place_status,
        }
        summary["events"].append(processed)
        processed_events.append(processed)
        if (
            rule
            and summary["points_earned"] is not None
            and summary["points_earned"] >= rule["points"]
            and summary["counted_places"] >= rule["places"]
        ):
            summary["complete"] = True
            summary["transition_date"] = event["date"]
            current_index = min(current_index + 1, len(CLASS_ORDER) - 1)

    return {
        "classes": summaries,
        "events": processed_events,
        "undated_events": undated_events,
    }
