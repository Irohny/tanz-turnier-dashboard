"""Gespeicherte Punkte und Platzierungen."""

from collections import defaultdict

import streamlit as st

from etl.common import (
    format_date,
    format_event_place,
    render_header,
    require_analysis_context,
)
from etl.insights import (
    CLASS_ORDER,
    CURRENT_CLASS_RULES,
    class_code,
    progression_ladder,
)

context = require_analysis_context()
if context is None:
    st.stop()

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
    st.info("Im Archiv sind noch keine Aufstiegspunkte gespeichert.")

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
grouped = sorted(
    totals.items(),
    key=lambda item: (
        CLASS_ORDER.index(class_code(item[0][0]))
        if class_code(item[0][0]) in CLASS_ORDER
        else len(CLASS_ORDER),
        item[0][0].casefold(),
        item[0][1].casefold(),
        item[0][2].casefold(),
    ),
)
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

st.divider()
st.subheader("Aufstiegsfortschritt")
st.caption(
    "Die Berechnung startet in D und verarbeitet Standard-Turniere chronologisch. "
    "Punkte und Platzierungen zählen unabhängig von der im Turnier gespeicherten "
    "Startklasse; LM- und OT-Ergebnisse werden gemeinsam berücksichtigt. Sobald "
    "Punkte- und Platzierungsgrenze einer Klasse erreicht sind, zählt das nächste "
    "Turnier für die nächste Klasse."
)
progress_events = context["progression_events"]
progress_records = context["progression_analysis"]["point_records"]
standard_event_ids = {
    event["id"]
    for event in progress_events
    if event.get("discipline", "").casefold() == "standard"
}
point_types = list(
    dict.fromkeys(
        record["label"]
        for record in progress_records
        if record["event_id"] in standard_event_ids
    )
)
preferred_point_type = next(
    (label for label in point_types if "aufstiegspunkt" in label.casefold()),
    point_types[0] if point_types else "Keine Punktart verfügbar",
)
point_type = st.selectbox(
    "Punktart für den Klassenvergleich",
    point_types or [preferred_point_type],
    key="advancement_point_type",
    help=(
        "Die Aufstiegs-Punktart wählen. Für diese Punktart werden die Einträge "
        "aus LM und OT zusammengezählt; unterschiedliche Punktarten werden "
        "nicht miteinander addiert."
    ),
)
progression = progression_ladder(progress_events, progress_records, point_type)
class_summaries = progression["classes"]
if progression["undated_events"]:
    st.caption(
        f"{progression['undated_events']} Standard-Turnier(e) ohne Datum "
        "werden nicht in die chronologische Aufstiegsberechnung aufgenommen."
    )
for column, current_class in zip(
    st.columns(len(CLASS_ORDER)), CLASS_ORDER, strict=True
):
    summary = class_summaries[current_class]
    with column.container(border=True):
        target = CURRENT_CLASS_RULES.get(current_class)
        if context["selected_discipline"] not in {"Alle", "Standard"}:
            st.metric(current_class, "nicht anwendbar")
            st.caption("Grenzwerte sind nur für Standard dokumentiert.")
            continue
        points = summary["points_earned"]
        rule = summary["rule"]
        if target and rule:
            st.metric(
                f"{current_class} → {target} · Punkte",
                f"{points:g} / {rule['points']}"
                if points is not None
                else f"— / {rule['points']}",
                help=(
                    f"{summary['starts']} Starts in berechneter Stufe "
                    f"{current_class}; Punktart: {point_type}"
                ),
            )
            st.caption(
                f"Platzierungen {summary['counted_places']} / {rule['places']} "
                f"(Rang 1–{rule['rank_max']}; "
                f"{summary['unknown_places']} ungeklärt)"
            )
            if rule["points"]:
                st.progress(
                    min(1.0, points / rule["points"]) if points is not None else 0.0,
                    text="Punkte",
                )
            st.progress(
                min(1.0, summary["counted_places"] / rule["places"]),
                text="Platzierungen",
            )
            if summary["complete"]:
                st.success(
                    f"Grenzen erreicht am {format_date(summary['transition_date'])}"
                )
        else:
            st.metric(
                "S · gespeicherte Punkte",
                f"{points:g}" if points is not None else "—",
                help=f"{summary['starts']} Starts in berechneter Stufe S; Punktart: {point_type}",
            )
            st.caption("Keine nächste Aufstiegsklasse oder Grenze dokumentiert.")
st.warning(
    "Die Grenzen gelten nur für Standard. Die Ansicht zeigt die nach "
    "Startklasse getrennten Nachweise, stellt aber keinen Aufstiegsstatus "
    "fest: Saisonbezug und Mehrfachstartregeln sind nicht dokumentiert."
)
st.dataframe(
    [
        {
            "Datum": format_date(event["date"]),
            "Turnier": event["title"],
            "Ort": event.get("city") or "—",
            "Turnier-Startklasse": event["group"],
            "Berechnete Klasse": event["progression_class"],
            "Disziplin": event["discipline"],
            "Platz": format_event_place(event),
            "Punkte dieser Punktart": event["progression_points"],
            "Zählt im Rangbereich": event["counted_place"],
        }
        for event in progression["events"]
    ],
    hide_index=True,
    use_container_width=True,
)
st.caption(
    "Regelquelle: punkte_und_platzierungen.md. D→C verwendet C-Grenzen, "
    "C→B die B-Grenzen, B→A die A-Grenzen und A→S die S-Grenzen. "
    "S hat keine dokumentierte nächste Grenze."
)
