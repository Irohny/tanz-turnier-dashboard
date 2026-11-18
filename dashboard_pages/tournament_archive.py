"""Turnierübersicht und gespeicherte Rundendetails."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from etl.auswertung import numeric_value
from etl.common import (
    format_date,
    format_event_place,
    format_place,
    render_header,
    require_analysis_context,
)
from etl.domain import integer_value, round_type


def _placement_color(place: float, max_place: float) -> str:
    ratio = min(1.0, max(0.0, (place - 1) / max(1.0, max_place - 1)))
    best = (187, 247, 208)
    worst = (254, 202, 202)
    channels = [
        round(start + (end - start) * ratio)
        for start, end in zip(best, worst, strict=True)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _apply_matrix_styles(_: pd.DataFrame, cell_styles: pd.DataFrame) -> pd.DataFrame:
    return cell_styles


def main() -> None:
    context = require_analysis_context()
    if context is None:
        return

    events = context["events"]
    render_header(
        "Ein Turnier im Detail", context["subtitle"], events, context["pair_name"]
    )

    event_by_id = {
        event["id"]: event
        for event in sorted(
            events,
            key=lambda event: (
                event["date"] is not None,
                event["date"] or date.min,
                event["title"],
            ),
            reverse=True,
        )
    }
    selected_id = st.selectbox(
        "Turnier auswählen",
        list(event_by_id),
        format_func=lambda event_id: (
            f"{event_by_id[event_id]['title']} · "
            f"{format_date(event_by_id[event_id]['date'])} · "
            f"{event_by_id[event_id].get('city') or 'Ort unbekannt'}"
        ),
    )
    selected = event_by_id[selected_id]
    st.markdown(f"#### {selected['title']}")
    st.caption(
        f"{format_date(selected['date'])} · {selected.get('city') or 'Ort unbekannt'} · "
        f"{selected['group']} · "
        f"{selected['discipline']}"
    )
    st.caption(
        f"Platz: {format_event_place(selected)} · "
        f"Feldgröße: {selected['field_size'] or 'nicht verfügbar'}"
    )
    rounds = context["analysis"]["rounds_by_event"].get(selected_id, [])
    if not rounds:
        st.info(
            "Für dieses Turnier sind keine Rundendetails gespeichert. "
            "Erfasse die Detailseiten erneut mit dem Crawler."
        )
        with st.expander("Quellen dieses Turniers"):
            for page in selected["pages"]:
                st.write(page["url"])
        return

    round_rows = []
    for round_data in rounds:
        if round_data["crosses"] is None:
            cross_text = (
                f"nicht verfügbar (bis zu {round_data['votes']} Stimmen)"
                if round_data["votes"] is not None
                else "nicht verfügbar"
            )
        elif round_data["votes"] is None:
            cross_text = f"{round_data['crosses']} (Stimmenzahl nicht verfügbar)"
        else:
            cross_text = f"{round_data['crosses']} / {round_data['votes']}"
        if round_data["cross_totals_derived"]:
            cross_text += " (aus vollständigen Richterkreuzen berechnet)"
        dance_places = ", ".join(
            f"{dance}: {format_place(place)}"
            for dance, place in round_data["dance_places"].items()
        )
        if round_type(round_data["stage"]) == "Finale/Endrunde":
            qualification = "Endrunde bestritten"
        elif round_data["qualified"] is None:
            qualification = "nicht verfügbar"
        elif round_data["qualified"]:
            qualification = "weitergekommen"
            if round_data["qualified_for"]:
                qualification += f" für {round_data['qualified_for']}"
            if round_data["qualification_inferred"]:
                qualification += " (aus späterer Runde abgeleitet)"
        else:
            qualification = "nicht weitergekommen"
        if round_data["stage"] == "Finale/Endrunde":
            cutoff_text = "nicht anwendbar"
        elif round_data["cross_cutoff"] is None:
            cutoff_text = "nicht berechnet"
        elif round_data["cross_margin"] is None:
            cutoff_text = (
                f"Grenze bei {round_data['cross_cutoff']} Kreuzen; "
                "Abstand nicht verfügbar"
            )
        else:
            cutoff_text = (
                f"{round_data['cross_margin']:+d} zur Grenze "
                f"({round_data['cross_cutoff']} Kreuze)"
            )
        if round_data["place"] is None:
            place_text = "nicht verfügbar"
        elif round_data["field_size"] is None:
            place_text = format_place(round_data["place"])
        else:
            place_text = (
                f"{format_place(round_data['place'])} / " f"{round_data['field_size']}"
            )
        round_rows.append(
            {
                "Runde": round_data["stage"],
                "Kreuze / Stimmen": cross_text,
                "Kreuzrate": (
                    f"{round_data['cross_rate']:.1%}"
                    if round_data["cross_rate"] is not None
                    else "nicht verfügbar"
                ),
                "Feldgröße": round_data["field_size"] or "nicht verfügbar",
                "Platz / Feld": place_text,
                "Normierter Platz": (
                    f"{round_data['normalized_place']:.1%}"
                    if round_data["normalized_place"] is not None
                    else "nicht berechenbar"
                ),
                "Qualifikation": qualification,
                "Abstand zur Grenze": cutoff_text,
                "Platz je Tanz": dance_places or "nicht verfügbar",
                "Wertungsrichter": ", ".join(round_data["judges"]) or "nicht verfügbar",
            }
        )
    st.dataframe(
        [
            {
                key: row[key]
                for key in (
                    "Runde",
                    "Kreuze / Stimmen",
                    "Kreuzrate",
                    "Qualifikation",
                    "Abstand zur Grenze",
                    "Platz / Feld",
                )
            }
            for row in round_rows
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Der normierte Platz wird aus Platz und Feldgröße berechnet; abgeleitete "
        "Stimmenzahlen und Qualifikationen sind markiert. Unbekannte Werte werden "
        "nicht geschätzt."
    )
    with st.expander("Weitere Rundendaten"):
        st.dataframe(round_rows, hide_index=True, use_container_width=True)

    cross_tab, marks_tab = st.tabs(
        ["Kreuze je Wertungsrichter", "Einzelwertungen der Richter"]
    )
    with cross_tab:
        aggregated = [
            round_data for round_data in rounds if round_data["judge_crosses"]
        ]
        if aggregated:
            judge_order = list(
                dict.fromkeys(
                    mark["judge"]
                    for round_data in aggregated
                    for mark in round_data["judge_crosses"]
                )
            )
            round_order = [round_data["stage"] for round_data in aggregated]
            matrix = pd.DataFrame(
                "—", index=round_order, columns=judge_order, dtype=object
            )
            styles = pd.DataFrame(
                "", index=round_order, columns=judge_order, dtype=object
            )
            for round_data in aggregated:
                for mark in round_data["judge_crosses"]:
                    crosses = integer_value(mark["crosses"])
                    possible = integer_value(mark["possible"])
                    if crosses is not None:
                        matrix.at[round_data["stage"], mark["judge"]] = str(crosses)
                    if (
                        crosses is not None
                        and possible is not None
                        and possible > 0
                        and 0 <= crosses <= possible
                    ):
                        color = _placement_color(2 - crosses / possible, 2)
                        styles.at[round_data["stage"], mark["judge"]] = (
                            f"background-color: {color}; color: #111827; "
                            "font-weight: bold; text-align: center"
                        )
            matrix.index.name = "Runde"
            matrix.columns.name = "Wertungsrichter"
            st.markdown("##### Aggregierte Richterkreuze")
            st.caption(
                "Grün = höherer, Rot = niedrigerer Anteil an möglichen Kreuzen. "
                "Ohne bekannte mögliche Kreuzzahl bleibt das Feld ungefärbt; "
                "„—“ bedeutet, dass kein Wert gespeichert ist."
            )
            st.dataframe(
                matrix.style.apply(_apply_matrix_styles, axis=None, cell_styles=styles),
                hide_index=False,
                use_container_width=True,
            )
        else:
            st.info(
                "Für dieses Turnier sind keine aggregierten Richter-Kreuzdaten "
                "gespeichert."
            )

    with marks_tab:
        if any(round_data["individual_marks"] for round_data in rounds):
            st.caption(
                "Spalten zeigen Tänze, Zeilen die Wertungsrichter; in den Feldern "
                "steht der vergebene Platz. Grün = besserer, Rot = schlechterer "
                "Platz."
            )
            for round_data in rounds:
                mark_rows = round_data["individual_marks"]
                if not mark_rows:
                    continue
                judge_order = list(dict.fromkeys(mark["judge"] for mark in mark_rows))
                dance_order = list(dict.fromkeys(mark["dance"] for mark in mark_rows))
                matrix = pd.DataFrame(
                    "—", index=judge_order, columns=dance_order, dtype=object
                )
                styles = pd.DataFrame(
                    "", index=judge_order, columns=dance_order, dtype=object
                )
                numeric_places = []
                mark_cells = []
                for mark in mark_rows:
                    raw_mark = str(mark["mark"]).strip()
                    place = numeric_value(raw_mark)
                    shown_mark = (
                        format_place(place) if place is not None else raw_mark or "—"
                    )
                    matrix.at[mark["judge"], mark["dance"]] = shown_mark
                    mark_cells.append((mark["judge"], mark["dance"], place))
                    if place is not None and place >= 1:
                        numeric_places.append(place)

                max_place = max(numeric_places, default=1)
                for judge, dance, place in mark_cells:
                    if place is not None and place >= 1:
                        styles.at[judge, dance] = (
                            f"background-color: {_placement_color(place, max_place)}; "
                            "color: #111827; font-weight: bold; text-align: center"
                        )
                matrix.index.name = "Wertungsrichter"
                matrix.columns.name = "Tanz"
                st.markdown(f"##### {round_data['stage']}")
                st.dataframe(
                    matrix.style.apply(
                        _apply_matrix_styles, axis=None, cell_styles=styles
                    ),
                    hide_index=False,
                    use_container_width=True,
                )
        else:
            st.info("Für dieses Turnier sind keine Einzelwertungen gespeichert.")
    for round_data in rounds:
        for issue in round_data["quality_issues"]:
            st.warning(f"{round_data['stage']}: {issue}")
    with st.expander("Quellen dieses Turniers"):
        for page in selected["pages"]:
            st.write(page["url"])


main()
