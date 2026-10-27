"""Streamlit interface for natural-language Jira issue search."""

from __future__ import annotations

import streamlit as st

from app import AppError, analyze_issues, display_value, search_jira, translate_to_jql

st.set_page_config(page_title="Jira Finder", page_icon="🔎", layout="wide")
st.title("Rajat's Jira Finder")
with st.form("jira_search"):
    question = st.text_area(
        "Enter your Jira query in plain English",
        placeholder="For example: Show unresolved bugs assigned to me and updated this week",
        max_chars=1000,
        height=100,
    )
    submitted = st.form_submit_button("Search Jira", type="primary")

if submitted:
    st.session_state.pop("jira_search_result", None)
    st.session_state.pop("jira_search_error", None)

    if not question.strip():
        st.session_state.jira_search_error = "Enter a question to search Jira."
    else:
        try:
            with st.spinner("Searching Jira..."):
                generated_jql = translate_to_jql(question.strip())
                found_issues = search_jira(generated_jql)
                analysis = analyze_issues(found_issues)
            st.session_state.jira_search_result = {
                "jql": generated_jql,
                "issues": found_issues,
                "analysis": analysis,
            }
        except AppError as exc:
            st.session_state.jira_search_error = str(exc)

if error := st.session_state.get("jira_search_error"):
    st.error(error)

if result := st.session_state.get("jira_search_result"):
    analysis = result["analysis"]
    issues = result["issues"]

    st.subheader(f"Results · {analysis['total']} issue(s)")
    with st.expander("Generated JQL"):
        st.code(result["jql"], language="sql")

    if issues:
        metric_columns = st.columns(3)
        metric_columns[0].metric("Matching issues", analysis["total"])
        metric_columns[1].metric("Unassigned", analysis["unassigned_count"])
        metric_columns[2].metric(
            "Fields with missing values", len(analysis["missing_counts"])
        )

        count_columns = st.columns(4)
        count_groups = (
            ("By status", analysis["status_counts"]),
            ("By issue type", analysis["type_counts"]),
            ("By priority", analysis["priority_counts"]),
            ("Missing values", analysis["missing_counts"]),
        )
        for column, (heading, counts) in zip(count_columns, count_groups):
            with column:
                st.markdown(f"**{heading}**")
                if counts:
                    for label, count in counts:
                        st.write(f"{label}: {count}")
                else:
                    st.caption("None")

        st.caption(
            "Completeness checks cover standard fields only, not custom or "
            "project-specific required fields."
        )

        st.markdown("### Issues")
        for issue in issues:
            fields = issue.get("fields", {})
            issue_key = issue.get("key", "Jira issue")
            summary = display_value(fields.get("summary"))
            with st.expander(f"{issue_key} · {summary}"):
                detail_columns = st.columns(4)
                details = (
                    ("Status", display_value(fields.get("status"))),
                    ("Type", display_value(fields.get("issuetype"))),
                    ("Assignee", display_value(fields.get("assignee"), "assignee")),
                    ("Priority", display_value(fields.get("priority"))),
                )
                for column, (label, value) in zip(detail_columns, details):
                    column.markdown(f"**{label}**  \n{value}")

                if issue.get("description_text"):
                    st.markdown("**Description**")
                    st.write(issue["description_text"])

                if issue.get("missing_fields"):
                    st.warning("Missing: " + ", ".join(issue["missing_fields"]))
                else:
                    st.success("No missing values in the checked fields.")
    else:
        st.info("No matching issues. Try changing or broadening your query.")
