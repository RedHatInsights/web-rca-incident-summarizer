# Web RCA Incident Summarizer

## Project Overview

A Python application that fetches incident reports from WebRCA and generates summaries using an LLM
service. Operates in CLI mode (single incident) or worker mode (continuous background processing).
Deployed as a containerized service on OpenShift.

## Dependencies

- **Runtime:** Python 3.12+, click, python-keycloak, wordmill, mdformat, rich, requests
- **Dev:** pytest, ruff, flake8, pre-commit, ipython
- **Package management:** Pipenv
- **CI:** None configured (Dockerfile and OpenShift template for deployment)

## Development Commands

```sh
# Install dependencies
pipenv install --dev

# Run CLI mode
pipenv shell
WEBRCA_TOKEN=$(ocm token) python summarizer.py generate --id <incident-id>

# Run worker mode
pipenv run python summarizer.py worker

# Run tests
pipenv run pytest

# Lint
pipenv run ruff check .
```

See [Setup][readme-setup] in the README for full environment configuration.

## Architecture

Single-file application (`summarizer.py`) with Click CLI, WebRCA API integration, and LLM
summarization via wordmill. Worker mode uses a thread pool for concurrent processing. See
[ARCHITECTURE.md][architecture] for design decisions and component details.

## Code Style

- **Linter:** ruff, flake8
- **Formatter:** Not configured
- **Python version:** 3.12+ (per Pipfile)
- Single-file architecture — all application logic in `summarizer.py`

## Common Mistakes

1. **Missing `.env` file.** The application requires `LLM_API_KEY`, `LLM_BASE_URL`, and
   `LLM_MODEL_NAME` environment variables. Without these, the application will fail at startup
   with no clear error message.

2. **Confusing CLI and worker authentication.** CLI mode uses `WEBRCA_TOKEN` (short-lived OCM
   token). Worker mode uses `SSO_OFFLINE_TOKEN` or `SSO_CLIENT_ID`/`SSO_CLIENT_SECRET`. Using
   the wrong auth method for the wrong mode will produce 401 errors.

3. **Running worker with `MAX_WORKERS > 1` without testing.** The default is 1. Increasing
   concurrency may hit WebRCA API rate limits or LLM service quotas, causing silent failures
   in the thread pool.

[readme-setup]: ./README.md#setup
[architecture]: ./ARCHITECTURE.md
