import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import click
import mdformat
import requests
from keycloak import KeycloakOpenID
from rich.console import Console
from rich.logging import RichHandler
from rich.spinner import Spinner
from rich.traceback import install
from wordmill.llm import llm_client

log = logging.getLogger(__name__)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", 1))
WEBRCA_V1_API_BASE_URL = os.environ.get(
    "WEBRCA_V1_API_BASE_URL", "https://api.openshift.com/api/web-rca/v1"
).lstrip("/")
WEBRCA_TOKEN = os.environ.get("WEBRCA_TOKEN")
STATUS_TYPES = os.environ.get("STATUS_TYPES", "new,ongoing,paused,resolved,closed")

SSO_AUTH_URL = os.environ.get("SSO_AUTH_URL", "https://sso.redhat.com/auth/")
SSO_REALM_NAME = os.environ.get("SSO_REALM_NAME", "redhat-external")
SSO_CLIENT_ID = os.environ.get("SSO_CLIENT_ID", "cloud-services")
SSO_CLIENT_SECRET = os.environ.get("SSO_CLIENT_SECRET")
SSO_OFFLINE_TOKEN = os.environ.get("SSO_OFFLINE_TOKEN")


class TokenManager:
    def __init__(self):
        self.access_token = None
        self.expires_at = 0

    def _get_new_token(self):
        keycloak_openid = KeycloakOpenID(
            server_url=SSO_AUTH_URL,
            client_id=SSO_CLIENT_ID,
            client_secret_key=SSO_CLIENT_SECRET,
            realm_name=SSO_REALM_NAME,
        )

        if SSO_OFFLINE_TOKEN:
            token = keycloak_openid.refresh_token(SSO_OFFLINE_TOKEN)
        elif SSO_CLIENT_ID and SSO_CLIENT_SECRET:
            token = keycloak_openid.token(grant_type="client_credentials")
        else:
            raise ValueError(
                "need SSO_CLIENT_ID/SSO_CLIENT_SECRET or SSO_OFFLINE_TOKEN defined"
            )

        self.access_token = token["access_token"]
        self.expires_at = time.time() + token["expires_in"]
        return self.access_token

    def get_access_token(self):
        if WEBRCA_TOKEN:
            return WEBRCA_TOKEN

        if not self.access_token or time.time() >= self.expires_at - 30:
            return self._get_new_token()

        return self.access_token


token_manager = TokenManager()


def _get(api_path: str, params: dict = None) -> dict:
    url = f"{WEBRCA_V1_API_BASE_URL}{api_path}"
    token = token_manager.get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params)
    log.debug(
        'HTTP Request: GET %s "%d %s"',
        url,
        response.status_code,
        response.reason,
    )
    response.raise_for_status()
    return response.json()


def _patch(api_path: str, json_data: dict) -> dict:
    url = f"{WEBRCA_V1_API_BASE_URL}{api_path}"
    token = token_manager.get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.patch(url, headers=headers, json=json_data)
    log.debug(
        'HTTP Request: PATCH %s "%d %s"',
        url,
        response.status_code,
        response.reason,
    )
    response.raise_for_status()
    return response.json()


def _get_all_items(api_path: str, params: dict = None) -> dict:
    items = []
    page = 1
    if not params:
        params = {"page": page}

    while True:
        params["page"] = page
        data = _get(api_path, params)
        items.extend(data["items"])
        log.debug(
            "fetched page %d, fetched items %d, current items %d",
            page,
            len(items),
            data["total"],
        )
        if len(items) >= data["total"]:
            break
        page += 1

    return items


def _filter_by_keys(d: dict, desired_keys: list[str]) -> None:
    for key in list(d.keys()):
        if key not in desired_keys:
            del d[key]


def _cleanup_event_note(text: str) -> str:
    # make sure code block syntax is surrounded by newlines
    text = re.sub("```", "\n```\n", text)

    # remove dynatrace links, they are often really large
    text = re.sub(r"\S+http(s?):\/\/\S+dynatrace\S+", "[dynatrace url]", text)

    # remove hyperlinks and just display plain text
    text = re.sub(r"<(\S+)\|([^\r\n\t\f\v]+)>", r"\2", text)

    # remove multi-line code blocks, they are often large log outputs
    lines = []
    in_code_block = False
    for line in text.split("\n"):
        if line == "```" and not in_code_block:
            in_code_block = True
            # remove text within code block, but preserve indentation of the block
            whitespace = " " * (len(line) - len(line.lstrip()))
            lines.append(f"{whitespace}[code block/log snippet]")
        elif in_code_block:
            if line == "```":
                in_code_block = False
            continue
        else:
            lines.append(line)

    return "\n".join(lines)


def _parse_events(events: list[dict]) -> None:
    desired_keys = ("note", "creator", "created_at", "updated_at")

    for event in events:
        _filter_by_keys(event, desired_keys)

        if "note" in event:
            # remove code blocks from notes
            event["note"] = _cleanup_event_note(event["note"])

        if "creator" in event:
            creator_keys = ("name", "email")
            _filter_by_keys(event["creator"], creator_keys)
            if not event["creator"]:
                # sometimes after filtering, no "desired keys" are left
                del event["creator"]


def _filter_keys(incident: dict) -> None:
    desired_keys = (
        "id",
        "summary",
        "description",
        "incident_id",
        "products",
        "status",
        "external_coordination",
        "created_at",
        "resolved_at",
        "private",
        "creator",
        "incident_owner",
        "participants",
    )
    _filter_by_keys(incident, desired_keys)
    _filter_by_keys(incident["creator"], ("name",))
    if "incident_owner" in incident:
        _filter_by_keys(incident["incident_owner"], ("name",))
    for participant in incident.get("participants", {}):
        _filter_by_keys(participant, ("name",))


def _process_incident(incident: dict) -> dict:
    public_id = incident["incident_id"]
    log.debug("Processing incident '%s' ...", public_id)

    incident_id = incident["id"]

    api_path = f"/incidents/{incident_id}/events"
    params = {
        "order_by": "occurred_at asc",
        "page": 1,
        "size": 999,
        "event_type": "comment,follow_up,escalation,external_reference,audit_log",
    }

    _filter_keys(incident)

    log.info("Fetching events for incident '%s' ...", public_id)
    events = _get_all_items(api_path, params)
    if events:
        _parse_events(events)

    incident["events"] = events

    log.info("Incident '%s' num events: %d", public_id, len(events))

    return incident


def get_incident(public_id: str) -> dict:
    log.info("Fetching incident '%s' from WebRCA...", public_id)

    api_path = "/incidents"
    params = {"public_id": public_id}
    items = _get(api_path, params).get("items", [])

    if not items:
        raise ValueError(f"incident {public_id} not found")

    incident = items[0]

    return incident


def _parse_status_types(status_types: str) -> str:
    split = status_types.lower().split(",")
    to_lowercase = []
    for status in split:
        if status.lower() not in ("new", "ongoing", "paused", "closed", "resolved"):
            raise ValueError(f"invalid status type: {status}")
        to_lowercase.append(status.lower())
    return ",".join(to_lowercase)


def get_all_incidents() -> dict:
    params = None
    if STATUS_TYPES:
        status_param = _parse_status_types(STATUS_TYPES)
        params = {"status": status_param}
    api_path = "/incidents"
    return _get_all_items(api_path, params=params)


def _wait_with_spinner(console, handler):
    time.sleep(0.1)  # allow HTTP POST log to print before spinner
    text = "[magenta]Waiting on LLM response... (bytes received: {bytes_received})[/magenta]"

    spinner = Spinner("aesthetic", text=text.format(bytes_received=0))
    with console.status(spinner):
        while not handler.done:
            bytes_received = len(handler.content.encode("utf-8"))
            spinner.update(text=text.format(bytes_received=bytes_received))
            time.sleep(0.1)


def summarize_incident(prompt, incident, console=None):
    incident = _process_incident(incident)
    as_json = json.dumps(incident)

    log.info(
        "Requesting LLM to summarize... prompt size: %d chars, context size: %d chars",
        len(prompt),
        len(as_json),
    )

    start_time = time.perf_counter()
    handler = llm_client.summarize(as_json, prompt=prompt)

    if console:
        _wait_with_spinner(console, handler)
    else:
        while not handler.done:
            time.sleep(0.1)
        bytes_received = len(handler.content.encode("utf-8"))
        log.info("Summary generated, %d bytes received", bytes_received)

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    log.info(
        f"Summary successfully generated (time elapsed: {elapsed_time:.4f} seconds)"
    )

    try:
        md = mdformat.text(handler.content)
    except Exception as err:
        log.warning("mdformat failed: %s, markdown may contain syntax errors", err)
        md = handler.content

    return md


def summarize_incident_and_update_webrca(prompt, incident, console=None):
    threading.current_thread().name = incident["incident_id"]

    summary_md = summarize_incident(prompt, incident, console)

    incident_uuid = incident["id"]
    api_path = f"/incidents/{incident_uuid}"
    _patch(api_path, json_data={"ai_summary": summary_md})


def _get_last_change_time(incident) -> datetime:
    id = incident["id"]

    # get incident "last_changed_at" time
    incident_last_changed_at = datetime.min.replace(tzinfo=timezone.utc)
    if "last_changed_at" in incident:
        incident_last_changed_at = datetime.fromisoformat(incident["last_changed_at"])
    log.debug("incident_last_changed_at: %s", incident_last_changed_at)

    # get last updated event
    api_path = f"/incidents/{id}/events"
    params = {
        "order_by": "updated_at desc",
        "size": "1",
        "event_type": "comment,follow_up,escalation,external_reference",
    }
    response = _get(api_path, params)
    events_last_changed_at = datetime.min.replace(tzinfo=timezone.utc)
    if response["items"]:
        events_last_changed_at = datetime.fromisoformat(
            response["items"][0]["updated_at"]
        )
    log.debug("events_last_changed_at: %s", events_last_changed_at)

    # get last updated follow-up
    api_path = f"/incidents/{id}/follow_ups"
    params = {"order_by": "updated_at desc", "size": "1"}
    response = _get(api_path, params)
    follow_ups_last_changed_at = datetime.min.replace(tzinfo=timezone.utc)
    if response["items"]:
        follow_ups_last_changed_at = datetime.fromisoformat(
            response["items"][0]["updated_at"]
        )
    log.debug("follow_ups_last_changed_at: %s", follow_ups_last_changed_at)

    changed_at = max(
        incident_last_changed_at, events_last_changed_at, follow_ups_last_changed_at
    )
    log.debug("final changed_at: %s", changed_at)

    return changed_at


def _get_incidents_to_update(max_days_since_update: int) -> list[dict]:
    if max_days_since_update:
        since_time = datetime.now(tz=timezone.utc) - timedelta(
            days=max_days_since_update
        )
    else:
        since_time = datetime.min.replace(tzinfo=timezone.utc)

    incidents = get_all_incidents()

    incidents_to_update = []

    for incident in incidents:
        changed_at = _get_last_change_time(incident)

        ai_summary_updated_at = None
        if "ai_summary_updated_at" in incident:
            ai_summary_updated_at = datetime.fromisoformat(
                incident["ai_summary_updated_at"]
            )

        log.debug("ai_summary_updated_at: %s", ai_summary_updated_at)

        public_id = incident["incident_id"]

        if changed_at < since_time:
            log.info(
                "incident %s last updated more than %d days ago, skipping",
                public_id,
                max_days_since_update,
            )
        elif not ai_summary_updated_at or changed_at > ai_summary_updated_at:
            log.info("incident %s needs AI summary updated", public_id)
            incidents_to_update.append(incident)
        else:
            log.info("incident %s summary up-to-date", public_id)

    return incidents_to_update


def load_prompt():
    with open("prompt.txt") as fp:
        return fp.read()


@click.group()
def cli():
    install(show_locals=True)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    logging.basicConfig(
        level=LOG_LEVEL,
        format="(%(threadName)14s) %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


@cli.command(help="generate summary for a single incident")
@click.option(
    "--id", required=True, help="incident public ID (example: ITN-2025-00096)"
)
def generate(id):
    console = Console()

    incident = get_incident(id)
    summary_md = summarize_incident(load_prompt(), incident, console)

    console.rule("AI-generated Summary")
    console.print(summary_md)


@cli.command(help="generate summaries for all incidents and update web-rca")
@click.option(
    "--since",
    "max_days_since_update",
    type=int,
    help="summarize only if updated_at is less than N days old",
)
def worker(max_days_since_update):
    incidents_to_update = _get_incidents_to_update(max_days_since_update)
    prompt = load_prompt()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

    errors = 0
    successes = 0
    total = 0

    future_to_incident = {}
    for incident in incidents_to_update:
        future = executor.submit(summarize_incident_and_update_webrca, prompt, incident)
        future_to_incident[future] = incident["incident_id"]
        total += 1

    for future in concurrent.futures.as_completed(future_to_incident):
        incident_id = future_to_incident[future]
        try:
            future.result()
        except Exception:
            log.exception("summarization failed for incident %s", incident_id)
            errors += 1
        else:
            log.info("summarization successful for incident %s", incident_id)
            successes += 1

    log.info(
        "incident summarization worker completed (%d total, %d errors, %d successes)",
        total,
        errors,
        successes,
    )


if __name__ == "__main__":
    cli()
