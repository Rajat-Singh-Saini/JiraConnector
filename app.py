"""Natural-language Jira Cloud issue search web app."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request

load_dotenv()

app = Flask(__name__)

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
JIRA_SEARCH_PATH = "/rest/api/3/search/jql"
RESULT_LIMIT = 500
ANALYZED_FIELDS = {
    "summary": "Summary",
    "description": "Description",
    "status": "Status",
    "issuetype": "Issue type",
    "project": "Project",
    "assignee": "Assignee",
    "reporter": "Reporter",
    "priority": "Priority",
    "labels": "Labels",
    "components": "Components",
    "fixVersions": "Fix versions",
    "duedate": "Due date",
}


class AppError(Exception):
    """An expected, user-displayable application error."""


def required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AppError(f"Set {name} in your .env file before searching.")
    return value


def translate_to_jql(question: str) -> str:
    """Translate the user's natural-language request into a read-only JQL query."""
    api_key = required_setting("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    system_prompt = (
        "Translate the user's request into one Jira Cloud JQL query. "
        "Return only JQL, with no markdown or explanation. Use only read-only search "
        "syntax. Prefer standard Jira fields and functions (currentUser(), startOfDay(), "
        "-7d) where appropriate. Do not invent project keys, usernames, or field names; "
        "if a request is ambiguous, make the safest reasonable JQL interpretation."
    )
    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": 0,
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except requests.Timeout as exc:
        raise AppError("The language service timed out. Please try again.") from exc
    except requests.RequestException as exc:
        detail = ""
        if exc.response is not None:
            try:
                detail = exc.response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                pass
        raise AppError(
            detail or "Could not translate the request. Check your OpenAI settings."
        ) from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AppError("The language service returned an unexpected response.") from exc

    if not isinstance(content, str):
        raise AppError("The language service returned an unexpected response.")
    jql = (
        content.strip()
        .removeprefix("```jql")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    if not jql or len(jql) > 2000:
        raise AppError(
            "The generated Jira query was empty or too long. Try rephrasing it."
        )
    return jql


def search_jira(jql: str) -> list[dict[str, Any]]:
    """Run a bounded issue search using Jira Cloud's REST API."""
    base_url = required_setting("JIRA_BASE_URL").rstrip("/")
    email = required_setting("JIRA_EMAIL")
    token = required_setting("JIRA_API_TOKEN")
    try:
        response = requests.post(
            f"{base_url}{JIRA_SEARCH_PATH}",
            auth=(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={
                "jql": jql,
                "maxResults": RESULT_LIMIT,
                "fields": [
                    *ANALYZED_FIELDS,
                    "updated",
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("issues", [])
    except requests.Timeout as exc:
        raise AppError("Jira did not respond in time. Please try again.") from exc
    except requests.RequestException as exc:
        detail = ""
        if exc.response is not None:
            try:
                detail = exc.response.json().get("errorMessages", [""])[0]
            except (ValueError, AttributeError, IndexError):
                pass
        raise AppError(
            detail or "Could not search Jira. Check your Jira URL and credentials."
        ) from exc
    except (ValueError, AttributeError) as exc:
        raise AppError("Jira returned an unexpected response.") from exc


def display_value(value: Any, key: str = "") -> str:
    """Convert Jira's nested field values into short, readable strings."""
    if value is None:
        return "Unassigned" if key == "assignee" else "—"
    if isinstance(value, dict):
        for candidate in ("displayName", "name", "value", "key"):
            if value.get(candidate):
                return str(value[candidate])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return ", ".join(display_value(item) for item in value) or "—"
    return str(value)


def description_text(value: Any) -> str:
    """Extract readable text from Jira's Atlassian Document Format."""
    if isinstance(value, dict):
        text = value.get("text", "")
        nested = description_text(value.get("content", []))
        return " ".join(part for part in (text, nested) if part).strip()
    if isinstance(value, list):
        return " ".join(filter(None, (description_text(item) for item in value)))
    return ""


def field_is_missing(field: str, value: Any) -> bool:
    if field == "description":
        return not description_text(value)
    if value is None or value == []:
        return True
    if isinstance(value, dict) and not value:
        return True
    return isinstance(value, str) and not value.strip()


def analyze_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic counts and completeness details from returned issues."""
    status_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    unassigned_count = 0

    for issue in issues:
        fields = issue.get("fields", {})
        status = display_value(fields.get("status"))
        issue_type = display_value(fields.get("issuetype"))
        status_counts[status] += 1
        type_counts[issue_type] += 1
        if fields.get("priority"):
            priority_counts[display_value(fields["priority"])] += 1
        if field_is_missing("assignee", fields.get("assignee")):
            unassigned_count += 1

        missing = [
            label
            for field, label in ANALYZED_FIELDS.items()
            if field_is_missing(field, fields.get(field))
        ]
        issue["missing_fields"] = missing
        for label in missing:
            missing_counts[label] += 1
        issue["description_text"] = description_text(fields.get("description"))

    return {
        "total": len(issues),
        "status_counts": status_counts.most_common(),
        "type_counts": type_counts.most_common(),
        "priority_counts": priority_counts.most_common(),
        "missing_counts": [
            (label, missing_counts[label])
            for label in ANALYZED_FIELDS.values()
            if missing_counts[label]
        ],
        "unassigned_count": unassigned_count,
    }


@app.route("/", methods=["GET", "POST"])
def home() -> str:
    question = ""
    jql = ""
    issues: list[dict[str, Any]] = []
    analysis: dict[str, Any] = {}
    error = ""

    if request.method == "POST":
        question = request.form.get("query", "").strip()
        if not question:
            error = "Enter a question to search Jira."
        elif len(question) > 1000:
            error = "Keep your question under 1,000 characters."
        else:
            try:
                jql = translate_to_jql(question)
                issues = search_jira(jql)
                analysis = analyze_issues(issues)
            except AppError as exc:
                error = str(exc)

    return render_template(
        "index.html",
        question=question,
        jql=jql,
        issues=issues,
        analysis=analysis,
        error=error,
        result_limit=RESULT_LIMIT,
        display_value=display_value,
    )


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
