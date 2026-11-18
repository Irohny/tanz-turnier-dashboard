"""Gespeicherte Punkte und Platzierungen."""

from collections import defaultdict

import streamlit as st

from etl.common import (
    format_date,
    format_event_place,
    render_header,
    require_analysis_context,
)


def main() -> None:
    context = require_analysis_context()
    if context is None:
        return

    events = context["events"]
    render_header(
        "Punkte & Plätze",
        "Erfasste Quellenwerte · keine Aufstiegsprognose",
        events,
        context["pair_name"],
    )
    st.caption(
        "Gespeicherte Einzelwerte ohne Prüfung einer Aufstiegsberechtigung "
        "und ohne Hochrechnung."
    )
    records = context["analysis"]["point_records"]
    if not records:
        st.info(
            "Im Archiv sind noch keine Aufstiegspunkte gespeichert. "
            "Der Crawler liest paarbezogene Punkte aus tabges.htm, sofern "
            "sie in der Quelle vorliegen. Fehlende Angaben bleiben unbekannt; es werden "
            "keine Werte geschätzt oder aus Platzierungen abgeleitet."
        )
        return

    event_by_id = {event["id"]: event for event in events}
    totals: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    unclassified = 0
    for record in records:
        event = event_by_id[record["event_id"]]
        if "Nicht angegeben" in (event["group"], event["discipline"]):
            unclassified += 1
            continue
        totals[(event["group"], event["discipline"], record["label"])].append(
            record["points"]
        )

    st.subheader("Gespeicherte Punkte")
    st.caption(
        f"{len(records)} Punkteinträge; Summen getrennt nach Startgruppe, "
        "Disziplin und Punktart."
    )
    grouped = sorted(totals.items())
    for start in range(0, len(grouped), 3):
        batch = grouped[start : start + 3]
        for column, ((group, discipline, label), values) in zip(
            st.columns(len(batch)), batch, strict=True
        ):
            column.metric(
                f"{group} · {discipline} · {label}",
                f"{sum(values):g}",
            )
            column.caption(
                f"{len(values)} "
                f"{'gespeicherter Punkteintrag' if len(values) == 1 else 'gespeicherte Punkteinträge'}"
            )
    if unclassified:
        st.caption(
            f"{unclassified} {'Punkteintrag' if unclassified == 1 else 'Punkteinträge'} "
            "ohne eindeutige Startgruppe oder "
            "Disziplin werden nicht zu einer Summe zusammengefasst."
        )
    st.dataframe(
        [
            {
                "Turnier": record["title"],
                "Ort": event_by_id[record["event_id"]].get("city") or "—",
                "Datum": format_date(record["date"]),
                "Startgruppe": event_by_id[record["event_id"]]["group"],
                "Disziplin": event_by_id[record["event_id"]]["discipline"],
                "Platz / Feld": (
                    f"{format_event_place(event_by_id[record['event_id']])} / "
                    f"{event_by_id[record['event_id']]['field_size']}"
                    if event_by_id[record["event_id"]]["field_size"]
                    else format_event_place(event_by_id[record["event_id"]])
                ),
                "Punktart": record["label"],
                "Gespeicherte Punkte": record["points"],
                "Quelle": record["url"],
            }
            for record in records
        ],
        hide_index=True,
        use_container_width=True,
    )


main()
