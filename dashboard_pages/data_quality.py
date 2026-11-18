"""Datenabdeckung und Qualitätsprobleme des gefilterten Archivs."""

from __future__ import annotations

from collections import defaultdict

import streamlit as st

from etl.common import (
    format_date,
    render_header,
    require_analysis_context,
)
from etl.crawler import PARSER_VERSION
from etl.data import normalize_quality_issue
from etl.domain import PRE_FINAL_STAGES, round_type

context = require_analysis_context()
if context is None:
    st.stop()

events = context["events"]
analysis = context["analysis"]
render_header("Datenqualität", context["subtitle"], events, context["pair_name"])

event_issues = analysis.get("event_quality", [])
round_issues = analysis["quality_issues"]
issues = list(event_issues)
event_by_id = {event["id"]: event for event in events}
parser_unknown = 0
for event in events:
    versions = [
        page.get("parser_version")
        for page in event["pages"]
        if isinstance(page.get("parser_version"), int)
    ]
    if not versions:
        parser_unknown += 1
    elif min(versions) < PARSER_VERSION:
        issues.append(
            {
                "event_id": event["id"],
                "code": "old_parser_version",
                "severity": "veraltet",
                "tournament": event["title"],
                "round": "",
                "note": (f"Parserstand {min(versions)}; aktuell ist {PARSER_VERSION}."),
                "source": ", ".join(page["url"] for page in event["pages"]),
                "action": "Quelldaten bei Bedarf erneut mit dem aktuellen Parser einlesen.",
            }
        )
for issue in round_issues:
    issues.append(normalize_quality_issue(issue))

quality_col, incomplete_col, conflict_col, coverage_col = st.columns(4)
quality_col.metric("Prüfhinweise", len(issues))
incomplete_col.metric(
    "Betroffene Turniere",
    len({issue["event_id"] for issue in issues if issue["event_id"]}),
)
conflict_col.metric(
    "Widersprüchliche Hinweise",
    sum(issue["severity"] == "widersprüchlich" for issue in issues),
)
rounds = [
    round_data
    for event_id in event_by_id
    for round_data in analysis["rounds_by_event"].get(event_id, [])
]
relevant_rounds = [
    item for item in rounds if round_type(item["stage"]) in PRE_FINAL_STAGES
]
known_cutoffs = sum(
    item.get("cross_cutoff") is not None
    and item.get("cross_margin") is not None
    and not item.get("cross_conflict")
    for item in relevant_rounds
)
known_qualifications = sum(
    item.get("qualified") is not None for item in relevant_rounds
)
coverage_col.metric(
    "Qualifikation bekannt",
    f"{known_qualifications} / {len(relevant_rounds)}",
)
if context.get("undated_events"):
    st.warning(
        f"{context['undated_events']} Turnier(e) ohne Datum liegen außerhalb "
        "des gewählten Zeitraums und sind in dieser Auswertung nicht enthalten."
    )

checks = (
    ("Datum", lambda event: event.get("date") is not None),
    ("Ort", lambda event: bool(event.get("city"))),
    ("Endplatzierung", lambda event: event.get("place_range") is not None),
    ("Feldgröße", lambda event: event.get("field_size") is not None),
    (
        "Rundendetails",
        lambda event: bool(analysis["rounds_by_event"].get(event["id"])),
    ),
    (
        "Richterdaten",
        lambda event: (
            event["id"]
            not in {
                issue["event_id"]
                for issue in event_issues
                if issue["code"] == "missing_judge_data"
            }
        ),
    ),
)
st.subheader("Abdeckung nach Datenart")
st.dataframe(
    [
        {
            "Datenart": label,
            "Vorhanden": sum(check(event) for event in events),
            "Gesamt": len(events),
            "Abdeckung": (
                f"{sum(check(event) for event in events) / len(events):.0%}"
                if events
                else "—"
            ),
        }
        for label, check in checks
    ],
    hide_index=True,
    use_container_width=True,
)
st.dataframe(
    [
        {
            "Datenart": "Kreuzgrenzen",
            "Vorhanden": known_cutoffs,
            "Gesamt": len(relevant_rounds),
            "Abdeckung": (
                f"{known_cutoffs / len(relevant_rounds):.0%}"
                if relevant_rounds
                else "—"
            ),
        },
        {
            "Datenart": "Parserstand",
            "Vorhanden": len(events) - parser_unknown,
            "Gesamt": len(events),
            "Abdeckung": (
                f"{(len(events) - parser_unknown) / len(events):.0%}; "
                f"{parser_unknown} unbekannt"
                if events
                else "—"
            ),
        },
    ],
    hide_index=True,
    use_container_width=True,
)
st.caption(
    f"Parserstand der aktuellen Version: {PARSER_VERSION}. "
    "Die Abdeckung bezieht sich auf die angezeigten Turniere. Fehlende "
    "Daten werden nicht als negative Leistung gewertet. Ein unbekannter "
    "Parserstand wird nicht als veraltet eingestuft."
)

if not issues:
    st.success("Für die geprüften Daten wurden keine Hinweise gefunden.")
else:
    by_code: dict[str, set[str]] = defaultdict(set)
    for issue in issues:
        if issue["event_id"]:
            by_code[issue["code"]].add(issue["event_id"])
    st.subheader("Prüfliste")
    st.dataframe(
        [
            {
                "Status": issue["severity"],
                "Turnier": issue["tournament"],
                "Datum": (
                    format_date(event_by_id[issue["event_id"]]["date"])
                    if issue["event_id"] in event_by_id
                    else "—"
                ),
                "Runde": issue["round"] or "—",
                "Hinweis": issue["note"],
                "Nächster Schritt": issue["action"],
                "Quelle": issue["source"] or "nicht gespeichert",
            }
            for issue in issues
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Turnierzahl je Hinweisart: "
        + " · ".join(
            f"{code}: {len(event_ids)}" for code, event_ids in sorted(by_code.items())
        )
    )
st.info(
    "Diese Übersicht löst keine erneuten Importe automatisch aus. "
    "Prüfe die verlinkte Quelle und nutze bei Bedarf den vorhandenen "
    "Erfassungs- oder Importweg."
)
