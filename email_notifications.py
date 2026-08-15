"""Best-effort email notifications for newly submitted beta feedback."""

from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Mapping

import streamlit as st


LOGGER = logging.getLogger(__name__)


def _smtp_settings() -> dict[str, Any] | None:
    required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD")
    try:
        values = {key: st.secrets[key] for key in required}
    except (KeyError, FileNotFoundError):
        return None

    return {
        "host": str(values["SMTP_HOST"]),
        "port": int(values["SMTP_PORT"]),
        "username": str(values["SMTP_USERNAME"]),
        "password": str(values["SMTP_PASSWORD"]),
        "use_ssl": bool(st.secrets.get("SMTP_USE_SSL", True)),
        "from_email": str(st.secrets.get("FEEDBACK_FROM_EMAIL", "contact@ltli.kr")),
        "to_email": str(st.secrets.get("FEEDBACK_TO_EMAIL", "kvpark10@naver.com")),
    }


def send_feedback_notification(feedback: Mapping[str, Any]) -> bool:
    """Email non-email feedback fields without affecting the submission result."""
    settings = _smtp_settings()
    if settings is None:
        return False

    fields = [
        ("Overall satisfaction", feedback.get("satisfaction")),
        ("Helpfulness", feedback.get("helpfulness")),
        ("False-positive level", feedback.get("false_positive_level")),
        ("Most useful check", feedback.get("most_useful_rule")),
        ("Requested features", feedback.get("requested_features")),
        ("Reuse intention", feedback.get("reuse_intent")),
        ("Role", feedback.get("job_group")),
        ("Other comments", feedback.get("comments")),
    ]

    message = EmailMessage()
    message["Subject"] = f"[LTLI QA] New beta feedback — {feedback.get('satisfaction', '—')}/5"
    message["From"] = settings["from_email"]
    message["To"] = settings["to_email"]
    message.set_content(
        "New LTLI QA beta feedback was submitted.\n\n"
        + "\n".join(f"{label}: {value or '—'}" for label, value in fields)
        + "\n\nDashboard: https://ltli-feedback-insights.streamlit.app/\n"
        + "Interview email is intentionally excluded from this notification."
    )
    rows = "".join(
        "<tr><th style='text-align:left;padding:6px 12px 6px 0'>"
        f"{html.escape(label)}</th><td style='padding:6px 0'>{html.escape(str(value or '—'))}</td></tr>"
        for label, value in fields
    )
    message.add_alternative(
        "<h2>New LTLI QA beta feedback</h2>"
        f"<table>{rows}</table>"
        "<p><a href='https://ltli-feedback-insights.streamlit.app/'>Open administrator dashboard</a></p>"
        "<p><small>Interview email is intentionally excluded from this notification.</small></p>",
        subtype="html",
    )

    try:
        if settings["use_ssl"]:
            with smtplib.SMTP_SSL(
                settings["host"], settings["port"], timeout=8,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.login(settings["username"], settings["password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings["host"], settings["port"], timeout=8) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings["username"], settings["password"])
                smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError) as error:
        # Never log credentials or message contents. The exception type and
        # SMTP response are sufficient for operational diagnosis.
        LOGGER.warning(
            "LTLI feedback email notification failed (%s): %s",
            type(error).__name__,
            error,
        )
        return False
