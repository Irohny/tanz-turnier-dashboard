"""Ergebnisse von einer Turnierseite abrufen und archivieren."""

import sqlite3

import streamlit as st

from etl import crawler
from etl.archiv import archive_pages
from etl.auswertung import competition_key
from etl.common import (
    IMPORT_MESSAGE_KEY,
    IMPORT_WARNINGS_KEY,
    get_dashboard_context,
)
from etl.data import filter_tournaments_for_pair


def main() -> None:
    context = get_dashboard_context()
    database = context["database"]
    st.title("Turniere erfassen")
    st.write(
        "Gib die Start- oder Übersichtsseite mit den Turnierergebnissen ein. "
        "Der Crawler folgt den verlinkten Ergebnisseiten und speichert nur "
        "Turniere, an denen das ausgewählte Paar teilgenommen hat."
    )
    st.caption(
        "In den passenden Turnieren bleiben auch die Ranglisten und Wertungen "
        "der anderen Paare erhalten, damit Gegnervergleiche möglich sind. "
        "Bereits vorhandene Archivinhalte werden nicht gelöscht."
    )

    with st.form("crawl_results_form"):
        pair_name = st.text_input(
            "Paar für die Auswertung",
            value=context.get("pair_name", ""),
            placeholder="Vorname Nachname / Vorname Nachname",
            help="Am besten beide Namen angeben, damit nur passende Turniere gespeichert werden.",
        )
        start_url = st.text_input(
            "Link zur Ergebnisseite",
            placeholder="https://www.1scn.de/turnierergebnisse_tanzen_2026/index.htm",
        )
        with st.expander("Erweiterte Einstellungen"):
            max_pages = st.number_input(
                "Maximale Seitenanzahl",
                min_value=1,
                max_value=2000,
                value=500,
                help="Schutz vor Endlosschleifen; bei größeren Turnierarchiven erhöhen.",
            )
        submitted = st.form_submit_button(
            "Ergebnisse abrufen und speichern", type="primary"
        )

    if not submitted:
        return

    pair_query = (pair_name or "").strip()
    if not pair_query:
        st.error("Bitte gib das Paar an, dessen Turniere gespeichert werden sollen.")
        return

    try:
        start_url = crawler.validate_start_url(start_url)
    except ValueError as error:
        st.error(str(error))
        return

    errors: list[str] = []
    try:
        with st.spinner("Ergebnisse werden abgerufen und aufbereitet …"):
            crawled_pages = crawler.crawl(
                start_url,
                delay=0.5,
                max_pages=int(max_pages),
                cache=None,
                errors=errors,
            )
            if not crawled_pages:
                st.error(
                    "Es wurden keine HTML-Seiten geladen. Prüfe den Link und "
                    "den Netzwerkzugriff."
                )
                if errors:
                    st.caption(errors[0])
                return

            processed_pages = crawler.process_pages(crawled_pages, include_all=True)
            if not processed_pages:
                st.error(
                    "Die geladenen Seiten enthalten keine erkennbaren "
                    "Ergebnisdaten. Der Archivbestand wurde nicht geändert."
                )
                return

            selected_pages = filter_tournaments_for_pair(processed_pages, pair_query)
            if not selected_pages:
                st.error(
                    f"Für «{pair_query}» wurde in den abgerufenen Ergebnissen "
                    "kein Turnier gefunden. Das Archiv wurde nicht geändert."
                )
                return

            inserted, updated, unchanged = archive_pages(
                database, start_url, selected_pages
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        st.error(f"Crawl oder Archivierung fehlgeschlagen: {error}")
        return

    competition_count = len({competition_key(page) for page in selected_pages})
    result_count = sum(len(page["paar_ergebnisse"]) for page in selected_pages)
    st.session_state[IMPORT_MESSAGE_KEY] = (
        f"Import für {pair_query} abgeschlossen: {competition_count} passende "
        f"Turniere, {result_count} Einzelwertungen; "
        f"{inserted} neu, {updated} aktualisiert, "
        f"{unchanged} unverändert."
    )
    if not result_count:
        st.warning(
            "Es wurden keine paarbezogenen Einzelwertungen erkannt. "
            "Platzierungen aus den Ranglisten können trotzdem verfügbar sein."
        )
    warnings = []
    if not result_count:
        warnings.append("Keine paarbezogenen Einzelwertungen erkannt.")
    if errors:
        warnings.extend(["Der Import ist möglicherweise unvollständig.", *errors[:5]])
        st.warning(
            f"Bei {len(errors)} Seite(n) gab es Abruffehler. Die erfolgreich "
            "geladenen Seiten wurden gespeichert; der Import kann unvollständig sein."
        )
        for error in errors[:5]:
            st.caption(error)
    if len(crawled_pages) >= max_pages:
        warnings.append(f"Das Seitenlimit von {max_pages} wurde erreicht.")
        st.warning(
            f"Das Seitenlimit von {max_pages} wurde erreicht. Prüfe, ob weitere "
            "Ergebnisseiten nicht abgerufen wurden."
        )
    st.session_state[IMPORT_WARNINGS_KEY] = warnings
    st.rerun()


main()
