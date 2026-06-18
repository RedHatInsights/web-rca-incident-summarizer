# Web RCA Incident Summarizer

Fetches incident reports from WebRCA and generates summaries using an LLM service. Supports both
single-incident CLI mode and a background worker mode that continuously processes updated
incidents.

## Prerequisites

- Python 3.12+
- [pyenv][pyenv] (recommended)
- [Pipenv][pipenv]
- [OCM CLI][ocm-cli] (for authentication)

## Setup

1. Install pyenv (follow all steps in the installation guide)
2. Set up the virtual environment:

   ```sh
   pipenv install --dev
   ```

3. Add LLM access info to `.env`:

   ```sh
   LLM_API_KEY=<your key>
   LLM_BASE_URL="https://your-llm-service:443/v1"
   LLM_MODEL_NAME="your-model"
   ```

## Usage

### CLI Mode (Single Incident)

Generate a summary for a specific incident:

```sh
ocm login --use-auth-code
pipenv shell
WEBRCA_TOKEN=$(ocm token) python summarizer.py generate --id ITN-2025-00094
```

### Worker Mode (Continuous Processing)

Processes all incidents that need updated summaries:

```sh
pipenv run python summarizer.py worker
```

The worker generates summaries for incidents where:

- `ai_summary_updated_at` is older than the incident's `changed_at` time
- New follow-ups have been added since the last summary
- New events (non-system) have occurred since the last summary

### Environment Variables

| Variable                  | Description                              | Default                                        |
| ------------------------- | ---------------------------------------- | ---------------------------------------------- |
| `LLM_API_KEY`             | API key for the LLM service              | (required)                                     |
| `LLM_BASE_URL`            | Base URL for the LLM API                 | (required)                                     |
| `LLM_MODEL_NAME`          | Model name to use                        | (required)                                     |
| `LOG_LEVEL`               | Logging level                            | `INFO`                                         |
| `MAX_WORKERS`             | Thread pool size for worker mode         | `1`                                            |
| `WEBRCA_V1_API_BASE_URL`  | WebRCA API base URL                      | `https://api.openshift.com/api/web-rca/v1`     |
| `WEBRCA_TOKEN`            | OCM bearer token (CLI mode)              | (required for CLI)                              |
| `SSO_OFFLINE_TOKEN`       | Red Hat SSO offline token (worker mode)  | (alternative to client credentials)             |
| `SSO_CLIENT_ID`           | SSO client ID (production worker mode)   | (recommended for production)                    |
| `SSO_CLIENT_SECRET`       | SSO client secret (production)           | (recommended for production)                    |

## Deployment

A Dockerfile is included for container deployment. An OpenShift deployment template is in
`deploy/template.yaml`.

## License

No license file is included in this repository.

[pyenv]: https://github.com/pyenv/pyenv
[pipenv]: https://pipenv.pypa.io/
[ocm-cli]: https://github.com/openshift-online/ocm-cli
