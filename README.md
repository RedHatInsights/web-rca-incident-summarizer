# web-rca-incident-summarizer

Fetches incident reports from WebRCA and summarizes them using a LLM service.

## Setup

1. It is recommended to [install pyenv](https://github.com/pyenv/pyenv?tab=readme-ov-file#installation).

     NOTE: Make sure to follow all steps! (A, B, C, D, and so on)

2. Set up the virtual environment:

    ```shell
    pipenv install --dev
    ```

3. Add your LLM access info into `.env`, example:

   ```bash
   LLM_API_KEY=<your key>
   LLM_BASE_URL="https://your-llm-service:443/v1"
   LLM_MODEL_NAME="your-model"
   ```

## Running CLI script

The 'generate' subcommand will fetch a single incident from WebRCA and summarize it. The result will be printed to the CLI.

1. Install [OCM CLI](https://github.com/openshift-online/ocm-cli)

2. Authenticate with OCM: `ocm login --use-auth-code`

3. Run script for a given incident ID:

```shell
pipenv shell
WEBRCA_TOKEN=$(ocm token) python summarizer.py generate --id ITN-2025-00094
```

## Running as a worker

The 'worker' subcommand fetches all incidents from WebRCA, generates summaries, and then uses the API to update the incident's "ai_summary" field.

- It runs tasks in a threadpool.
- Summaries are only generated for incidents which have an "ai_summary_updated_at" time older than "updated_at" time.

Example environment variable configuration:
```bash
LOG_LEVEL=INFO
MAX_WORKERS=3
WEBRCA_V1_API_BASE_URL="https://api.stage.openshift.com/api/web-rca/v1"
SSO_OFFLINE_TOKEN="<offline token>"
LLM_API_KEY="<your key>"
LLM_BASE_URL="https://your-llm-service:443/v1"
LLM_MODEL_NAME="your-model"
```

The environment variable `SSO_OFFLINE_TOKEN` should be set to a valid [OCM offline token](https://console.redhat.com/openshift/token)

Then the script can be invoked with:

```shell
pipenv run python summarizer.py worker
```

For production deployments, `SSO_CLIENT_ID` and `SSO_CLIENT_SECRET` are recommended to be set instead of utilizing `SSO_OFFLINE_TOKEN`
