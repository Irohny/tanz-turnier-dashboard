"""Paaranalyse und Leistungsübersicht."""

from __future__ import annotations

import hashlib
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
from etl.data import judge_meetings
from etl.domain import pair_identity, round_sort_key

_START_CLASS_KEY = "overview_start_class_selection"
_PREVIOUS_START_CLASS_KEY = "overview_previous_start_class_selection"


def _selection_key(prefix: str, rows: list[dict[str, Any]]) -> str:
    names = "\0".join(row["name"] for row in rows)
    return f"{prefix}_{hashlib.sha256(names.encode()).hexdigest()[:16]}"


def _place_range_label(bounds: tuple[int, int] | None) -> str:
    if not bounds:
        return "nicht verfügbar"
    first, last = bounds
    return f"{first}." if first == last else f"{first}.–{last}."


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


def _normalize_start_class_selection() -> None:
    selected = list(st.session_state.get(_START_CLASS_KEY, []))
    previous = st.session_state.get(_PREVIOUS_START_CLASS_KEY, ["Alle"])
    if "Alle" in selected and "Alle" not in previous:
        selected = ["Alle"]
    elif "Alle" in selected:
        selected = [value for value in selected if value != "Alle"]
    if not selected:
        selected = ["Alle"]
    st.session_state[_START_CLASS_KEY] = selected
    st.session_state[_PREVIOUS_START_CLASS_KEY] = selected.copy()


def _render_overview(
    analysis: dict[str, Any], events: list[dict[str, Any]], section: str
) -> None:
    if section == "trend":
        scores = [
            event["normalized_place"]
            for event in events
            if event["normalized_place"] is not None
        ]
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
            [
                event
                for event in dated_events
                if event["date"] == dated_events[0]["date"]
            ]
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
        st.caption(
            f"Ø normierter Platz: {len(scores)} von {len(events)} Turnieren auswertbar."
        )
        trend_column, recent_column = st.columns([1.5, 1])
        with trend_column.container(border=True):
            st.subheader("Leistung über Zeit")
            chart_rows = [
                {
                    "Zeitpunkt": _timepoint_label(event),
                    "Turnier": event["title"],
                    "date": event["date"],
                    "Perzentil": round(event["normalized_place"] * 100, 1),
                }
                for event in events
                if event["normalized_place"] is not None
            ]
            if chart_rows:
                chart_rows.sort(key=_chronological_key)
                for index, row in enumerate(chart_rows):
                    row["Reihenfolge"] = index
                trend_chart = cast(
                    alt.Chart,
                    (
                        alt.Chart(pd.DataFrame(chart_rows))
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
                                alt.Tooltip(
                                    "Perzentil:Q", title="Perzentil (%)", format=".1f"
                                ),
                            ],
                        )
                        .properties(height=330)
                        .mark_line(point=True)
                    ),
                )
                st.altair_chart(trend_chart, key="tournament_performance_chart")
                st.caption(
                    f"Feldgrößen-normalisierte Platzierungen bei {len(chart_rows)} "
                    f"von {len(events)} Turnieren. 100% = erster, 0% = letzter Platz."
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
                                "Quellen": ", ".join(
                                    page["url"]
                                    for page in event["pages"]
                                    if page["url"].endswith(
                                        ("ergwert.htm", "tabges.htm")
                                    )
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

    if section == "dance":
        with st.container(border=True):
            st.subheader("Platzierungen nach Tanz")
            dance_rows = analysis["dance_rows"]
            if not dance_rows:
                st.info(
                    "Keine Tanzplatzierungen aus Su-Feldern gefunden. "
                    "Die Auswertung benötigt gespeicherte Tanz-Summen und Feldgrößen."
                )
            else:
                dance_class_rows = analysis["dance_class_rows"]
                classes = sorted({row["start_class"] for row in dance_class_rows})
                options = ["Alle", *classes]
                selected = st.session_state.get(
                    _START_CLASS_KEY, classes if len(classes) > 1 else ["Alle"]
                )
                selected = [
                    value for value in selected if value == "Alle" or value in classes
                ]
                if not selected:
                    selected = ["Alle"]
                st.session_state[_START_CLASS_KEY] = selected
                previous = st.session_state.get(_PREVIOUS_START_CLASS_KEY)
                if previous is None or any(
                    value != "Alle" and value not in classes for value in previous
                ):
                    st.session_state[_PREVIOUS_START_CLASS_KEY] = selected.copy()

                if len(classes) > 1:
                    selected = st.segmented_control(
                        "Startklasse",
                        options,
                        selection_mode="multi",
                        key=_START_CLASS_KEY,
                        on_change=_normalize_start_class_selection,
                        help=(
                            "„Alle“ fasst alle Startklassen zusammen. Wähle eine oder "
                            "mehrere Klassen, um sie als farbige Balken zu vergleichen."
                        ),
                    )
                else:
                    selected = ["Alle"]
                    if classes:
                        st.caption(f"Startklasse: {classes[0]}")
                show_all_classes_together = not selected or "Alle" in selected
                selected_classes = set(selected or [])
                if show_all_classes_together:
                    chart_rows = [
                        {
                            "Tanz": row["dance"],
                            "Startklasse": "Alle",
                            "Normierte Platzierung": round(
                                row["normalized_place"] * 100, 1
                            ),
                        }
                        for row in dance_rows
                    ]
                    sample_text = ", ".join(
                        f"{row['dance']} n={row['observations']}" for row in dance_rows
                    )
                else:
                    filtered_rows = [
                        row
                        for row in dance_class_rows
                        if row["start_class"] in selected_classes
                    ]
                    chart_rows = [
                        {
                            "Tanz": row["dance"],
                            "Startklasse": row["start_class"],
                            "Normierte Platzierung": round(
                                row["normalized_place"] * 100, 1
                            ),
                        }
                        for row in filtered_rows
                    ]
                    sample_text = "; ".join(
                        f"{dance}: "
                        + ", ".join(
                            f"{row['start_class']} n={row['observations']}"
                            for row in filtered_rows
                            if row["dance"] == dance
                        )
                        for dance in dict.fromkeys(
                            row["dance"] for row in filtered_rows
                        )
                    )
                dance_pick = alt.selection_point(
                    name="dance_pick",
                    fields=["Tanz"],
                    on="click",
                    clear="dblclick",
                    toggle=False,
                )
                dance_chart = cast(
                    alt.Chart,
                    (
                        alt.Chart(pd.DataFrame(chart_rows))
                        .encode(
                            x=alt.X(
                                "Tanz:N",
                                title=None,
                                sort=[str(row["dance"]) for row in dance_rows],
                            ),
                            xOffset=alt.XOffset("Startklasse:N"),
                            y=alt.Y(
                                "Normierte Platzierung:Q",
                                title="Normierte Platzierung (%)",
                                scale=alt.Scale(domain=[0, 100]),
                            ),
                            color=alt.Color(
                                "Startklasse:N",
                                title="Startklasse",
                                scale=alt.Scale(
                                    domain=(
                                        ["Alle"]
                                        if show_all_classes_together
                                        else classes
                                    ),
                                ),
                                legend=(
                                    None
                                    if show_all_classes_together
                                    else alt.Legend(title="Startklasse")
                                ),
                            ),
                            opacity=alt.condition(
                                dance_pick, alt.value(1), alt.value(0.65)
                            ),
                            tooltip=[
                                alt.Tooltip("Tanz:N", title="Tanz"),
                                alt.Tooltip("Startklasse:N", title="Startklasse"),
                                alt.Tooltip(
                                    "Normierte Platzierung:Q",
                                    title="Normierte Platzierung (%)",
                                    format=".1f",
                                ),
                            ],
                        )
                        .add_params(dance_pick)
                        .properties(height=330)
                        .mark_bar()
                    ),
                )
                chart_selection = st.altair_chart(
                    dance_chart,
                    key="dance_placement_chart",
                    on_select="rerun",
                    selection_mode="dance_pick",
                )
                st.caption(
                    "Stichproben: "
                    + sample_text
                    + ". Höher ist besser; Ergebnisse sind nach Feldgröße normalisiert. "
                    "Balken anklicken, um den Zeitverlauf zu sehen; doppelklicken "
                    "hebt die Auswahl auf."
                )
                selected_points = chart_selection.selection.get("dance_pick", [])
                if isinstance(selected_points, dict):
                    selected_points = [selected_points]
                selected_dance = (
                    selected_points[0].get("Tanz") if selected_points else None
                )
                if selected_dance:
                    history_rows = [
                        row
                        for row in analysis["dance_history_rows"]
                        if row["dance"] == selected_dance
                        and (
                            show_all_classes_together
                            or row["start_class"] in selected_classes
                        )
                    ]
                    st.markdown(f"##### Zeitverlauf: {selected_dance}")
                    if not history_rows:
                        st.info(
                            "Für diesen Tanz und die gewählte Startklasse liegen "
                            "keine einzelnen Turnierwertungen vor."
                        )
                    else:
                        history_rows.sort(key=_chronological_key)
                        history_chart_rows = [
                            {
                                "Zeitpunkt": _timepoint_label(row, row["stage"]),
                                "Turnier": row["title"],
                                "date": row["date"],
                                "Runde": row["stage"],
                                "Startklasse": row["start_class"],
                                "Reihenfolge": index,
                                "Normierte Platzierung": round(
                                    row["normalized_place"] * 100, 1
                                ),
                            }
                            for index, row in enumerate(history_rows)
                        ]
                        history_chart = cast(
                            alt.Chart,
                            (
                                alt.Chart(pd.DataFrame(history_chart_rows))
                                .encode(
                                    x=alt.X(
                                        "Zeitpunkt:N",
                                        title="Datum · Ort · Runde",
                                        sort=[
                                            str(row["Zeitpunkt"])
                                            for row in history_chart_rows
                                        ],
                                        axis=alt.Axis(labelAngle=-45),
                                    ),
                                    y=alt.Y(
                                        "Normierte Platzierung:Q",
                                        title="Normierte Platzierung (%)",
                                        scale=alt.Scale(domain=[0, 100]),
                                    ),
                                    color=alt.Color(
                                        "Startklasse:N",
                                        title="Startklasse",
                                        scale=alt.Scale(domain=classes),
                                    ),
                                    order=alt.Order("Reihenfolge:Q", sort="ascending"),
                                    tooltip=[
                                        alt.Tooltip(
                                            "Zeitpunkt:N", title="Datum · Ort · Runde"
                                        ),
                                        alt.Tooltip("Turnier:N", title="Turnier"),
                                        alt.Tooltip("Runde:N", title="Runde"),
                                        alt.Tooltip(
                                            "Startklasse:N", title="Startklasse"
                                        ),
                                        alt.Tooltip(
                                            "Normierte Platzierung:Q",
                                            title="Normierte Platzierung (%)",
                                            format=".1f",
                                        ),
                                    ],
                                )
                                .properties(height=300)
                                .mark_line(point=True)
                            ),
                        )
                        st.altair_chart(
                            history_chart,
                            key="dance_history_chart",
                            width="stretch",
                        )
                        st.caption(
                            f"{len(history_chart_rows)} einzelne Tanzwertungen; "
                            "100% = bester, 0% = letzter Platz."
                        )

                with st.expander("Belege: Tanzplatzierungen"):
                    st.dataframe(
                        [
                            {
                                "Turnier": row["title"],
                                "Datum": format_date(row["date"]),
                                "Tanz": row["dance"],
                                "Klasse": row["start_class"],
                                "Runde": row["stage"],
                                "Platz": row["place"],
                                "Feldgröße": row["field_size"],
                                "Normierter Platz": row["normalized_place"],
                                "Quelle": row["url"],
                            }
                            for row in analysis["dance_history_rows"]
                            if show_all_classes_together
                            or row["start_class"] in selected_classes
                        ],
                        hide_index=True,
                    )

            st.markdown("#### Vor- und Zwischenrunden")
            round_cross_rows = analysis["round_cross_rows"]
            if not round_cross_rows:
                st.info(
                    "Keine verwertbaren Vor- oder Zwischenrunden-Kreuzraten "
                    "mit bekanntem Nenner vorhanden."
                )
            else:
                st.bar_chart(
                    [
                        {
                            "Runde": row["stage"],
                            "Ø Kreuzrate (%)": round(row["cross_rate"] * 100, 1),
                        }
                        for row in round_cross_rows
                    ],
                    x="Runde",
                    y="Ø Kreuzrate (%)",
                    height=300,
                )
                st.caption(
                    "Ø Anteil der erhaltenen Kreuze an allen möglichen Kreuzen je "
                    "Runde. Stichproben je Runde: "
                    + ", ".join(
                        f"{row['stage']} n={row['observations']}"
                        for row in round_cross_rows
                    )
                    + ". Vor-, Zwischen-, Viertel- und Halbfinals sind getrennt "
                    "von den Tanzplatzierungen dargestellt; Runden ohne bekannten "
                    "Nenner bleiben unberücksichtigt."
                )

    if section == "judges":
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
                            ["#94363d", "#285a91"]
                            if dark_theme
                            else ["#f6aaaa", "#a9cdf5"]
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
                    judge_name = judge_rows[judge_selection.selection.cells[0][0]][
                        "name"
                    ]
                    st.subheader(f"Turniere mit {judge_name}")
                    st.dataframe(
                        [
                            {
                                "Datum": format_date(event["date"]),
                                "Ort": event["city"] or "nicht gespeichert",
                                "Turnier": event["title"],
                                "Euer Platz": format_event_place(event),
                            }
                            for event in judge_meetings(events, judge_name)
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption(
                        "Einen Eintrag anklicken, um gemeinsame Turniere anzuzeigen."
                    )
                st.caption(
                    "Finalwertungen werden nach Feldgröße, Vor- und Zwischenrunden "
                    "als Kreuze je Richter / mögliche Kreuze normiert. Angezeigt wird "
                    "die Abweichung vom Median der übrigen Richter in derselben "
                    "Runde und demselben Tanz in Prozentpunkten (pp). Runden ohne "
                    "bekannten Nenner bleiben unberücksichtigt. Rot = negative, "
                    "blau = positive Tendenz; positiv bedeutet relativ günstiger, "
                    "ist aber kein Nachweis einer Bevorzugung."
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

    if section == "opponents":
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
                            "Gemeinsame Turniere": row["starts"],
                            "Öfter geschlagen": row["wins"],
                            "Öfter vor euch": row["losses"],
                            "Gleichstände": row["ties"],
                            "Unbekannt": row["unknown"],
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
                                "Gegnerplatz": _place_range_label(
                                    row["opponent_place"]
                                ),
                            }
                            for row in analysis["opponent_evidence"]
                            if pair_identity(row["name"])
                            == pair_identity(opponent["name"])
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption(
                        "Einen Eintrag anklicken, um gemeinsame Turniere anzuzeigen."
                    )
                st.caption(
                    "Vergleich anhand belegter Endplatzierungen. Gleiche Platzbereiche "
                    "zählen als Gleichstand; fehlende oder überlappende Angaben als unbekannt."
                )
                with st.expander("Belege: Gegnerbegegnungen"):
                    st.dataframe(
                        [
                            {
                                "Turnier": row["title"],
                                "Paar": row["name"],
                                "Eigener Platzbereich": str(
                                    row["own_place"] or "unbekannt"
                                ),
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


def main(section: str = "trend") -> None:
    context = require_analysis_context()
    if context is None:
        return

    events = context["events"]
    titles = {
        "trend": "Eure Entwicklung",
        "dance": "Eure Tänze",
        "judges": "Wertungsrichter",
        "opponents": "Eure Begegnungen",
    }
    render_header(titles[section], context["subtitle"], events, context["pair_name"])
    if context["detail_count"] == 0 and section in {"dance", "judges"}:
        st.warning(
            "Es liegen keine Einzelwertungen vor. Für Tanz- und "
            "Richterauswertungen müssen die Detailseiten erneut gecrawlt "
            "und ins Archiv importiert werden."
        )
    _render_overview(context["analysis"], events, section)
    if issues := context["analysis"]["quality_issues"]:
        with st.expander(f"Datenqualität: {len(issues)} Hinweis(e)"):
            st.dataframe(issues, hide_index=True)


if __name__ == "__main__":
    main()
