"""Paaranalyse und Leistungsübersicht."""

from __future__ import annotations

from typing import Any, cast

import altair as alt
import pandas as pd
import streamlit as st

from etl.common import (
    format_date,
    format_event_place,
    render_header,
    require_analysis_context,
)
from etl.domain import round_sort_key
from etl.insights import placement_statistics, round_statistics


def _timepoint_label(event: dict[str, Any], stage: str | None = None) -> str:
    event_date = event.get("date")
    parts = [
        event_date.strftime("%d.%m.%Y") if event_date else "Datum unbekannt",
        str(event.get("city") or "").strip() or "Ort unbekannt",
    ]
    category = " ".join(
        str(value).strip()
        for value in (event.get("group"), event.get("discipline"))
        if value and value != "Nicht angegeben"
    )
    if category:
        parts.append(category)
    if stage:
        parts.append(stage)
    return " · ".join(parts)


def _chronological_key(row: dict[str, Any]) -> tuple:
    event_date = row.get("date")
    return (
        event_date is None,
        event_date.isoformat() if event_date else "",
        str(row.get("title", "")).casefold(),
        round_sort_key(row.get("stage", "")),
        str(row.get("start_class", "")),
    )


context = require_analysis_context()
if context is None:
    st.stop()

events = context["events"]

render_header("Entwicklung", context["subtitle"], events, context["pair_name"])

scores = [
    event["normalized_place"]
    for event in events
    if event["normalized_place"] is not None
]
stats = placement_statistics(events)
round_funnel, round_rows, round_outcomes = round_statistics(
    events, context["analysis"]["rounds_by_event"]
)
dated_events = sorted(
    (event for event in events if event["date"] is not None),
    key=lambda event: event["date"],
    reverse=True,
)
metric, normalized, latest = st.columns(3)
metric.metric("Turniere im Zeitraum", len(events))
normalized.metric(
    "Ø normierter Platz",
    f"{sum(scores) / len(scores):.0%}" if scores else "—",
    help=f"{len(scores)} von {len(events)} Turnieren auswertbar",
)
latest_events = (
    [event for event in dated_events if event["date"] == dated_events[0]["date"]]
    if dated_events
    else []
)
if len(latest_events) == 1:
    last_event = dated_events[0]
    last_place = format_event_place(last_event)
    if last_event["field_size"]:
        last_place += f" / {last_event['field_size']}"
    latest.metric(
        "Letztes Ergebnis",
        last_place,
    )
    latest.caption(
        f"{format_date(last_event['date'])} · "
        f"{last_event.get('city') or 'Ort unbekannt'}"
    )
elif latest_events:
    latest.metric(
        "Letztes Ergebnis",
        "Mehrere",
        help=f"{len(latest_events)} Turniere am {format_date(latest_events[0]['date'])}",
    )
    latest.caption(f"{len(latest_events)} Turniere am selben Tag")
else:
    latest.metric("Letztes Ergebnis", "—", help="Kein Turnierdatum verfügbar")
st.divider()
median_col, spread_col, range_col, recent_col, finals_col = st.columns(5)
median_col.metric(
    "Median normierter Platz",
    f"{stats['median']:.0%}" if stats["median"] is not None else "—",
    help=f"{stats['observations']} von {stats['starts']} Starts auswertbar",
)
spread_col.metric(
    "Streuung (IQR)",
    f"{stats['iqr']:.0%}" if stats["iqr"] is not None else "—",
    help=(
        f"Mittlere 50 %: {stats['q1']:.0%}–{stats['q3']:.0%}"
        if stats["q1"] is not None and stats["q3"] is not None
        else "Für die Streuung fehlen auswertbare Platzierungen."
    ),
)
range_col.metric(
    "Bester / schwächster Platz",
    (
        f"{stats['best']:.0%} / {stats['worst']:.0%}"
        if stats["best"] is not None and stats["worst"] is not None
        else "—"
    ),
)
recent_col.metric(
    "Letzte 3 Starts",
    (f"{stats['recent_median']:.0%}" if stats["recent_median"] is not None else "—"),
    help=(
        f"{stats['recent_observations']} von {stats['recent_starts']} "
        "datierten Starts mit normiertem Platz"
    ),
)
finals_col.metric(
    "Finals / bekannte Abschlüsse",
    (
        f"{round_outcomes['finals']} / {round_outcomes['final_decisions']}"
        if round_outcomes["final_decisions"]
        else "—"
    ),
    help=(
        f"{round_outcomes['final_eliminations']} bekannte Ausscheiden vor "
        f"dem Finale; {round_outcomes['final_unknown']} Starts ohne "
        "belegten Abschluss"
    ),
)
if round_outcomes["qualified_final_without_result"]:
    finals_col.caption(
        f"{round_outcomes['qualified_final_without_result']} Paar(e) für "
        "das Finale qualifiziert, aber ohne Finalergebnis"
    )
if stats["recent_median"] is not None and stats["median"] is not None:
    recent_col.metric(
        "Form vs. Gesamtmedian",
        f"{stats['recent_median']:.0%}",
        delta=f"{(stats['recent_median'] - stats['median']):+.0%}",
    )
if stats["recent_starts"] < 3 or stats["recent_observations"] < stats["recent_starts"]:
    st.caption(
        "Der Formvergleich nutzt ausschließlich die letzten drei datierten "
        "Starts; fehlende Platzierungen werden nicht durch ältere Starts ersetzt."
    )
st.caption(f"Ø normierter Platz: {len(scores)} von {len(events)} Turnieren auswertbar.")
trend_column, recent_column = st.columns([1.5, 1])
with trend_column.container(border=True):
    st.subheader("Leistung über Zeit")
    chart_rows = [
        {
            "Zeitpunkt": _timepoint_label(event),
            "Turnier": event["title"],
            "date": event["date"],
            "Perzentil": round(event["normalized_place"] * 100, 1),
            "Q1": round(stats["q1"] * 100, 1) if stats["q1"] is not None else None,
            "Q3": round(stats["q3"] * 100, 1) if stats["q3"] is not None else None,
        }
        for event in events
        if event["normalized_place"] is not None
    ]
    if chart_rows:
        chart_rows.sort(key=_chronological_key)
        for index, row in enumerate(chart_rows):
            row["Reihenfolge"] = index
        trend_data = pd.DataFrame(chart_rows)
        trend_line = (
            alt.Chart(trend_data)
            .encode(
                x=alt.X(
                    "Zeitpunkt:N",
                    title="Datum · Ort",
                    sort=[str(row["Zeitpunkt"]) for row in chart_rows],
                    axis=alt.Axis(labelAngle=-45),
                ),
                y=alt.Y(
                    "Perzentil:Q",
                    title="Normiertes Platzierungs-Perzentil (%)",
                    scale=alt.Scale(domain=[0, 100]),
                ),
                order=alt.Order("Reihenfolge:Q", sort="ascending"),
                tooltip=[
                    alt.Tooltip("Zeitpunkt:N", title="Datum · Ort"),
                    alt.Tooltip("Turnier:N", title="Turnier"),
                    alt.Tooltip("Perzentil:Q", title="Perzentil (%)", format=".1f"),
                ],
            )
            .mark_line(point=True)
        )
        trend_chart = cast(
            alt.Chart,
            (
                alt.layer(
                    alt.Chart(trend_data)
                    .mark_area(opacity=0.15, color="#3977b8")
                    .encode(
                        x=alt.X(
                            "Zeitpunkt:N",
                            title="Datum · Ort",
                            sort=[str(row["Zeitpunkt"]) for row in chart_rows],
                            axis=alt.Axis(labelAngle=-45),
                        ),
                        y=alt.Y(
                            "Q1:Q",
                            title="Normiertes Platzierungs-Perzentil (%)",
                            scale=alt.Scale(domain=[0, 100]),
                        ),
                        y2="Q3:Q",
                    ),
                    trend_line,
                ).properties(height=330)
            ),
        )
        st.altair_chart(trend_chart, key="tournament_performance_chart")
        st.caption(
            f"Feldgrößen-normalisierte Platzierungen bei {len(chart_rows)} "
            f"von {len(events)} Turnieren. 100% = erster, 0% = letzter Platz."
        )
        st.caption(
            "Das schattierte Band zeigt den mittleren 50%-Bereich (Q1–Q3) "
            "des ausgewählten Zeitraums."
        )
        with st.expander("Belege: Gesamtplatzierungen"):
            st.dataframe(
                [
                    {
                        "Turnier": event["title"],
                        "Datum": format_date(event["date"]),
                        "Platz": format_event_place(event),
                        "Feldgröße": event["field_size"],
                        "Normierter Platz": event["normalized_place"],
                        "Abweichung vom Median (pp)": (
                            round(
                                (event["normalized_place"] - stats["median"]) * 100,
                                1,
                            )
                            if event["normalized_place"] is not None
                            and stats["median"] is not None
                            else None
                        ),
                        "Quellen": ", ".join(
                            page["url"]
                            for page in event["pages"]
                            if page["url"].endswith(("ergwert.htm", "tabges.htm"))
                        ),
                    }
                    for event in events
                ],
                hide_index=True,
            )
    else:
        st.info(
            "Für den gewählten Zeitraum liegen keine vergleichbaren "
            "Platzierungen mit Feldgröße vor."
        )
with recent_column.container(border=True):
    st.subheader("Zuletzt getanzt")
    if dated_events:
        st.dataframe(
            [
                {
                    "Turnier": event["title"],
                    "Datum": format_date(event["date"]),
                    "Ort": event.get("city") or "—",
                    "Platz / Feld": (
                        f"{format_event_place(event)} / {event['field_size']}"
                        if event["field_size"]
                        else format_event_place(event)
                    ),
                }
                for event in dated_events[:3]
            ],
            hide_index=True,
            width="stretch",
        )
        st.page_link(
            "dashboard_pages/tournament_archive.py",
            label="Alle Turniere ansehen",
        )
    else:
        st.info("Für die ausgewählten Turniere sind keine Daten gespeichert.")
st.divider()
st.subheader("Rundenverlauf")
if round_funnel:
    st.dataframe(round_funnel, hide_index=True, use_container_width=True)
    st.caption(
        "Der Trichter zählt Turniere je tatsächlich belegter Runde. "
        "Direkte Finalstarts und fehlende Zwischenrunden werden nicht ergänzt."
    )
if round_rows:
    st.dataframe(
        [
            {
                **row,
                "Weiterkommensquote": (
                    f"{row['Weiterkommensquote']:.0%}"
                    if row["Weiterkommensquote"] is not None
                    else "—"
                ),
                "Ø Kreuzrate": (
                    f"{row['Kreuzrate']:.0%}" if row["Kreuzrate"] is not None else "—"
                ),
                "Grenzen bekannt": f"{row['Grenzen']} / {row['Teilnahmen']}",
                "Kreuzrate auswertbar": (
                    f"{row['Kreuzrate Beobachtungen']} / {row['Teilnahmen']}"
                ),
            }
            for row in round_rows
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        f"Weiter: {round_outcomes['advances']} · ausgeschieden: "
        f"{round_outcomes['eliminations']} · unbekannt: "
        f"{round_outcomes['unknown']}. Quoten verwenden nur bekannte "
        "Entscheidungen; „knapp“ bedeutet höchstens zwei Kreuze Abstand zu "
        "einer belegten Grenze."
    )
    event_by_id = {event["id"]: event for event in events}
    tight_rows = [
        {
            "Turnier": event_by_id[event_id]["title"],
            "Ort": event_by_id[event_id].get("city") or "—",
            "Runde": item["stage"],
            "Kreuze": item["crosses"],
            "Grenze": item["cross_cutoff"],
            "Abstand": item["cross_margin"],
            "Ergebnis": (
                "weiter"
                if item["qualified"] is True
                else "ausgeschieden"
                if item["qualified"] is False
                else "unbekannt"
            ),
        }
        for event_id, rounds in context["analysis"]["rounds_by_event"].items()
        for item in rounds
        if item.get("cross_margin") is not None
        and abs(item["cross_margin"]) <= 2
        and event_id in event_by_id
    ]
    if tight_rows:
        st.markdown("#### Belegte knappe Entscheidungen (±2 Kreuze)")
        st.dataframe(tight_rows, hide_index=True, use_container_width=True)
if issues := context["analysis"]["quality_issues"]:
    with st.expander(f"Datenqualität: {len(issues)} Hinweis(e)"):
        st.dataframe(issues, hide_index=True)
