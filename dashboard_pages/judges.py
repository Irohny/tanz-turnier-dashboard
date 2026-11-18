"""Richtertendenzen im gemeinsamen Dashboard-Kontext."""

import hashlib
from collections import defaultdict
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from etl.common import (
    format_date,
    format_event_place,
    render_header,
    require_analysis_context,
)
from etl.data import judge_meetings


def _selection_key(prefix: str, rows: list[dict[str, Any]]) -> str:
    names = "\0".join(row["name"] for row in rows)
    return f"{prefix}_{hashlib.sha256(names.encode()).hexdigest()[:16]}"


context = require_analysis_context()
if context is None:
    st.stop()
events = context["events"]
analysis = context["analysis"]

render_header("Wertungsrichter", context["subtitle"], events, context["pair_name"])
if context["detail_count"] == 0:
    st.warning(
        "Es liegen keine Einzelwertungen vor. Für Tanz- und "
        "Richterauswertungen müssen die Detailseiten erneut gecrawlt "
        "und ins Archiv importiert werden."
    )

with st.container(border=True):
    st.subheader("Im Vergleich zum übrigen Panel")
    judge_rows = analysis["judge_rows"]
    if not judge_rows:
        st.info(
            "Keine Richtertendenz berechenbar. Pro Paar, Runde und Tanz "
            "werden mindestens zwei Richterwertungen benötigt."
        )
    else:
        dark_theme = st.context.theme.type == "dark"
        judge_table = pd.DataFrame(
            [
                {
                    "Wertungsrichter": row["name"],
                    "Turniere": row["tournaments"],
                    "Wertungen": row["marks"],
                    "Vergleiche": row["observations"],
                    "Relative Tendenz (Prozentpunkte)": row["deviation_pp"],
                }
                for row in judge_rows
            ]
        )
        styled_judge_table = (
            judge_table.style.bar(
                subset=["Relative Tendenz (Prozentpunkte)"],
                align="zero",
                color=(
                    ["#94363d", "#285a91"] if dark_theme else ["#f6aaaa", "#a9cdf5"]
                ),
                vmin=-100,
                vmax=100,
            )
            .set_properties(
                subset=["Relative Tendenz (Prozentpunkte)"],
                **(
                    {"color": "#e5eee7", "background-color": "#1e3028"}
                    if dark_theme
                    else {"color": "#1d2928", "background-color": "#f5f6f1"}
                ),
            )
            .format({"Relative Tendenz (Prozentpunkte)": "{:+.1f} pp"})
        )
        judge_selection = st.dataframe(
            styled_judge_table,
            hide_index=True,
            use_container_width=True,
            key=_selection_key("judge_table_selection", judge_rows),
            on_select="rerun",
            selection_mode="single-cell",
        )
        if judge_selection.selection.cells:
            judge_name = judge_rows[judge_selection.selection.cells[0][0]]["name"]
            st.subheader(f"Turniere mit {judge_name}")
            event_by_id = {event["id"]: event for event in events}
            st.dataframe(
                [
                    {
                        "Datum": format_date(event["date"]),
                        "Ort": event["city"] or "nicht gespeichert",
                        "Turnier": event["title"],
                        "Platz": format_event_place(event),
                    }
                    for event in judge_meetings(events, judge_name)
                ],
                hide_index=True,
                use_container_width=True,
            )
            evidence = [
                row for row in analysis["judge_evidence"] if row["name"] == judge_name
            ]
            ordered_evidence = sorted(
                evidence,
                key=lambda row: (
                    event_by_id[row["event_id"]].get("date") is None,
                    event_by_id[row["event_id"]].get("date"),
                    row["stage"],
                    row["dance"],
                ),
            )
            if ordered_evidence:
                dated_evidence = [
                    row
                    for row in ordered_evidence
                    if event_by_id[row["event_id"]].get("date")
                ]
                for kind, kind_rows in (
                    (
                        "Tanzplatzierungen",
                        [
                            row
                            for row in dated_evidence
                            if row["dance"] != "Rundenkreuzrate"
                        ],
                    ),
                    (
                        "Rundenkreuzraten",
                        [
                            row
                            for row in dated_evidence
                            if row["dance"] == "Rundenkreuzrate"
                        ],
                    ),
                ):
                    if not kind_rows:
                        continue
                    st.markdown(f"#### {kind} im Zeitverlauf")
                    timeline_rows = [
                        {
                            "Datum": event_by_id[row["event_id"]]["date"],
                            "Turnier": row["title"],
                            "Serie": (
                                f"{row['dance']} · {row['stage']}"
                                if kind == "Tanzplatzierungen"
                                else row["stage"]
                            ),
                            "Abweichung (pp)": row["deviation_pp"],
                        }
                        for row in kind_rows
                    ]
                    timeline = (
                        alt.Chart(pd.DataFrame(timeline_rows))
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("Datum:T", title="Datum"),
                            y=alt.Y(
                                "Abweichung (pp):Q",
                                title="Abweichung zum übrigen Panel (pp)",
                            ),
                            color=alt.Color("Serie:N", title="Tanz · Runde"),
                            detail="Serie:N",
                            tooltip=[
                                "Datum:T",
                                "Turnier:N",
                                "Serie:N",
                                alt.Tooltip("Abweichung (pp):Q", format=".1f"),
                            ],
                        )
                        .properties(height=260)
                    )
                    st.altair_chart(timeline, use_container_width=True)
                if not dated_evidence:
                    st.info("Für diese Vergleiche sind keine Daten gespeichert.")

                grouped_evidence: dict[tuple[str, str, str], list[dict[str, Any]]] = (
                    defaultdict(list)
                )
                for row in evidence:
                    if row["dance"] == "Rundenkreuzrate":
                        grouped_evidence[("Rundenkreuzrate", "—", row["stage"])].append(
                            row
                        )
                    else:
                        grouped_evidence[
                            ("Tanzplatzierung", row["dance"], row["stage"])
                        ].append(row)
                breakdown = []
                for (kind, dance, stage), rows in sorted(grouped_evidence.items()):
                    values = [row["deviation_pp"] for row in rows]
                    breakdown.append(
                        {
                            "Wertung": kind,
                            "Tanz": dance,
                            "Runde": stage,
                            "Vergleiche": len(rows),
                            "Turniere": len({row["event_id"] for row in rows}),
                            "Ø Abweichung (pp)": sum(values) / len(values),
                            "Bereich (pp)": (
                                f"{min(values):+.1f} bis {max(values):+.1f}"
                            ),
                            "Stichprobe": ("klein" if len(rows) < 3 else "ausreichend"),
                        }
                    )
                st.markdown("#### Aufteilung nach Tanz und Runde")
                st.dataframe(breakdown, hide_index=True, use_container_width=True)
                st.dataframe(
                    [
                        {
                            "Datum": format_date(event_by_id[row["event_id"]]["date"]),
                            "Turnier": row["title"],
                            "Startgruppe": event_by_id[row["event_id"]]["group"],
                            "Disziplin": event_by_id[row["event_id"]]["discipline"],
                            "Runde": row["stage"],
                            "Tanz / Wertung": row["dance"],
                            "Abweichung (pp)": row["deviation_pp"],
                            "Quelle": row["url"],
                        }
                        for row in ordered_evidence
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.caption("Einen Eintrag anklicken, um gemeinsame Turniere anzuzeigen.")
        st.caption(
            "Finalwertungen werden nach Feldgröße, Vor- und Zwischenrunden "
            "als Kreuze je Richter / mögliche Kreuze normiert. Angezeigt wird "
            "die Abweichung vom Median der übrigen Richter in derselben "
            "Runde und demselben Tanz in Prozentpunkten (pp)."
        )
        if any(row["observations"] < 5 for row in judge_rows):
            st.warning(
                "Geringe Aussagekraft bei weniger als 5 verwendbaren Vergleichen. "
                "Diese Hinweisgrenze ist keine statistische Signifikanzgrenze."
            )
        with st.expander("Belege: Richtervergleiche"):
            judge_name = st.selectbox(
                "Wertungsrichter für Belege",
                [row["name"] for row in judge_rows],
            )
            selected_judge = next(
                row for row in judge_rows if row["name"] == judge_name
            )
            st.caption(
                f"Erfasste Rohwertungen: {selected_judge['raw_marks']}; "
                f"davon {selected_judge['marks']} für Vergleiche verwendet."
            )
            st.dataframe(
                [
                    {
                        "Turnier": row["title"],
                        "Runde": row["stage"],
                        "Tanz / Wertung": row["dance"],
                        "Normierte Wertung": row["score"],
                        "Median übriges Panel": row["panel_median"],
                        "Abweichung (pp)": row["deviation_pp"],
                        "Quelle": row["url"],
                    }
                    for row in analysis["judge_evidence"]
                    if row["name"] == judge_name
                ],
                hide_index=True,
            )

if issues := context["analysis"]["quality_issues"]:
    with st.expander(f"Datenqualität: {len(issues)} Hinweis(e)"):
        st.dataframe(issues, hide_index=True)
