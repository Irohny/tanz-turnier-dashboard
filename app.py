"""Streamlit-Einstiegspunkt für das Turnierauswertungs-Dashboard."""

from collections.abc import Mapping
from hmac import compare_digest

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from etl.common import (
    CONTEXT_KEY,
    build_dashboard_context,
    load_sidebar_data,
)

AUTH_STATE_KEY = "dashboard_authenticated"


def _auth_config() -> tuple[str, str] | None:
    try:
        auth = st.secrets.get("auth")
    except StreamlitSecretNotFoundError:
        return None
    if not isinstance(auth, Mapping):
        return None
    user = auth.get("user")
    password = auth.get("password")
    if not isinstance(user, str) or not user:
        return None
    if not isinstance(password, str) or not password:
        return None
    return user, password


def require_login() -> bool:
    credentials = _auth_config()
    if credentials is None:
        st.error(
            "Der Zugang ist nicht konfiguriert. Hinterlege `auth.user` und "
            "`auth.password` in den Streamlit Secrets."
        )
        return False

    if st.session_state.get(AUTH_STATE_KEY) is True:
        if st.sidebar.button("Abmelden"):
            del st.session_state[AUTH_STATE_KEY]
            st.rerun()
        return True

    st.title("Turnierblick")
    st.caption("Bitte melde dich an, um das Dashboard zu öffnen.")
    with st.form("login"):
        user = st.text_input("Benutzer")
        password = st.text_input("Passwort", type="password")
        submitted = st.form_submit_button("Anmelden", type="primary")

    if not submitted:
        return False

    expected_user, expected_password = credentials
    valid_user = compare_digest(user, expected_user)
    valid_password = compare_digest(password, expected_password)
    if not valid_user or not valid_password:
        st.error("Benutzer oder Passwort ist nicht korrekt.")
        return False

    st.session_state[AUTH_STATE_KEY] = True
    st.rerun()
    return False


def main() -> None:
    st.set_page_config(
        page_title="Turnierblick",
        page_icon="💃",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            background: color-mix(in srgb, currentColor 4%, transparent);
            border-color: color-mix(in srgb, currentColor 15%, transparent);
            border-radius: .75rem;
        }
        [data-testid="stMetric"] {
            padding: 1rem;
            border: 1px solid color-mix(in srgb, currentColor 15%, transparent);
            border-radius: .75rem;
            background: color-mix(in srgb, currentColor 4%, transparent);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not require_login():
        return

    navigation = st.navigation(
        [
            st.Page("dashboard_pages/overview.py", title="Überblick", default=True),
            st.Page("dashboard_pages/dance.py", title="Tänze"),
            st.Page("dashboard_pages/judges.py", title="Wertungsrichter"),
            st.Page("dashboard_pages/opponents.py", title="Gegnerbilanz"),
            st.Page("dashboard_pages/clubs.py", title="Vereine"),
            st.Page("dashboard_pages/locations.py", title="Turnierorte"),
            st.Page("dashboard_pages/data_quality.py", title="Datenqualität"),
            st.Page("dashboard_pages/tournament_archive.py", title="Turniere"),
            st.Page("dashboard_pages/points.py", title="Punkte & Plätze"),
            st.Page("dashboard_pages/fetch_results.py", title="Turnier erfassen"),
        ],
        position="sidebar",
    )

    database, pages = load_sidebar_data()
    st.session_state[CONTEXT_KEY] = build_dashboard_context(database, pages)
    navigation.run()


if __name__ == "__main__":
    main()
