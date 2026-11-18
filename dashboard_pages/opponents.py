"""Gegnerbilanz im gemeinsamen Dashboard-Kontext."""

import hashlib
from typing import Any

import streamlit as st

from etl.common import (
    format_date,
    render_header,
    require_analysis_context,
)
from etl.domain import pair_identity


def _selection_key(prefix: str, rows: list[dict[str, Any]]) -> str:
    names = "\0".join(row["name"] for row in rows)
    return f"{prefix}_{hashlib.sha256(names.encode()).hexdigest()[:16]}"


def _place_range_label(bounds: tuple[int, int] | None) -> str:
    if not bounds:
        return "nicht verfügbar"
    first, last = bounds
    return f"{first}." if first == last else f"{first}.–{last}."


context = require_analysis_context()
if context is None:
    st.stop()
events = context["events"]
analysis = context["analysis"]

render_header("Begegnungen", context["subtitle"], events, context["pair_name"])
with st.container(border=True):
    st.subheader("Gemeinsame Turniere")
    opponent_rows = analysis["opponent_rows"]
    if not opponent_rows:
        st.info(
            "Keine Gegnerbilanz verfügbar. Dafür müssen Ranglisten mit "
            "dem Paar und den Vergleichspaaren archiviert sein."
        )
    else:
        opponent_selection = st.dataframe(
            [
                {
                    "Paar": row["name"],
                    "Verein(e)": row["club"] or "—",
                    "Turniere": row["starts"],
                    "Besser": row["wins"],
                    "Schlechter": row["losses"],
                    "Gleich": row["ties"],
                    "Zuletzt": format_date(row["last_seen"]),
                }
                for row in opponent_rows
            ],
            hide_index=True,
            use_container_width=True,
            key=_selection_key("opponent_table_selection", opponent_rows),
            on_select="rerun",
            selection_mode="single-cell",
        )
        if opponent_selection.selection.cells:
            opponent = opponent_rows[opponent_selection.selection.cells[0][0]]
            st.subheader(f"Turniere mit {opponent['name']}")
            st.dataframe(
                [
                    {
                        "Datum": format_date(row["date"]),
                        "Ort": row["city"] or "nicht gespeichert",
                        "Turnier": row["title"],
                        "Euer Platz": _place_range_label(row["own_place"]),
                        "Gegnerplatz": _place_range_label(row["opponent_place"]),
                    }
                    for row in analysis["opponent_evidence"]
                    if pair_identity(row["name"]) == pair_identity(opponent["name"])
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Einen Eintrag anklicken, um gemeinsame Turniere anzuzeigen.")
        st.caption(
            "Vergleich anhand belegter Endplatzierungen. Gleiche Platzbereiche "
            "zählen als Gleichstand."
        )
        with st.expander("Belege: Gegnerbegegnungen"):
            st.dataframe(
                [
                    {
                        "Turnier": row["title"],
                        "Paar": row["name"],
                        "Eigener Platzbereich": str(row["own_place"] or "unbekannt"),
                        "Gegner-Platzbereich": str(
                            row["opponent_place"] or "unbekannt"
                        ),
                        "Bilanz": row["outcome"],
                        "Quellen": ", ".join(row["sources"]),
                    }
                    for row in analysis["opponent_evidence"]
                ],
                hide_index=True,
            )

if issues := context["analysis"]["quality_issues"]:
    with st.expander(f"Datenqualität: {len(issues)} Hinweis(e)"):
        st.dataframe(issues, hide_index=True)
