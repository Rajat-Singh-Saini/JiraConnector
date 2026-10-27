# Jira Finder

A small Streamlit application that turns plain-English questions into Jira Query Language (JQL), searches a Jira Cloud site, and displays matching issues.

## Requirements

- Python 3.10+
- A Jira Cloud account with permission to view the issues you want to search
- An Atlassian API token
- An OpenAI API key (the app uses it only for natural-language-to-JQL translation)

## Setup

1. Activate the existing virtual environment and install the dependencies from `requirements.txt`.
2. Create a `.env` file in the project root and set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `OPENAI_API_KEY`.
   - Create an Atlassian API token in your Atlassian account security settings.
   - Create an OpenAI API key in the OpenAI dashboard.
   - Do not commit `.env` or share your API tokens.
3. Start the app with `streamlit run MyJira.py`.

Ask something like “Show unresolved bugs assigned to me and updated this week.” The app displays up to 500 matching issues, generated JQL, readable task descriptions, and counts grouped by status, issue type, and priority. It also reports missing standard-field values per issue and across the result set. Each search is read-only.

Completeness checks cover summary, description, status, issue type, project, assignee, reporter, priority, labels, components, fix versions, and due date. Jira custom fields and project-specific required-field rules are not included.

## Configuration

- `JIRA_BASE_URL`: your Jira Cloud site, e.g. `https://company.atlassian.net`
- `JIRA_EMAIL`: email associated with the Jira account/API token
- `JIRA_API_TOKEN`: Atlassian API token
- `OPENAI_API_KEY`: key for translating English to JQL
- `OPENAI_MODEL`: optional model override; defaults to `gpt-4o-mini`

This starter app is intended for local use. Before deploying it for multiple users, add application authentication, rate limiting, and per-user Jira credentials; never expose a shared Jira API token through a public service.
