# Architecture

## Overview

The web-rca-incident-summarizer is a single-file Python application (`summarizer.py`) that bridges
the WebRCA incident tracking API with an LLM service for automated incident summarization.

## Module Structure

```text
summarizer.py       # Main application (CLI + worker modes)
prompt.txt          # LLM prompt template for summarization
deploy/
  template.yaml     # OpenShift deployment template
Pipfile             # Python dependency specification
Dockerfile          # Container build definition
```

## Key Components

### CLI Interface (`click`)

The application uses Click to provide two subcommands:

- `generate` — fetches a single incident by ID and prints the summary
- `worker` — continuously processes all incidents needing updated summaries

### WebRCA Integration

- Communicates with the WebRCA v1 REST API to fetch incident data
- Supports two authentication methods: OCM bearer token (CLI) and SSO client credentials (worker)
- Keycloak (`python-keycloak`) handles SSO token exchange

### LLM Integration

- Uses `wordmill.llm.llm_client` for LLM API communication
- Configurable model, endpoint, and API key via environment variables
- Summaries are formatted with `mdformat`

### Worker Mode

- Runs tasks in a thread pool (`concurrent.futures.ThreadPoolExecutor`)
- Filters incidents that need re-summarization based on timestamp comparison
- Updates the incident's `ai_summary` field via the WebRCA API

## Design Decisions

- **Single-file architecture.** The entire application is one Python file. This simplifies
  deployment and containerization for what is a straightforward data pipeline.
- **Thread pool over async.** Worker mode uses threads rather than asyncio because the WebRCA and
  LLM API calls are I/O-bound and the concurrency requirement is modest (`MAX_WORKERS` defaults
  to 1).
- **SSO dual-auth.** CLI mode uses short-lived OCM tokens for developer convenience. Worker mode
  uses SSO client credentials for long-running unattended operation.
