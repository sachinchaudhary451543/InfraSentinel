"""
core/provisioning.py
====================
ISV-grade SharePoint Provisioning Engine for ServerMonitor.

Public API:
    ensure_list(ctx, list_name)                 -> bool
    ensure_columns(ctx, list_name, columns)     -> list[str]  (names of added columns)
    run_provisioning(config)                    -> ProvisioningResult

Design rules (enforced, not just documented):
    - NEVER drops or recreates an existing list
    - NEVER modifies an existing column's type or settings
    - NEVER touches schema at runtime during normal upload cycles
    - Only adds what is missing; skips what already exists
    - Schema source of truth: scripts.database.setup_sharepoint_schema.REQUIRED_LISTS

run_provisioning() is called once at agent startup (before the scheduler).
It provisions everything that is missing and returns a result object that
the uploader consults to know which lists are ready.

The result is cached in module state so repeated calls within the same
process are free (no extra SP round-trips).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("Provisioning")

# ---------------------------------------------------------------------------
# Schema source of truth — imported, never redefined here
# ---------------------------------------------------------------------------

from scripts.database.setup_sharepoint_schema import (
    REQUIRED_LISTS,
    COLUMN_TYPES,
    FIELD_TYPE_TEXT,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_DATETIME,
    INDEXED_COLUMNS,
)

# ---------------------------------------------------------------------------
# SP column limit error code (Microsoft)
# ---------------------------------------------------------------------------

_SP_COLUMN_LIMIT_CODE = "-2130246218"

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProvisioningResult:
    """
    Returned by run_provisioning(). Consumed by the uploader and retry layer.

    ready_lists:   set of list names that exist and have all required columns
    missing_lists: set of list names that could not be created/verified
    added_columns: {list_name: [col_names]} — columns created during this run
    errors:        {list_name: error_message} — non-fatal errors per list
    provisioned:   True if at least one list is fully ready
    """
    ready_lists:   set[str]             = field(default_factory=set)
    missing_lists: set[str]             = field(default_factory=set)
    added_columns: dict[str, list[str]] = field(default_factory=dict)
    errors:        dict[str, str]       = field(default_factory=dict)

    @property
    def provisioned(self) -> bool:
        return bool(self.ready_lists)

    def is_ready(self, list_name: str) -> bool:
        return list_name in self.ready_lists

    def summary(self) -> str:
        lines = [
            f"Provisioning complete.",
            f"  Ready:   {sorted(self.ready_lists) or 'none'}",
            f"  Missing: {sorted(self.missing_lists) or 'none'}",
        ]
        for lst, cols in self.added_columns.items():
            lines.append(f"  Created columns on '{lst}': {cols}")
        for lst, err in self.errors.items():
            lines.append(f"  Error on '{lst}': {err}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Process-level cache — avoid re-provisioning on every scheduled cycle
# ---------------------------------------------------------------------------

_cached_result: ProvisioningResult | None = None


def invalidate_cache():
    """Force re-provisioning on the next run_provisioning() call."""
    global _cached_result
    _cached_result = None


# ---------------------------------------------------------------------------
# SP client context helper
# ---------------------------------------------------------------------------

def _build_ctx(site_url: str, client_id: str, client_secret: str):
    from office365.sharepoint.client_context import ClientContext
    from office365.runtime.auth.client_credential import ClientCredential
    return ClientContext(site_url).with_credentials(
        ClientCredential(client_id, client_secret)
    )


# ---------------------------------------------------------------------------
# Low-level SP helpers (retried internally)
# ---------------------------------------------------------------------------

def _sp_get_field_names(ctx, list_name: str) -> set[str]:
    """
    Return the set of field InternalNames and Titles for a list.
    Returns empty set if the list does not exist or cannot be read.
    """
    try:
        sp_list = ctx.web.lists.get_by_title(list_name)
        sp_list.get().execute_query()           # raises if list missing
        sp_list.fields.get().execute_query()
        internal = {f.properties.get("InternalName", "") for f in sp_list.fields}
        display  = {f.properties.get("Title", "")         for f in sp_list.fields}
        return internal | display
    except Exception:
        return set()


def _sp_list_exists(ctx, list_name: str) -> bool:
    """Return True if the list exists and is accessible."""
    try:
        sp_list = ctx.web.lists.get_by_title(list_name)
        sp_list.get().execute_query()
        return True
    except Exception:
        return False


def _sp_create_list(ctx, list_name: str) -> bool:
    """
    Create a generic SharePoint list (BaseTemplate=100).
    Returns True on success.
    ONLY called when the list does not exist.
    """
    try:
        from office365.sharepoint.lists.creation_information import ListCreationInformation
        list_info = ListCreationInformation()
        list_info.Title = list_name
        list_info.BaseTemplate = 100
        ctx.web.lists.add(list_info).execute_query()
        log.info("Created list '%s'.", list_name)
        return True
    except Exception as exc:
        log.error("Failed to create list '%s': %s", list_name, exc)
        return False


def _sp_add_column(ctx, list_name: str, col_name: str) -> tuple[bool, str]:
    """
    Add a single column to an existing list.
    Returns (success, error_message).
    ONLY called when the column does not already exist.
    """
    field_type = COLUMN_TYPES.get(col_name, FIELD_TYPE_TEXT)
    try:
        sp_list = ctx.web.lists.get_by_title(list_name)
        # Build schema XML — more reliable than the REST JSON endpoint
        # for non-default field types
        type_map = {
            FIELD_TYPE_TEXT:     "Text",
            FIELD_TYPE_NUMBER:   "Number",
            FIELD_TYPE_DATETIME: "DateTime",
        }
        type_str = type_map.get(field_type, "Text")
        schema_xml = (
            f'<Field Type="{type_str}" '
            f'DisplayName="{col_name}" '
            f'Name="{col_name}" '
            f'StaticName="{col_name}"/>'
        )
        sp_list.fields.create_field_as_xml(schema_xml).execute_query()
        log.info("  Added column '%s' (%s) to '%s'.", col_name, type_str, list_name)
        return True, ""
    except Exception as exc:
        err_str = str(exc)
        if _SP_COLUMN_LIMIT_CODE in err_str:
            msg = (
                f"SharePoint column limit reached on '{list_name}'. "
                f"Delete unused columns in the SharePoint UI, then re-run provisioning."
            )
            log.error(msg)
            return False, msg
        log.error("Failed to add column '%s' to '%s': %s", col_name, list_name, exc)
        return False, err_str


def _sp_ensure_index(ctx, list_name: str, col_name: str):
    """Set Indexed=True on a column if it is not already indexed."""
    try:
        sp_list = ctx.web.lists.get_by_title(list_name)
        field = sp_list.fields.get_by_internal_name_or_title(col_name)
        ctx.load(field)
        ctx.execute_query()
        if not field.properties.get("Indexed", False):
            field.set_property("Indexed", True)
            field.update()
            ctx.execute_query()
            log.info("  Indexed column '%s' on '%s'.", col_name, list_name)
    except Exception as exc:
        log.debug("Could not index '%s' on '%s': %s", col_name, list_name, exc)


# ---------------------------------------------------------------------------
# Public primitives
# ---------------------------------------------------------------------------

def ensure_list(ctx, list_name: str) -> bool:
    """
    Ensure the named SharePoint list exists.
    - If it already exists: returns True immediately (no-op).
    - If it does not exist: creates it and returns True on success.
    - Returns False only if creation fails.

    NEVER deletes or recreates an existing list.
    """
    if _sp_list_exists(ctx, list_name):
        log.debug("List '%s' already exists — skipping creation.", list_name)
        return True

    log.info("List '%s' not found — creating.", list_name)
    return _sp_create_list(ctx, list_name)


def ensure_columns(ctx, list_name: str, columns: list[str]) -> list[str]:
    """
    Ensure every column in `columns` exists on the named list.
    - Fetches current field names once per call.
    - Only adds columns that are absent; never modifies existing ones.
    - Returns a list of column names that were actually created this call.
    - On column-limit error, stops adding to that list and logs clearly.

    Args:
        ctx:       Authenticated ClientContext.
        list_name: SharePoint list title.
        columns:   List of column names that must exist (from REQUIRED_LISTS).

    Returns:
        List of column names added during this call (empty if all existed).
    """
    existing = _sp_get_field_names(ctx, list_name)
    if not existing:
        log.warning("Could not read fields for '%s' — skipping column check.", list_name)
        return []

    added = []
    for col in columns:
        if col in existing:
            log.debug("  Column '%s' already exists on '%s'.", col, list_name)
            continue

        ok, err = _sp_add_column(ctx, list_name, col)
        if ok:
            added.append(col)
        elif _SP_COLUMN_LIMIT_CODE in err:
            # Column limit hit — abort this list
            break

    # Index the key columns (best-effort, non-fatal)
    for idx_col in INDEXED_COLUMNS:
        if idx_col in columns:
            _sp_ensure_index(ctx, list_name, idx_col)

    return added


# ---------------------------------------------------------------------------
# Main provisioning run
# ---------------------------------------------------------------------------

def run_provisioning(config: dict) -> ProvisioningResult:
    """
    Provision all SharePoint lists and columns defined in REQUIRED_LISTS.
    Called once at agent startup, before the scheduler loop.

    - Reads credentials from config['sharepoint_credentials'].
    - Iterates REQUIRED_LISTS; for each list:
        1. ensure_list()   — create if missing, skip if exists
        2. ensure_columns() — add missing columns only
    - Caches the result for the process lifetime (invalidate_cache() resets).
    - Returns a ProvisioningResult that the uploader and retry layer consume.

    Non-fatal: if a list fails, provisioning continues with the others.
    If SharePoint is unreachable, all lists land in missing_lists and the
    agent continues without SP upload.
    """
    global _cached_result

    if _cached_result is not None:
        log.debug("Returning cached provisioning result.")
        return _cached_result

    result = ProvisioningResult()

    # Guard: SP disabled or no credentials
    if not config.get("sharepoint_enabled", True):
        log.info("SharePoint disabled — skipping provisioning.")
        _cached_result = result
        return result

    creds = config.get("sharepoint_credentials", {})
    site_url      = creds.get("site_url", "")
    client_id     = creds.get("client_id", "")
    client_secret = creds.get("client_secret", "")

    if not all([site_url, client_id, client_secret]):
        log.warning("SharePoint credentials incomplete — skipping provisioning.")
        result.errors["_global"] = "Credentials incomplete. Run onboarding."
        _cached_result = result
        return result

    # Build context — test connectivity first
    try:
        ctx = _build_ctx(site_url, client_id, client_secret)
        ctx.web.get().execute_query()
        log.info("SharePoint connection verified: %s", site_url)
    except Exception as exc:
        log.error("Cannot connect to SharePoint: %s", exc)
        result.errors["_global"] = f"Connection failed: {exc}"
        _cached_result = result
        return result

    # Provision each list
    for list_name, columns in REQUIRED_LISTS.items():
        log.info("Provisioning list '%s' ...", list_name)

        # Step 1: ensure list exists
        list_ok = ensure_list(ctx, list_name)
        if not list_ok:
            result.missing_lists.add(list_name)
            result.errors[list_name] = "List creation failed."
            log.error("Skipping columns for '%s' — list unavailable.", list_name)
            continue

        # Step 2: ensure all required columns exist
        try:
            added = ensure_columns(ctx, list_name, columns)
            if added:
                result.added_columns[list_name] = added
        except Exception as exc:
            result.errors[list_name] = f"Column provisioning error: {exc}"
            log.error("Column error on '%s': %s", list_name, exc)
            # Still mark as ready if the list exists — partial columns
            # are better than marking it entirely missing
            result.ready_lists.add(list_name)
            continue

        result.ready_lists.add(list_name)
        log.info("List '%s' is ready.", list_name)

    log.info(result.summary())
    _cached_result = result
    return result