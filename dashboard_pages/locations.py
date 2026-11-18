"""Ergebnisse nach Turnierort."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from etl.common import (
    format_date,
    format_event_place,
    render_header,
    require_analysis_context,
)
from etl.insights import location_statistics

context = require_analysis_context()
if context is None:
    st.stop()

events = context["events"]
analysis = context["analysis"]
render_header("Turnierorte", context["subtitle"], events, context["pair_name"])

locations = location_statistics(events, analysis["rounds_by_event"])
if not locations:
    st.info("Für den gewählten Zeitraum liegen keine Turnierorte vor.")
    st.stop()

st.caption(
    "Die Auswertung beschreibt eure archivierten Ergebnisse. Sie belegt "
    "keine Ursache-Wirkung-Beziehung zwischen Ort und Leistung."
)
with st.expander("Erklärung der Kennzahlen"):
    st.markdown(
        "- **Turniere / auswertbare Plätze:** alle Starts am Ort und die "
        "Starts mit verwertbarer Endplatzierung.\n"
        "- **Ø normierter Platz:** mittleres Ergebnis relativ zur Feldgröße; "
        "100 % ist der erste, 0 % der letzte Platz. Nur dokumentierte Plätze "
        "gehen ein.\n"
        "- **Spannweite:** niedrigster bis höchster normierter Platz. Sie wird "
        "erst ab zwei auswertbaren Ergebnissen angezeigt.\n"
        "- **Bester Rang / Ø Feldgröße:** absolut bester Rang und mittlere "
        "Größe der dokumentierten Felder.\n"
        "- **Finals / erreichte Runden:** Starts mit belegtem Finale und die "
        "Runden, für die Archivdaten vorliegen.\n"
        "- **Weiterkommen:** bekannte Weiterkommensentscheidungen geteilt "
        "durch alle bekannten Entscheidungen; unbekannte Fälle zählen nicht "
        "als Weiterkommen oder Ausscheiden.\n"
        "- **Zeitraum:** frühestes bis spätestes gespeichertes Turnierdatum."
    )
st.dataframe(
    [
        {
            "Ort": row["Ort"],
            "Turniere": row["Turniere"],
            "Auswertbare Plätze": f"{row['Auswertbare Plätze']} / {row['Turniere']}",
            "Ø normierter Platz": (
                f"{row['Ø normierter Platz']:.0%}"
                if row["Ø normierter Platz"] is not None
                else "—"
            ),
            "Spannweite": (
                f"{row['Spannweite'][0]:.0%}–{row['Spannweite'][1]:.0%}"
                if row["Spannweite"]
                else "—"
            ),
            "Bester Rang": row["Bester Rang"] or "—",
            "Ø Feldgröße": (
                round(row["Ø Feldgröße"], 1) if row["Ø Feldgröße"] is not None else "—"
            ),
            "Finals": row["Finals"],
            "Erreichte Runden": row["Erreichte Runden"],
            "Weiterkommen": (
                f"{row['Weiterkommen'][0]} / {row['Weiterkommen'][1]}"
                if row["Weiterkommen"]
                else "—"
            ),
            "Zeitraum": (
                f"{format_date(row['Von'])} – {format_date(row['Bis'])}"
                if row["Von"] or row["Bis"]
                else "nicht gespeichert"
            ),
        }
        for row in locations
    ],
    hide_index=True,
    use_container_width=True,
)

chart_rows = [
    {
        "Ort": row["Ort"],
        "Mittelwert": row["Ø normierter Platz"],
        "Minimum": row["Spannweite"][0] if row["Spannweite"] else None,
        "Maximum": row["Spannweite"][1] if row["Spannweite"] else None,
        "Turniere": row["Turniere"],
    }
    for row in locations
    if row["Ø normierter Platz"] is not None
]
if chart_rows:
    with st.container(border=True):
        st.subheader("Normierte Ergebnisse nach Ort")
        chart_data = pd.DataFrame(chart_rows)
        range_chart = (
            alt.Chart(chart_data)
            .mark_rule(strokeWidth=5, opacity=0.45)
            .encode(
                x=alt.X(
                    "Minimum:Q",
                    title="Normierter Platz",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format="%"),
                ),
                x2="Maximum:Q",
                y=alt.Y("Ort:N", sort="-x", title=None),
                tooltip=["Ort:N", "Turniere:Q", "Minimum:Q", "Maximum:Q"],
            )
        )
        mean_chart = (
            alt.Chart(chart_data)
            .mark_circle(size=100, color="#ff4b4b")
            .encode(
                x="Mittelwert:Q",
                y=alt.Y("Ort:N", sort="-x", title=None),
                tooltip=[
                    "Ort:N",
                    "Turniere:Q",
                    alt.Tooltip("Mittelwert:Q", format=".1%"),
                ],
            )
        )
        st.altair_chart(
            (range_chart + mean_chart).properties(
                height=max(180, 42 * len(chart_rows))
            ),
            use_container_width=True,
        )
        st.caption(
            "Punkt = Mittelwert, Linie = beobachtete Spannweite; 100 % "
            "entspricht dem ersten Platz."
        )

named_locations = [row for row in locations if row["_key"] is not None]
if len(named_locations) >= 2:
    st.divider()
    st.subheader("Zwei Orte vergleichen")
    left, right = st.columns(2)
    labels = [row["Ort"] for row in named_locations]
    first = left.selectbox("Erster Ort", labels, key="location_compare_first")
    second_options = [label for label in labels if label != first]
    second = right.selectbox(
        "Zweiter Ort", second_options, key="location_compare_second"
    )
    a = next(row for row in named_locations if row["Ort"] == first)
    b = next(row for row in named_locations if row["Ort"] == second)
    st.dataframe(
        [
            {
                "Kennzahl": name,
                first: value_a,
                second: value_b,
            }
            for name, value_a, value_b in (
                ("Turniere", a["Turniere"], b["Turniere"]),
                (
                    "Auswertbare Endplätze",
                    f"{a['Auswertbare Plätze']} / {a['Turniere']}",
                    f"{b['Auswertbare Plätze']} / {b['Turniere']}",
                ),
                (
                    "Ø normierter Platz",
                    f"{a['Ø normierter Platz']:.0%}"
                    if a["Ø normierter Platz"] is not None
                    else "—",
                    f"{b['Ø normierter Platz']:.0%}"
                    if b["Ø normierter Platz"] is not None
                    else "—",
                ),
                (
                    "Ø Feldgröße",
                    round(a["Ø Feldgröße"], 1) if a["Ø Feldgröße"] is not None else "—",
                    round(b["Ø Feldgröße"], 1) if b["Ø Feldgröße"] is not None else "—",
                ),
                ("Finalteilnahmen", a["Finals"], b["Finals"]),
                (
                    "Erreichte Runden",
                    a["Erreichte Runden"],
                    b["Erreichte Runden"],
                ),
                (
                    "Weiterkommen (bekannt)",
                    (
                        f"{a['Weiterkommen'][0]} / {a['Weiterkommen'][1]}"
                        if a["Weiterkommen"]
                        else "—"
                    ),
                    (
                        f"{b['Weiterkommen'][0]} / {b['Weiterkommen'][1]}"
                        if b["Weiterkommen"]
                        else "—"
                    ),
                ),
                (
                    "Startgruppen",
                    ", ".join(sorted({event["group"] for event in a["_events"]})),
                    ", ".join(sorted({event["group"] for event in b["_events"]})),
                ),
            )
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.warning(
        "Unterschiede können auch durch Startgruppe, Disziplin, Feldgröße "
        "und kleine Stichproben entstehen."
    )

with st.expander("Belege: Turniere nach Ort"):
    st.dataframe(
        [
            {
                "Ort": row["Ort"],
                "Datum": format_date(event["date"]),
                "Turnier": event["title"],
                "Startgruppe": event["group"],
                "Disziplin": event["discipline"],
                "Platz / Feld": (
                    f"{format_event_place(event)} / {event['field_size']}"
                    if event.get("field_size")
                    else format_event_place(event)
                ),
                "Normierter Platz": event.get("normalized_place"),
                "Quellen": ", ".join(
                    page["url"]
                    for page in event["pages"]
                    if page["url"].endswith(("ergwert.htm", "tabges.htm"))
                ),
            }
            for row in locations
            for event in row["_events"]
        ],
        hide_index=True,
        use_container_width=True,
    )
