"""Privacy-first anonymous telemetry for the LTLI QA public beta.

Only explicitly allow-listed, aggregate fields can be written to the event
table. Uploaded bytes, text, glossary contents, filenames and email addresses
are never accepted by ``track_event``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Mapping

import streamlit as st


APP_VERSION = "1.2.0-beta"
EVENT_NAMES = {
    "session_started",
    "file_uploaded",
    "qa_started",
    "qa_completed",
    "qa_failed",
    "report_downloaded",
}

# Event-specific metadata allow-list. Any unexpected field is discarded.
EVENT_FIELDS = {
    "session_started": {"app_version"},
    "file_uploaded": {"file_formats", "file_count", "size_buckets"},
    "qa_started": {"input_mode", "glossary_used", "segment_count"},
    "qa_completed": {
        "input_mode", "glossary_used", "segment_count", "processing_ms",
        "error_segment_count", "issue_counts",
    },
    "qa_failed": {"stage", "error_type"},
    "report_downloaded": {"report_format", "segment_count"},
}


def get_session_id() -> str:
    """Return a random per-browser-session identifier."""
    if "anonymous_session_id" not in st.session_state:
        st.session_state["anonymous_session_id"] = str(uuid.uuid4())
    return st.session_state["anonymous_session_id"]


def file_size_bucket(size_bytes: int | None) -> str:
    """Convert an exact file size into a coarse, non-identifying range."""
    if size_bytes is None:
        return "unknown"
    if size_bytes < 100 * 1024:
        return "under_100_kb"
    if size_bytes < 1024 * 1024:
        return "100_kb_to_1_mb"
    if size_bytes < 5 * 1024 * 1024:
        return "1_mb_to_5_mb"
    return "5_mb_to_10_mb"


def telemetry_enabled() -> bool:

    """Whether Google Sheets telemetry is configured."""

    from pathlib import Path

    return Path(

        "/etc/ltli/secrets/google-service-account.json"

    ).is_file()





def _insert(table: str, row: Mapping[str, Any]) -> bool:

    """Write anonymous events to Google Sheets."""

    if table != "analytics_events":

        return False



    from google_sheets_storage import append_event



    metadata = {

        "app_version": row.get("app_version"),

        **(row.get("event_data") or {}),

    }



    return append_event(

        session_id=row["session_id"],

        event_name=row["event_name"],

        metadata=metadata,

    )





def track_event(event_name: str, metadata: Mapping[str, Any] | None = None) -> bool:
    """Record an anonymous event after removing all non-allow-listed fields."""
    if event_name not in EVENT_NAMES:
        raise ValueError(f"Unsupported event: {event_name}")
    allowed = EVENT_FIELDS[event_name]
    safe_metadata = {
        key: value for key, value in (metadata or {}).items() if key in allowed
    }
    return _insert(
        "analytics_events",
        {
            "session_id": get_session_id(),
            "event_name": event_name,
            "app_version": APP_VERSION,
            "event_data": safe_metadata,
        },
    )


def track_once(event_key: str, event_name: str, metadata: Mapping[str, Any] | None = None) -> bool:
    state_key = f"telemetry_once_{event_key}"
    if st.session_state.get(state_key):
        return False
    # Mark attempted events as complete so an outage cannot cause repeated calls.
    st.session_state[state_key] = True
    return track_event(event_name, metadata)


def elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))
