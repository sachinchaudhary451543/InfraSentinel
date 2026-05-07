"""
core/onboarding.py
==================
ISV onboarding flow for ServerMonitor.

Entry point: run_onboarding_if_needed(config: dict) -> dict
  - Checks whether SharePoint credentials are present and valid in config
  - If missing: collects them interactively and saves via encrypt_config
  - Returns the updated config dict (no-op if credentials already present)

Called from main() before the scheduler starts. Never blocks startup if
SharePoint is disabled — only gates when sharepoint_enabled=True and
credentials are absent or incomplete.

Credential collection uses getpass for the client secret so it is never
echoed to the terminal or written to any log.
"""

from __future__ import annotations

import getpass
import logging
import sys
from typing import Any

log = logging.getLogger("Onboarding")

# Fields required for a valid SharePoint credential set
_REQUIRED_SP_FIELDS = ("site_url", "client_id", "client_secret", "tenant_id")


# ---------------------------------------------------------------------------
# Credential completeness check
# ---------------------------------------------------------------------------

def _sp_creds_present(config: dict) -> bool:
    """
    Return True if all required SharePoint credential fields are non-empty.
    Does NOT test connectivity — that is done by the provisioning engine.
    """
    creds = config.get("sharepoint_credentials", {})
    if not creds:
        return False
    return all(bool(creds.get(f, "").strip()) for f in _REQUIRED_SP_FIELDS)


# ---------------------------------------------------------------------------
# Interactive credential collection
# ---------------------------------------------------------------------------

def _print_banner():
    sep = "─" * 62
    print(f"\n{sep}")
    print("  ServerMonitor — SharePoint Onboarding")
    print(f"  SharePoint credentials are required to enable data upload.")
    print(f"  These will be encrypted and stored on this machine only.")
    print(f"{sep}\n")


def _collect_credentials(existing: dict) -> dict:
    """
    Interactively collect SharePoint credentials.
    Existing values shown as defaults; press Enter to keep them.
    client_secret is collected via getpass (not echoed).
    Returns a credentials dict with all four required fields.
    """
    def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
        if default and not secret:
            full = f"  {prompt} [{default}]: "
        elif default and secret:
            masked = "*" * min(len(default), 8)
            full = f"  {prompt} [{masked}]: "
        else:
            full = f"  {prompt}: "

        if secret:
            val = getpass.getpass(full)
        else:
            try:
                val = input(full).strip()
            except EOFError:
                # Non-interactive environment (e.g. service startup)
                return default

        return val if val else default

    print("  Tip: These values come from your Azure AD App Registration.\n")

    site_url      = _ask("SharePoint site URL",    existing.get("site_url", ""))
    tenant_id     = _ask("Azure AD Tenant ID",     existing.get("tenant_id", ""))
    client_id     = _ask("Azure AD Client ID",     existing.get("client_id", ""))
    client_secret = _ask("Azure AD Client Secret", existing.get("client_secret", ""), secret=True)

    return {
        "site_url":      site_url.rstrip("/"),
        "tenant_id":     tenant_id,
        "client_id":     client_id,
        "client_secret": client_secret,
    }


def _validate_and_confirm(creds: dict) -> bool:
    """Print a summary and ask for confirmation. Returns True if accepted."""
    print("\n  Credentials entered:")
    print(f"    site_url:      {creds['site_url']}")
    print(f"    tenant_id:     {creds['tenant_id']}")
    print(f"    client_id:     {creds['client_id']}")
    print(f"    client_secret: {'(set)' if creds['client_secret'] else '(empty)'}\n")

    missing = [f for f in _REQUIRED_SP_FIELDS if not creds.get(f, "").strip()]
    if missing:
        log.warning("The following fields are still empty: %s", missing)
        print(f"  Warning: fields still empty: {missing}")

    try:
        ans = input("  Save these credentials? [Y/n]: ").strip().lower()
    except EOFError:
        ans = "y"   # non-interactive: accept automatically

    return ans in ("", "y", "yes")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_onboarding_if_needed(config: dict) -> dict:
    """
    Check whether SharePoint credentials are present in config.
    If not, and SharePoint is enabled, run the interactive collection flow.
    Saves credentials via encrypt_config and returns the updated config.

    Args:
        config: The full merged config dict from load_config().

    Returns:
        Updated config dict. If onboarding was skipped or user cancelled,
        the original dict is returned unchanged (SP upload will simply be
        skipped by the uploader due to missing creds).
    """
    # If SP is disabled, nothing to do
    if not config.get("sharepoint_enabled", True):
        log.debug("SharePoint disabled — skipping onboarding check.")
        return config

    # If creds are already complete, nothing to do
    if _sp_creds_present(config):
        log.debug("SharePoint credentials present — skipping onboarding.")
        return config

    # Credentials are missing — start interactive flow
    log.info("SharePoint credentials missing. Starting onboarding flow.")
    _print_banner()

    max_attempts = 3
    existing = config.get("sharepoint_credentials", {})

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            print(f"\n  Attempt {attempt} of {max_attempts}.\n")

        creds = _collect_credentials(existing)

        if not _validate_and_confirm(creds):
            print("\n  Onboarding cancelled. SharePoint upload will be skipped this session.")
            log.warning("Onboarding cancelled by user.")
            return config

        # Merge into config and persist via the secure storage layer
        config["sharepoint_credentials"] = creds
        try:
            from auth.multi_tenant_auth import encrypt_config
            encrypt_config(config)
            print("\n  Credentials saved (encrypted, machine-bound).")
            log.info("SharePoint credentials saved successfully during onboarding.")
            return config
        except Exception as exc:
            log.error("Failed to save credentials: %s", exc)
            print(f"\n  Error saving credentials: {exc}")
            if attempt < max_attempts:
                print("  Please try again.")
                existing = creds   # carry forward what was typed
            else:
                print("  Could not save credentials. SharePoint upload will be skipped.")

    return config