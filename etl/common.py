"""Gemeinsame Daten- und UI-Helfer für die Dashboard-Seiten."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from etl.archiv import archive_json_file, load_pages
from etl.auswertung import competition_key, source_name
from etl.data import (
    build_pair_dashboard,
    filter_events,
    pair_options,
    summarize_pair_events,
)
from etl.domain import pair_identity

DEFAULT_DATABASE = os.environ.get("TURNIER_DATABASE", "turniere.sqlite")
DEFAULT_JSON = "ergebnis.json"
CONTEXT_KEY = "dashboard_context"
IMPORT_MESSAGE_KEY = "dashboard_import_message"
IMPORT_WARNINGS_KEY = "dashboard_import_warnings"
# Increment when the analysis produced by etl.data changes.
ANALYSIS_CACHE_VERSION = 2
ArchiveToken = tuple[tuple[int, int, int, int], ...]


def archive_token(database: str) -> ArchiveToken:
    stamps = []
    for path in (Path(database), Path(database + "-wal")):
        try:
            stat = path.stat()
        except FileNotFoundError:
            stamps.append((0, 0, 0, 0))
        else:
            stamps.append(
                (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            )
    return tuple(stamps)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_pages(database: str, token: ArchiveToken) -> list[dict[str, Any]]:
    del token  # Part of the Streamlit cache key.
    return load_pages(database)


@st.cache_data(show_spinner=False, max_entries=8)
def pair_catalog(
    database: str, token: ArchiveToken, _pages: list[dict[str, Any]]
) -> tuple[list[str], str]:
    del database, token  # Part of the Streamlit cache key.
    pairs = pair_options(_pages)
    counts: Counter[str] = Counter(
        pair_identity(str(result.get("paar", "")))
        for page in _pages
        if source_name(page).lower() not in {"starter.htm", "tabges.htm"}
        for result in page.get("paar_ergebnisse", [])
    )
    default_pair = (
        max(pairs, key=lambda pair: counts[pair_identity(pair)]) if pairs else ""
    )
    return pairs, default_pair


@st.cache_data(show_spinner=False, max_entries=32)
def cached_events(
    database: str, token: ArchiveToken, pair: str, _pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    del database, token  # Part of the Streamlit cache key.
    return summarize_pair_events(_pages, pair)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_analysis(
    database: str,
    token: ArchiveToken,
    pair: str,
    selected_keys: tuple[tuple[str, str], ...],
    _pages: list[dict[str, Any]],
    analysis_version: int,
) -> dict[str, Any]:
    del database, token, analysis_version  # Part of the Streamlit cache key.
    keys = set(selected_keys)
    return build_pair_dashboard(
        [page for page in _pages if competition_key(page) in keys], pair
    )


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "nicht gespeichert"


def format_place(value: float | None) -> str:
    if value is None:
        return "—"
    formatted = f"{value:g}".replace(".", ",")
    return f"{formatted}."


def format_event_place(event: dict[str, Any]) -> str:
    bounds = event.get("place_range")
    if bounds and bounds[0] != bounds[1]:
        return f"{bounds[0]}.-{bounds[1]}."
    return format_place(event["place"])


def _try_import(database: str, json_file: str) -> bool:
    try:
        inserted, updated, unchanged = archive_json_file(database, json_file)
    except (OSError, sqlite3.Error, ValueError) as error:
        st.sidebar.error(f"Import fehlgeschlagen: {error}")
        return False
    st.session_state[IMPORT_MESSAGE_KEY] = (
        f"Import abgeschlossen: {inserted} neu, {updated} aktualisiert, "
        f"{unchanged} unverändert."
    )
    return True


def load_sidebar_data() -> tuple[str, list[dict[str, Any]] | None]:
    st.sidebar.title("Turnierblick")
    with st.sidebar.expander(
        "Archiv & JSON-Import",
        expanded=not Path(
            st.session_state.get("dashboard_database", DEFAULT_DATABASE)
        ).is_file(),
    ):
        database = st.text_input(
            "SQLite-Archiv", value=DEFAULT_DATABASE, key="dashboard_database"
        )
        json_file = st.text_input("JSON-Import", value=DEFAULT_JSON)
        import_requested = st.button("JSON ins Archiv importieren")
    if message := st.session_state.pop(IMPORT_MESSAGE_KEY, None):
        st.sidebar.success(message)
    for warning in st.session_state.pop(IMPORT_WARNINGS_KEY, []):
        st.sidebar.warning(warning)

    if import_requested and _try_import(database, json_file):
        st.rerun()

    if not Path(database).is_file():
        st.sidebar.info(
            "Noch kein Archiv gefunden. Importiere eine Crawler-JSON-Datei "
            "oder erstelle das Archiv mit dem Crawler."
        )
        return database, None

    try:
        resolved_database = str(Path(database).resolve())
        pages = cached_pages(resolved_database, archive_token(resolved_database))
    except (OSError, sqlite3.Error, ValueError) as error:
        st.sidebar.error(f"Archiv kann nicht gelesen werden: {error}")
        return database, None
    return database, pages


def build_dashboard_context(
    database: str, pages: list[dict[str, Any]] | None
) -> dict[str, Any]:
    context: dict[str, Any] = {"database": database, "pages": pages}
    if pages is None:
        context["status"] = "missing_archive"
        return context
    if not pages:
        context["status"] = "empty_archive"
        return context

    resolved_database = str(Path(database).resolve())
    token = archive_token(resolved_database)
    pairs, default_pair = pair_catalog(resolved_database, token, pages)
    if not pairs:
        context["status"] = "no_pairs"
        return context

    with st.sidebar.expander("Filter & Paar ändern"):
        previous_pair = st.session_state.get("dashboard_pair", default_pair)
        if previous_pair not in pairs:
            st.session_state["dashboard_pair"] = default_pair
        pair_name = st.selectbox(
            "Mein Paar",
            pairs,
            index=pairs.index(
                previous_pair if previous_pair in pairs else default_pair
            ),
            key="dashboard_pair",
        )

        events = cached_events(resolved_database, token, pair_name, pages)
        if not events:
            context.update(status="no_events", pair_name=pair_name)
            return context

        groups = ["Alle"] + sorted({event["group"] for event in events})
        disciplines = ["Alle"] + sorted({event["discipline"] for event in events})
        selected_group = st.selectbox("Startgruppe", groups)
        selected_discipline = st.selectbox("Disziplin", disciplines)

        known_dates = [event["date"] for event in events if event["date"]]
        date_range = None
        if known_dates:
            first_date, last_date = min(known_dates), max(known_dates)
            date_selection = st.date_input(
                "Zeitraum",
                value=(first_date, last_date),
                min_value=first_date,
                max_value=last_date,
            )
            if isinstance(date_selection, (tuple, list)):
                if len(date_selection) == 2:
                    date_range = (date_selection[0], date_selection[1])
                elif len(date_selection) == 1:
                    date_range = (date_selection[0], date_selection[0])
            elif isinstance(date_selection, date):
                date_range = (date_selection, date_selection)
            if any(event["date"] is None for event in events):
                st.caption(
                    "Turniere ohne erkanntes Datum werden bei der Zeitraumsauswahl "
                    "ausgeblendet."
                )
        else:
            st.caption("Für diese Daten sind keine Turnierdaten erkennbar.")

    filtered_events = filter_events(
        events,
        group=selected_group,
        discipline=selected_discipline,
        date_range=date_range,
    )
    st.sidebar.caption(
        f"{pair_name} · {selected_group} · {selected_discipline} · "
        f"{len(filtered_events)} Turniere"
    )
    if date_range:
        st.sidebar.caption(
            f"{format_date(date_range[0])} – {format_date(date_range[1])}"
        )
    if not filtered_events:
        context.update(status="no_filtered_events", pair_name=pair_name)
        return context

    selected_keys = tuple(sorted({event["key"] for event in filtered_events}))
    analysis = cached_analysis(
        resolved_database,
        token,
        pair_name,
        selected_keys,
        pages,
        analysis_version=ANALYSIS_CACHE_VERSION,
    )
    detail_count = sum(
        1
        for event in filtered_events
        for page, _ in event["results"]
        if source_name(page).lower() not in {"starter.htm", "tabges.htm"}
    )
    context.update(
        status="ready",
        pair_name=pair_name,
        events=filtered_events,
        analysis=analysis,
        detail_count=detail_count,
        subtitle=(
            f"{pair_name} · {selected_group} · {selected_discipline} · "
            f"{len(filtered_events)} Turniere"
        ),
    )
    return context


def get_dashboard_context() -> dict[str, Any]:
    context = st.session_state.get(CONTEXT_KEY)
    if context is None:
        raise RuntimeError(
            "Das Dashboard wurde ohne gemeinsamen Seitenkontext gestartet."
        )
    return context


def require_analysis_context() -> dict[str, Any] | None:
    context = get_dashboard_context()
    status = context["status"]
    if status == "ready":
        return context

    st.title("Tanzturnier-Auswertung")
    if status == "missing_archive":
        st.info(
            f"Lege zuerst ein Archiv unter `{context['database']}` an oder "
            f"importiere `{DEFAULT_JSON}` über die Seitenleiste."
        )
    elif status == "empty_archive":
        st.info("Das Archiv enthält noch keine Turnierseiten.")
    elif status == "no_pairs":
        st.warning(
            "Im Archiv wurden keine Paare erkannt. Importiere Ergebnisse mit "
            "Startlisten oder Ranglisten."
        )
    elif status == "no_events":
        st.warning("Für dieses Paar wurden keine Turniere im Archiv gefunden.")
    else:
        st.info("Keine Turniere passen zu den gewählten Filtern.")
    return None


def summary_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Turnier": event["title"],
            "Ort": event.get("city") or "—",
            "Datum": format_date(event["date"]),
            "Startgruppe": event["group"],
            "Disziplin": event["discipline"],
            "Platz": format_event_place(event),
            "Feldgröße": event["field_size"] or "—",
        }
        for event in events
    ]


def csv_export(events: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    fields = [
        "Turnier",
        "Datum",
        "Startgruppe",
        "Disziplin",
        "Platz",
        "Feldgröße",
        "Platzierungs-Perzentil",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, delimiter=";")
    writer.writeheader()
    for event in events:
        score = event["normalized_place"]
        writer.writerow(
            {
                "Turnier": event["title"],
                "Datum": event["date"].isoformat() if event["date"] else "",
                "Startgruppe": event["group"],
                "Disziplin": event["discipline"],
                "Platz": format_event_place(event) if event.get("place_range") else "",
                "Feldgröße": event["field_size"] or "",
                "Platzierungs-Perzentil": (
                    round(score * 100, 1) if score is not None else ""
                ),
            }
        )
    return output.getvalue()


def render_header(
    title: str, subtitle: str, events: list[dict[str, Any]], pair_name: str
) -> None:
    heading, export = st.columns([5, 1])
    with heading:
        st.title(title)
        st.caption(subtitle)
    with export, st.popover("Export"):
        st.download_button(
            "CSV exportieren",
            data=csv_export(events),
            file_name=f"turnierauswertung-{pair_name.replace('/', '-')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
