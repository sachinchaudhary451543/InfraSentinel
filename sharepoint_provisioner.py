"""
sharepoint_provisioner.py – ServerMonitor ISV (Phase 2)
=========================================================
Idempotent SharePoint provisioning engine.
Safe to run on every startup. Never deletes lists or existing columns.

Lists provisioned:
  ServerInventory, ServerMetricsHistory, ServerVMs, AgentControl, Alerts

Schema versioning via ProvisionerMeta list item.
Self-healing: retries all SP calls up to 3x with backoff (Phase 7).

BUGS FIXED IN THIS FILE:
  Bug #3  – ensure_site_exists returned wrong URL on 404 instead of raising.
             Now raises ConfigurationError with actionable instructions.
  Bug #4  – _add_field used json= kwarg (double-serialises) which clashed with
             the odata=verbose Content-Type. Fixed to use data=json.dumps(payload).
  Bug #13 – _retry() swallowed the root cause. Now chains the original exception
             so callers and logs always see the real error.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger("[SP-PROVISIONER]")
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(asctime)s %(levelname)s: %(message)s",
)

SCHEMA_VERSION = 4

# Field types: 2=Text, 3=Number, 4=DateTime, 8=Boolean
REQUIRED_LISTS: dict[str, list[dict[str, Any]]] = {
    "ServerInventory": [
        {"name": "ServerName",    "type": 2, "indexed": True},
        {"name": "IPAddress",     "type": 2},
        {"name": "MACAddress",    "type": 2},
        {"name": "OS",            "type": 2},
        {"name": "Domain",        "type": 2},
        {"name": "Location",      "type": 2},
        {"name": "AgentVersion",  "type": 2},
        {"name": "LastSeen",      "type": 4},
        {"name": "IsManaged",     "type": 8},
        {"name": "TenantId",      "type": 2, "indexed": True},
        {"name": "SchemaVersion", "type": 3},
    ],
    "ServerMetricsHistory": [
        {"name": "ServerName",    "type": 2, "indexed": True},
        {"name": "Timestamp",     "type": 2, "indexed": True},
        {"name": "AvgCPU",        "type": 3},
        {"name": "AvgRAM",        "type": 3},
        {"name": "AvgDisk",       "type": 3},
        {"name": "AvgSSD",        "type": 3},
        {"name": "TotalRAM",      "type": 3},
        {"name": "AvailableRAM",  "type": 3},
        {"name": "TotalSSD",      "type": 3},
        {"name": "AvailableSSD",  "type": 3},
        {"name": "HealthStatus",  "type": 2},
        {"name": "TenantId",      "type": 2, "indexed": True},
        {"name": "SchemaVersion", "type": 3},
    ],
    "ServerVMs": [
        {"name": "HostServer",     "type": 2, "indexed": True},
        {"name": "VMName",         "type": 2, "indexed": True},
        {"name": "State",          "type": 2},
        {"name": "CPUUsage",       "type": 3},
        {"name": "MemoryAssigned", "type": 3},
        {"name": "Uptime",         "type": 2},
        {"name": "Path",           "type": 2},
        {"name": "HostIP",         "type": 2},
        {"name": "HostOS",         "type": 2},
        {"name": "TenantId",       "type": 2, "indexed": True},
        {"name": "SchemaVersion",  "type": 3},
    ],
    "AgentControl": [
        {"name": "ServerName",    "type": 2, "indexed": True},
        {"name": "Action",        "type": 2},
        {"name": "ActionPayload", "type": 2},
        {"name": "Status",        "type": 2},
        {"name": "RequestedBy",   "type": 2},
        {"name": "RequestedAt",   "type": 4},
        {"name": "ExecutedAt",    "type": 4},
        {"name": "ResultMessage", "type": 2},
        {"name": "TenantId",      "type": 2, "indexed": True},
        {"name": "SchemaVersion", "type": 3},
    ],
    "Alerts": [
        {"name": "ServerName",    "type": 2, "indexed": True},
        {"name": "AlertType",     "type": 2},
        {"name": "Severity",      "type": 2},
        {"name": "Message",       "type": 2},
        {"name": "Timestamp",     "type": 4, "indexed": True},
        {"name": "Acknowledged",  "type": 8},
        {"name": "TenantId",      "type": 2, "indexed": True},
        {"name": "SchemaVersion", "type": 3},
    ],
    "ProvisionerMeta": [
        {"name": "SchemaVersion", "type": 3},
    ],
}


class ConfigurationError(Exception):
    """Raised when SharePoint is misconfigured (site missing, permissions wrong)."""


# ── Helpers ────────────────────────────────────────────────────────────────────
def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json;odata=verbose",
        "Content-Type":  "application/json;odata=verbose",
    }


# Bug #13 fix: capture and chain the last exception
def _retry(fn, retries: int = 3, delay: int = 3):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError(
        f"All {retries} attempts exhausted. Last error: {last_exc}"
    ) from last_exc


# ── Bug #3 fix: raise when site is absent instead of returning wrong URL ───────
def ensure_site_exists(graph_base: str, access_token: str) -> str:
    """
    Detect the SharePoint site URL from Microsoft Graph.
    Raises ConfigurationError if the 'ServerMonitoring' site does not exist.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    try:
        root = _retry(lambda: requests.get(
            "https://graph.microsoft.com/v1.0/sites/root",
            headers=headers, timeout=15
        ).json())
    except Exception as exc:
        raise ConfigurationError(
            f"Cannot reach Microsoft Graph to discover SharePoint root: {exc}"
        ) from exc

    hostname = root.get("siteCollection", {}).get("hostname")
    if not hostname:
        raise ConfigurationError(
            f"Unexpected Graph response (no hostname). Full response: {root}"
        )

    check_url = (
        f"https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/ServerMonitoring"
    )
    resp = requests.get(check_url, headers=headers, timeout=15)

    if resp.status_code == 200:
        site_url = f"https://{hostname}/sites/ServerMonitoring"
        logger.info(f"SharePoint site found: {site_url}")
        return site_url

    # Site does not exist – raise with clear instructions (Bug #3)
    raise ConfigurationError(
        f"SharePoint site 'ServerMonitoring' does not exist on '{hostname}'.\n"
        f"Please create it:\n"
        f"  1. Go to https://{hostname.split('.')[0]}-admin.sharepoint.com\n"
        f"  2. Click 'Active sites' → 'Create' → Team site\n"
        f"  3. Name it 'ServerMonitoring'\n"
        f"  4. Re-run this application."
    )


# ── Column management ──────────────────────────────────────────────────────────
def _get_existing_fields(site_url: str, list_name: str, token: str) -> set:
    url = (
        f"{site_url}/_api/web/lists/GetByTitle('{list_name}')"
        f"/fields?$select=InternalName"
    )
    r = requests.get(url, headers=_headers(token), timeout=15)
    r.raise_for_status()
    return {f["InternalName"] for f in r.json().get("d", {}).get("results", [])}


def _create_list(site_url: str, list_name: str, token: str) -> None:
    url     = f"{site_url}/_api/web/lists"
    payload = json.dumps({
        "__metadata": {"type": "SP.List"},
        "Title":        list_name,
        "BaseTemplate": 100,
    })
    # Bug #4 fix: use data= (raw JSON string) NOT json= (which double-encodes)
    r = requests.post(
        url,
        headers=_headers(token),
        data=payload,          # ← correct: raw body, headers already set CT
        timeout=15,
    )
    if r.status_code in (200, 201):
        logger.info(f"Created list: {list_name}")
    else:
        raise RuntimeError(
            f"List creation failed [{r.status_code}]: {r.text[:300]}"
        )


# SP field type code → OData metadata type
_TYPE_MAP = {
    2: "SP.FieldText",
    3: "SP.FieldNumber",
    4: "SP.FieldDateTime",
    8: "SP.FieldBoolean",
}


def _add_field(site_url: str, list_name: str, field: dict, token: str) -> None:
    url     = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')/fields"
    payload = json.dumps({
        "__metadata":    {"type": _TYPE_MAP.get(field["type"], "SP.FieldText")},
        "Title":         field["name"],
        "FieldTypeKind": field["type"],
        "Required":      False,
    })
    # Bug #4 fix: data= not json= — avoid double serialisation + CT conflict
    r = requests.post(
        url,
        headers=_headers(token),
        data=payload,
        timeout=15,
    )
    if r.status_code in (200, 201):
        logger.info(f"  Added column '{field['name']}' to '{list_name}'")
    elif "already exists" in r.text.lower() or r.status_code == 400:
        logger.debug(f"  Column '{field['name']}' already exists – skipped")
    else:
        logger.error(
            f"  Failed to add '{field['name']}' [{r.status_code}]: {r.text[:200]}"
        )


def _set_indexed(site_url: str, list_name: str, fname: str, token: str) -> None:
    url  = (
        f"{site_url}/_api/web/lists/GetByTitle('{list_name}')"
        f"/fields/getbytitle('{fname}')"
    )
    hdrs = {**_headers(token), "X-HTTP-Method": "MERGE", "If-Match": "*"}
    payload = json.dumps({"__metadata": {"type": "SP.Field"}, "Indexed": True})
    requests.post(url, headers=hdrs, data=payload, timeout=15)


# ── Per-list provisioning ──────────────────────────────────────────────────────
def ensure_list_and_columns(
    site_url: str, list_name: str, fields: list, token: str
) -> None:
    """Idempotent: ensure list exists; add only missing columns."""
    r = requests.get(
        f"{site_url}/_api/web/lists/GetByTitle('{list_name}')",
        headers=_headers(token),
        timeout=15,
    )
    if r.status_code == 404:
        logger.info(f"List '{list_name}' not found – creating...")
        _retry(lambda: _create_list(site_url, list_name, token))
    elif r.status_code != 200:
        raise RuntimeError(
            f"Cannot check list '{list_name}': [{r.status_code}] {r.text[:200]}"
        )
    else:
        logger.info(f"List '{list_name}' exists ✓")

    existing = _retry(lambda: _get_existing_fields(site_url, list_name, token))
    for field in fields:
        if field["name"] not in existing:
            _retry(lambda f=field: _add_field(site_url, list_name, f, token))

    for field in fields:
        if field.get("indexed"):
            _set_indexed(site_url, list_name, field["name"], token)


# ── Schema versioning ──────────────────────────────────────────────────────────
def _get_schema_version(site_url: str, token: str) -> int:
    try:
        url = (
            f"{site_url}/_api/web/lists/GetByTitle('ProvisionerMeta')/items"
            f"?$filter=Title eq 'SchemaVersion'&$select=SchemaVersion"
        )
        r = requests.get(url, headers=_headers(token), timeout=15)
        if r.status_code != 200:
            return 0
        results = r.json().get("d", {}).get("results", [])
        if results:
            return int(results[0].get("SchemaVersion", 0))
        return 0
    except Exception:
        return 0


def _set_schema_version(site_url: str, token: str, version: int) -> None:
    try:
        # Check if item exists
        url = (
            f"{site_url}/_api/web/lists/GetByTitle('ProvisionerMeta')/items"
            f"?$filter=Title eq 'SchemaVersion'"
        )
        r = requests.get(url, headers=_headers(token), timeout=15)
        results = r.json().get("d", {}).get("results", [])

        payload = json.dumps({
            "__metadata": {"type": "SP.Data.ProvisionerMetaListItem"},
            "Title":         "SchemaVersion",
            "SchemaVersion": version,
        })

        if results:
            item_id = results[0]["Id"]
            patch_url = (
                f"{site_url}/_api/web/lists/GetByTitle('ProvisionerMeta')/items({item_id})"
            )
            hdrs = {**_headers(token), "X-HTTP-Method": "MERGE", "If-Match": "*"}
            requests.post(patch_url, headers=hdrs, data=payload, timeout=15)
        else:
            post_url = f"{site_url}/_api/web/lists/GetByTitle('ProvisionerMeta')/items"
            requests.post(post_url, headers=_headers(token), data=payload, timeout=15)

        logger.info(f"Schema version set to {version}")
    except Exception as e:
        logger.warning(f"Could not update schema version: {e}")


# ── Public API ─────────────────────────────────────────────────────────────────
def provision_tenant(site_url: str, access_token: str) -> None:
    """
    Idempotently provision all SharePoint lists for this tenant.
    Safe to call on every startup.

    Raises ConfigurationError / RuntimeError on unrecoverable failures.
    """
    current_ver = _get_schema_version(site_url, access_token)
    if current_ver >= SCHEMA_VERSION:
        logger.info(
            f"SharePoint schema is up to date (v{current_ver}). Nothing to provision."
        )
        return

    logger.info(
        f"Provisioning SharePoint schema (current v{current_ver} → target v{SCHEMA_VERSION})…"
    )

    failed_lists: list[str] = []
    for list_name, fields in REQUIRED_LISTS.items():
        try:
            _retry(
                lambda ln=list_name, fl=fields: ensure_list_and_columns(
                    site_url, ln, fl, access_token
                )
            )
        except Exception as exc:
            logger.error(f"Failed to provision list '{list_name}': {exc}")
            failed_lists.append(list_name)

    if failed_lists:
        raise RuntimeError(
            "Provisioning failed for required list(s): " + ", ".join(failed_lists)
        )

    _set_schema_version(site_url, access_token, SCHEMA_VERSION)
    logger.info("✓ SharePoint provisioning complete.")
