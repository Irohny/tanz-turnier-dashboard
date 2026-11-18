"""Tanzanalyse im gemeinsamen Dashboard-Kontext."""

from typing import Any, cast

import altair as alt
import pandas as pd
import streamlit as st

from etl.common import format_date, render_header, require_analysis_context
from etl.domain import round_sort_key
from etl.insights import numeric_distribution

_START_CLASS_KEY = "overview_start_class_selection"
_PREVIOUS_START_CLASS_KEY = "overview_previous_start_class_selection"


def _heatmap_style(value: Any) -> str:
    if pd.isna(value):
        return ""
    ratio = max(0.0, min(1.0, float(value) / 100))
    red = round(239 - 170 * ratio)
    green = round(91 + 106 * ratio)
    blue = round(91 + 37 * ratio)
    return (
        f"background-color: #{red:02x}{green:02x}{blue:02x}; "
        "color: #111827; font-weight: bold"
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
analysis = context["analysis"]

render_header("Tänze", context["subtitle"], events, context["pair_name"])
if context["detail_count"] == 0:
    st.warning(
        "Es liegen keine Einzelwertungen vor. Für Tanz- und "
        "Richterauswertungen müssen die Detailseiten erneut gecrawlt "
        "und ins Archiv importiert werden."
    )

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
        selected = [value for value in selected if value == "Alle" or value in classes]
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
                    "Normierte Platzierung": round(row["normalized_place"] * 100, 1),
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
                    "Normierte Platzierung": round(row["normalized_place"] * 100, 1),
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
                for dance in dict.fromkeys(row["dance"] for row in filtered_rows)
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
                            domain=(["Alle"] if show_all_classes_together else classes),
                        ),
                        legend=(
                            None
                            if show_all_classes_together
                            else alt.Legend(title="Startklasse")
                        ),
                    ),
                    opacity=alt.condition(dance_pick, alt.value(1), alt.value(0.65)),
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
        )
        selected_points = chart_selection.selection.get("dance_pick", [])
        if isinstance(selected_points, dict):
            selected_points = [selected_points]
        selected_dance = selected_points[0].get("Tanz") if selected_points else None
        if selected_dance:
            history_rows = [
                row
                for row in analysis["dance_history_rows"]
                if row["dance"] == selected_dance
                and (
                    show_all_classes_together or row["start_class"] in selected_classes
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
                                    str(row["Zeitpunkt"]) for row in history_chart_rows
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
                                alt.Tooltip("Zeitpunkt:N", title="Datum · Ort · Runde"),
                                alt.Tooltip("Turnier:N", title="Turnier"),
                                alt.Tooltip("Runde:N", title="Runde"),
                                alt.Tooltip("Startklasse:N", title="Startklasse"),
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

        selected_history = [
            row
            for row in analysis["dance_history_rows"]
            if show_all_classes_together or row["start_class"] in selected_classes
        ]
        if selected_history:
            st.markdown("#### Niveau und Streuung je Tanz")
            st.caption(
                "Der normierte Platz setzt jede Wertung ins Verhältnis zur "
                "Feldgröße: 100 % entspricht dem ersten, 0 % dem letzten Platz. "
                "Median zeigt das typische Niveau; das mittlere 50-%-Intervall "
                "umfasst die mittleren Ergebnisse. „Wertungen“ zählt einzelne "
                "Tanz-Runden, „Turniere“ die unterschiedlichen Starts."
            )
            st.caption(
                "Klassen, Disziplinen und Runden bleiben getrennt. Kleine "
                "Stichproben können den Median und das Intervall stark beeinflussen."
            )
            distribution_classes = sorted(
                {row["start_class"] for row in selected_history}
            )
            selected_distribution_class = "Alle"
            if len(distribution_classes) > 1:
                selected_distribution_class = st.segmented_control(
                    "Startklasse für Niveau und Streuung",
                    ["Alle", *distribution_classes],
                    default="Alle",
                    key="dance_distribution_start_class",
                )
            elif distribution_classes:
                st.caption(f"Startklasse: {distribution_classes[0]}")
            distribution_history = [
                row
                for row in selected_history
                if selected_distribution_class in {None, "Alle"}
                or row["start_class"] == selected_distribution_class
            ]
            distributions = []
            by_dance: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
            for row in distribution_history:
                key = (
                    row["dance"],
                    row["start_class"],
                    row["discipline"],
                    row["stage"],
                )
                by_dance.setdefault(key, []).append(row)
            for (dance, start_class, discipline, stage), observations in sorted(
                by_dance.items()
            ):
                distribution = numeric_distribution(
                    [row["normalized_place"] for row in observations]
                )
                distributions.append(
                    {
                        "Tanz": dance,
                        "Startklasse": start_class,
                        "Disziplin": discipline,
                        "Runde": stage,
                        "Wertungen": distribution["observations"],
                        "Turniere": len({row["event_id"] for row in observations}),
                        "Median (%)": (
                            round(distribution["median"] * 100, 1)
                            if distribution["median"] is not None
                            else None
                        ),
                        "Mittlere 50 %": (
                            f"{distribution['q1']:.0%}–{distribution['q3']:.0%}"
                            if distribution["q1"] is not None
                            and distribution["q3"] is not None
                            else "—"
                        ),
                    }
                )
            st.dataframe(distributions, hide_index=True, use_container_width=True)

            stages = sorted({row["stage"] for row in selected_history})
            selected_stage = st.selectbox(
                "Heatmap-Runde",
                stages,
                key="dance_heatmap_stage",
            )
            heat_rows = [
                row for row in selected_history if row["stage"] == selected_stage
            ]
            heatmap = pd.DataFrame(
                [
                    {
                        "Turnier": (f"{row['title']} · {format_date(row['date'])}"),
                        "event_id": row["event_id"],
                        "Tanz": row["dance"],
                        "Platzierung (%)": round(row["normalized_place"] * 100),
                        "Platz / Feld": f"{row['place']:g} / {row['field_size']}",
                        "Quelle": row["url"],
                    }
                    for row in heat_rows
                ]
            )
            pivot = heatmap.pivot_table(
                index=["event_id", "Turnier"],
                columns="Tanz",
                values="Platzierung (%)",
                aggfunc="first",
            )
            pivot_event_ids = list(pivot.index.get_level_values("event_id"))
            pivot.index = pivot.index.get_level_values("Turnier")
            pivot.index.name = "Turnier"
            heat_selection = st.dataframe(
                pivot.style.format("{:.0f}").map(_heatmap_style),
                hide_index=False,
                use_container_width=True,
                key="dance_heatmap",
                on_select="rerun",
                selection_mode="single-cell",
            )
            if heat_selection.selection.cells:
                row_index, column_index = heat_selection.selection.cells[0]
                selected_event_id = pivot_event_ids[row_index]
                selected_tournament = pivot.index[row_index]
                selected_column = column_index
                selected_cell = heatmap[
                    (heatmap["event_id"] == selected_event_id)
                    & (heatmap["Tanz"] == selected_column)
                ]
                if not selected_cell.empty:
                    st.caption(
                        f"{selected_tournament} · {selected_column} · "
                        f"{selected_cell.iloc[0]['Platz / Feld']} · "
                        f"Quelle: {selected_cell.iloc[0]['Quelle']}"
                    )
            st.caption(
                "Leere Zellen bedeuten, dass für diesen Tanz in dieser Runde "
                "keine Wertung vorliegt. Jeder Wert ist der auf ganze Prozent "
                "gerundete, normierte Platz des Paars in diesem Tanz: 100 % "
                "steht für den ersten und 0 % für den letzten Platz. Die Farbe "
                "ordnet die Werte von niedrig (rot) bis hoch (grün) ein."
            )
            st.dataframe(
                [
                    {
                        **row,
                        "Platzierung (%)": f"{row['Platzierung (%)']}%",
                    }
                    for row in heatmap[
                        [
                            "Turnier",
                            "Tanz",
                            "Platzierung (%)",
                            "Platz / Feld",
                            "Quelle",
                        ]
                    ].to_dict("records")
                ],
                hide_index=True,
                use_container_width=True,
            )
            dated_events = sorted(
                {row["date"] for row in selected_history if row["date"] is not None}
            )
            period_rows = []
            if len(dated_events) >= 2:
                midpoint = dated_events[(len(dated_events) - 1) // 2]
                for (
                    dance,
                    start_class,
                    discipline,
                    stage,
                ), observations in by_dance.items():
                    for period, values in (
                        (
                            "Früher",
                            [
                                row
                                for row in observations
                                if row["date"] is not None and row["date"] <= midpoint
                            ],
                        ),
                        (
                            "Später",
                            [
                                row
                                for row in observations
                                if row["date"] is not None and row["date"] > midpoint
                            ],
                        ),
                    ):
                        if not values:
                            continue
                        values.sort(key=lambda row: row["date"])
                        period_rows.append(
                            {
                                "Tanz": dance,
                                "Startklasse": start_class,
                                "Disziplin": discipline,
                                "Runde": stage,
                                "Abschnitt": period,
                                "Zeitraum": (
                                    f"{format_date(values[0]['date'])} – "
                                    f"{format_date(values[-1]['date'])}"
                                ),
                                "Turniere": len({row["event_id"] for row in values}),
                                "Wertungen": len(values),
                                "Ø normierter Platz (%)": round(
                                    sum(row["normalized_place"] for row in values)
                                    / len(values)
                                    * 100,
                                    1,
                                ),
                            }
                        )
            if period_rows:
                st.markdown("#### Zeitliche Abschnitte")
                st.dataframe(period_rows, hide_index=True, use_container_width=True)

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
                f"{row['stage']} n={row['observations']}" for row in round_cross_rows
            )
            + ". Vor-, Zwischen-, Viertel- und Halbfinals sind getrennt "
            "von den Tanzplatzierungen dargestellt; Runden ohne bekannten "
            "Nenner bleiben unberücksichtigt."
        )

if issues := context["analysis"]["quality_issues"]:
    with st.expander(f"Datenqualität: {len(issues)} Hinweis(e)"):
        st.dataframe(issues, hide_index=True)
