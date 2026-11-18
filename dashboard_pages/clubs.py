"""Vereinsübersicht und direkte Paarbegegnungen."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

import streamlit as st

from etl.common import format_date, render_header, require_analysis_context
from etl.domain import normalize, pair_identity


def _selection_key(rows: list[dict[str, Any]]) -> str:
    signature = "\0".join(str(row["name"]) for row in rows)
    return "club_selection_" + hashlib.sha256(signature.encode()).hexdigest()[:16]


def _place_label(bounds: tuple[int, int] | None) -> str:
    if not bounds:
        return "unbekannt"
    first, last = bounds
    return f"{first}." if first == last else f"{first}.–{last}."


context = require_analysis_context()
if context is None:
    st.stop()

events = context["events"]
analysis = context["analysis"]
render_header("Vereine", context["subtitle"], events, context["pair_name"])

event_by_id = {event["id"]: event for event in events}
evidence = [
    row for row in analysis["opponent_evidence"] if row["event_id"] in event_by_id
]
if not evidence:
    st.info(
        "Für den gewählten Zeitraum liegen keine belegten gemeinsamen "
        "Ranglisten-Begegnungen mit anderen Paaren vor."
    )
    st.stop()

by_club: dict[str, list[dict[str, Any]]] = defaultdict(list)
club_names: dict[str, str] = {}
for row in evidence:
    club = " ".join(str(row.get("club") or "").split())
    key = normalize(club) if club else "verein unbekannt"
    club_names.setdefault(key, club or "Verein unbekannt")
    by_club[key].append(row)

club_rows = []
for key, rows in by_club.items():
    club_rows.append(
        {
            "name": club_names[key],
            "_key": key,
            "Paare": len({pair_identity(row["name"]) for row in rows}),
            "Turniere": len({row["event_id"] for row in rows}),
            "Begegnungen": len(rows),
            "Ihr besser": sum(row["outcome"] == "wins" for row in rows),
            "Gegner besser": sum(row["outcome"] == "losses" for row in rows),
            "Gleich": sum(row["outcome"] == "ties" for row in rows),
            "Unbekannt": sum(row["outcome"] == "unknown" for row in rows),
        }
    )
club_rows.sort(key=lambda row: (-row["Begegnungen"], row["name"].casefold()))
st.caption(
    "Nur gemeinsame Turniere derselben ausgewählten Startgruppe und Disziplin "
    "werden angezeigt. Die Vereinsbilanz ist kein allgemeines Vereinsranking."
)
selection = st.dataframe(
    [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in club_rows
    ],
    hide_index=True,
    use_container_width=True,
    key=_selection_key(club_rows),
    on_select="rerun",
    selection_mode="single-cell",
)
selected_club_cells = selection.selection.get("cells", [])
if not selected_club_cells:
    st.caption("Einen Verein anklicken, um die begegneten Paare zu sehen.")
    st.stop()

selected_club = club_rows[selected_club_cells[0][0]]
club_evidence = by_club[selected_club["_key"]]
by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
pair_names: dict[str, str] = {}
for row in club_evidence:
    identity = pair_identity(row["name"])
    by_pair[identity].append(row)
    pair_names.setdefault(identity, row["name"])

pair_rows = []
for identity, rows in by_pair.items():
    pair_rows.append(
        {
            "name": pair_names[identity],
            "_identity": identity,
            "Begegnungen": len(rows),
            "Ihr besser": sum(row["outcome"] == "wins" for row in rows),
            "Gegner besser": sum(row["outcome"] == "losses" for row in rows),
            "Gleich": sum(row["outcome"] == "ties" for row in rows),
            "Unbekannt": sum(row["outcome"] == "unknown" for row in rows),
            "Letzte Begegnung": format_date(
                max(
                    (row["date"] for row in rows if row.get("date")),
                    default=None,
                )
            ),
        }
    )
pair_rows.sort(key=lambda row: (-row["Begegnungen"], row["name"].casefold()))
st.divider()
st.subheader(f"Begegnete Paare von {selected_club['name']}")
pair_selection = st.dataframe(
    [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in pair_rows
    ],
    hide_index=True,
    use_container_width=True,
    key=_selection_key(pair_rows),
    on_select="rerun",
    selection_mode="single-cell",
)
selected_pair_cells = pair_selection.selection.get("cells", [])
if not selected_pair_cells:
    st.caption("Ein Paar anklicken, um die direkten Turnierbegegnungen zu sehen.")
    st.stop()

selected_pair = pair_rows[selected_pair_cells[0][0]]
pair_evidence = sorted(
    by_pair[selected_pair["_identity"]],
    key=lambda row: (
        row.get("date") is None,
        row.get("date"),
        row["title"].casefold(),
    ),
)
st.subheader(f"Begegnungen mit {selected_pair['name']}")
st.dataframe(
    [
        {
            "Datum": format_date(row["date"]),
            "Turnier": row["title"],
            "Ort": row["city"] or "—",
            "Startgruppe": row["group"],
            "Disziplin": row["discipline"],
            "Euer Platz": _place_label(row["own_place"]),
            "Gegnerplatz": _place_label(row["opponent_place"]),
            "Bilanz": {
                "wins": "Ihr besser",
                "losses": "Gegner besser",
                "ties": "Gleichstand",
                "unknown": "Unbekannt",
            }[row["outcome"]],
            "Quelle": ", ".join(row["sources"]),
        }
        for row in pair_evidence
    ],
    hide_index=True,
    use_container_width=True,
)
st.caption(
    f"{len(pair_evidence)} belegte Paarbegegnungen. Überlappende oder "
    "fehlende Platzbereiche bleiben unbekannt; Ortsangaben beeinflussen "
    "die Vereinszuordnung nicht."
)
