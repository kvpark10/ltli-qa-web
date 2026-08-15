"""Private administrator dashboard for LTLI QA beta feedback and usage."""

from __future__ import annotations

import hmac
import json
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st


st.set_page_config(page_title="LTLI QA Beta Dashboard", page_icon="📊", layout="wide")

st.title("LTLI QA Beta Dashboard")
st.caption("Private, read-only view of anonymous QA usage and beta feedback.")


def require_admin_login() -> None:
    """Stop before any database call unless the administrator is authenticated."""
    try:
        expected_password = str(st.secrets["ADMIN_PASSWORD"])
    except (KeyError, FileNotFoundError):
        st.error("Administrator login is not configured.")
        st.stop()

    if st.session_state.get("admin_authenticated"):
        with st.sidebar:
            st.success("Administrator signed in")
            if st.button("Sign out"):
                st.session_state["admin_authenticated"] = False
                st.rerun()
        return

    with st.form("admin_login"):
        supplied_password = st.text_input("Administrator password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if hmac.compare_digest(supplied_password, expected_password):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        st.error("Incorrect administrator password.")
    st.stop()


require_admin_login()


def _settings() -> tuple[str, str]:
    try:
        url = str(st.secrets["SUPABASE_URL"]).rstrip("/")
        key = str(st.secrets["SUPABASE_SERVICE_ROLE_KEY"])
    except (KeyError, FileNotFoundError) as error:
        raise RuntimeError("Supabase administrator Secrets are not configured.") from error
    if not url.startswith("https://") or not key:
        raise RuntimeError("Supabase administrator Secrets are invalid.")
    return url, key


@st.cache_data(ttl=60, show_spinner=False)
def load_table(table: str, columns: str = "*") -> pd.DataFrame:
    if table not in {"analytics_events", "beta_feedback", "interview_opt_ins"}:
        raise ValueError("Unsupported table")
    url, key = _settings()
    query = urllib.parse.urlencode(
        {"select": columns, "order": "created_at.desc", "limit": "5000"}
    )
    request = urllib.request.Request(
        f"{url}/rest/v1/{table}?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load {table}.") from error

    dataframe = pd.DataFrame(rows)
    if "created_at" in dataframe.columns:
        dataframe["created_at"] = pd.to_datetime(
            dataframe["created_at"], utc=True, errors="coerce"
        )
    return dataframe


def csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8-sig")


if st.button("Refresh data", type="primary"):
    st.cache_data.clear()

try:
    events = load_table("analytics_events")
    feedback = load_table("beta_feedback")
    opt_ins = load_table("interview_opt_ins")
except RuntimeError as error:
    st.error(str(error))
    st.stop()

overview_tab, feedback_tab, activity_tab, interview_tab = st.tabs(
    ["Overview", "Feedback", "Usage activity", "Interview opt-ins"]
)

with overview_tab:
    completed = events[events.get("event_name", pd.Series(dtype=str)) == "qa_completed"]
    unique_sessions = events["session_id"].nunique() if "session_id" in events else 0
    average_score = feedback["satisfaction"].mean() if not feedback.empty else 0

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Anonymous sessions", f"{unique_sessions:,}")
    metric2.metric("Completed QA runs", f"{len(completed):,}")
    metric3.metric("Feedback responses", f"{len(feedback):,}")
    metric4.metric("Average satisfaction", f"{average_score:.1f} / 5" if average_score else "—")

    left, right = st.columns(2)
    with left:
        st.subheader("Satisfaction")
        if feedback.empty:
            st.info("No feedback has been submitted yet.")
        else:
            satisfaction_counts = (
                feedback["satisfaction"].value_counts().sort_index().rename("Responses")
            )
            st.bar_chart(satisfaction_counts)
    with right:
        st.subheader("Reuse intention")
        if feedback.empty:
            st.info("No feedback has been submitted yet.")
        else:
            st.bar_chart(feedback["reuse_intent"].fillna("Not answered").value_counts())

    st.subheader("Most useful checks")
    useful = feedback.get("most_useful_rule", pd.Series(dtype=str)).dropna()
    useful = useful[useful.astype(str).str.strip() != ""]
    if useful.empty:
        st.info("No check preferences have been submitted yet.")
    else:
        st.bar_chart(useful.value_counts().head(15))

with feedback_tab:
    st.subheader("Submitted feedback")
    if feedback.empty:
        st.info("No feedback has been submitted yet.")
    else:
        score_options = sorted(feedback["satisfaction"].dropna().astype(int).unique())
        selected_scores = st.multiselect(
            "Satisfaction", score_options, default=score_options
        )
        role_options = sorted(feedback["job_group"].dropna().astype(str).unique())
        selected_roles = st.multiselect("Role", role_options, default=role_options)
        filtered_feedback = feedback[
            feedback["satisfaction"].astype(int).isin(selected_scores)
        ]
        if role_options:
            filtered_feedback = filtered_feedback[
                filtered_feedback["job_group"].isin(selected_roles)
                | filtered_feedback["job_group"].isna()
            ]

        display_columns = [
            "created_at", "satisfaction", "helpfulness", "false_positive_level",
            "most_useful_rule", "requested_features", "reuse_intent", "job_group",
            "comments",
        ]
        display_columns = [column for column in display_columns if column in filtered_feedback]
        st.dataframe(
            filtered_feedback[display_columns], use_container_width=True, hide_index=True
        )
        st.download_button(
            "Download filtered feedback (CSV)",
            csv_bytes(filtered_feedback[display_columns]),
            "ltli_beta_feedback.csv",
            "text/csv",
        )

with activity_tab:
    st.subheader("Anonymous usage activity")
    if events.empty:
        st.info("No usage events have been recorded yet.")
    else:
        event_counts = events["event_name"].value_counts().rename("Count")
        st.bar_chart(event_counts)
        activity_columns = ["created_at", "event_name", "app_version", "event_data"]
        activity_columns = [column for column in activity_columns if column in events]
        st.dataframe(events[activity_columns], use_container_width=True, hide_index=True)
        st.download_button(
            "Download usage events (CSV)",
            csv_bytes(events[activity_columns]),
            "ltli_qa_usage_events.csv",
            "text/csv",
        )

with interview_tab:
    st.subheader("Interview volunteers")
    st.warning(
        "Contains personal information. Use emails only for the consented beta interview purpose."
    )
    if opt_ins.empty:
        st.info("No interview opt-ins have been submitted yet.")
    else:
        opt_in_columns = [column for column in ["created_at", "email"] if column in opt_ins]
        st.dataframe(opt_ins[opt_in_columns], use_container_width=True, hide_index=True)
        st.download_button(
            "Download interview opt-ins (CSV)",
            csv_bytes(opt_ins[opt_in_columns]),
            "ltli_interview_opt_ins.csv",
            "text/csv",
        )

st.divider()
st.caption(
    "Uploaded files, filenames, source text, target text and glossary contents are not collected."
)
