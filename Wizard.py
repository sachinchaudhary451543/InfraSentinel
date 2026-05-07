#!/usr/bin/env python3
"""
installer/wizard.py
===================
First-time setup wizard for ServerMonitor.

Run as:
    python installer/wizard.py

What it does:
    1. Collects all configuration interactively (secrets via getpass, never echoed)
    2. Validates SharePoint connectivity before saving
    3. Writes non-secret settings to config.json
    4. Encrypts secrets into config.secrets.enc (machine-bound, no key file)
    5. Detects existing config and offers to update individual sections

Re-run at any time to update credentials. Existing settings are shown as
defaults so you only need to retype what changed.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Ensure project root is on the path so auth imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auth.multi_tenant_auth import (
    encrypt_config,
    decrypt_config,
)

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

BOLD  = "\033[1m"
DIM   = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"

def _h(text: str) -> str:
    """Section header."""
    return f"\n{BOLD}{'─' * 60}\n  {text}\n{'─' * 60}{RESET}\n"

def _ok(msg: str): print(f"  {GREEN}✓{RESET}  {msg}")
def _warn(msg: str): print(f"  {YELLOW}!{RESET}  {msg}")
def _err(msg: str): print(f"  {RED}✗{RESET}  {msg}")

def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    """Prompt the user for input. Shows masked default for secrets."""
    if default and not secret:
        full_prompt = f"  {prompt} [{default}]: "
    elif default and secret:
        full_prompt = f"  {prompt} [{'*' * min(len(default), 8)}]: "
    else:
        full_prompt = f"  {prompt}: "

    if secret:
        val = getpass.getpass(full_prompt)
    else:
        val = input(full_prompt).strip()

    return val if val else default

def _ask_bool(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    ans = input(f"  {prompt} [{yn}]: ").strip().lower()
    if not ans:
        return default
    return ans.startswith("y")

def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"  {prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            _err("Please enter a whole number.")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_sharepoint(site_url: str, client_id: str, client_secret: str) -> bool:
    """Attempt a real connection to SharePoint and return True on success."""
    print(f"\n  Connecting to SharePoint...", end="", flush=True)
    try:
        from office365.sharepoint.client_context import ClientContext
        from office365.runtime.auth.client_credential import ClientCredential
        ctx = ClientContext(site_url).with_credentials(
            ClientCredential(client_id, client_secret)
        )
        web = ctx.web
        ctx.load(web)
        ctx.execute_query()
        print(f"  {GREEN}connected{RESET} ({web.properties.get('Title', site_url)})")
        return True
    except ImportError:
        _warn("office365-rest-python-client not installed — skipping live validation.")
        return True   # can't validate, assume ok
    except Exception as exc:
        print()
        _err(f"Connection failed: {exc}")
        return False

# ---------------------------------------------------------------------------
# Section collectors
# ---------------------------------------------------------------------------

def _collect_sharepoint(existing_secrets: dict) -> dict:
    """Return updated sharepoint_credentials dict."""
    print(_h("SharePoint Credentials"))
    ex = existing_secrets.get("sharepoint_credentials", {})

    print(f"  {DIM}These are your Azure AD app registration values.{RESET}")
    print(f"  {DIM}Never commit these — they are stored encrypted on this machine.{RESET}\n")

    site_url      = _ask("SharePoint site URL", ex.get("site_url", ""))
    client_id     = _ask("Azure AD Client ID",  ex.get("client_id", ""), secret=False)
    client_secret = _ask("Azure AD Client Secret", ex.get("client_secret", ""), secret=True)
    tenant_id     = _ask("Azure AD Tenant ID",  ex.get("tenant_id", ""), secret=False)

    if not all([site_url, client_id, client_secret, tenant_id]):
        _warn("Some fields are empty — SharePoint integration will not work until all are provided.")
        validate = False
    else:
        validate = _ask_bool("Test connection now?", default=True)

    if validate:
        ok = _validate_sharepoint(site_url, client_id, client_secret)
        if not ok:
            if not _ask_bool("Save anyway?", default=False):
                _warn("SharePoint credentials not saved.")
                return ex   # return unchanged

    return {
        "site_url":      site_url,
        "client_id":     client_id,
        "client_secret": client_secret,
        "tenant_id":     tenant_id,
    }


def _collect_servers(existing_plain: dict) -> dict:
    """Return updated servers dict {hostname: [drive_letters]}."""
    print(_h("Monitored Servers"))
    ex = existing_plain.get("servers", {})

    print(f"  {DIM}Enter servers to monitor. Press Enter with empty hostname to finish.{RESET}")
    if ex:
        print(f"  {DIM}Current servers: {', '.join(ex.keys())}{RESET}")
        if not _ask_bool("Edit server list?", default=False):
            return ex

    servers: dict[str, list[str]] = {}
    while True:
        hostname = _ask("  Server hostname (blank to finish)", "").strip()
        if not hostname:
            break
        drives_raw = _ask(f"  Drive letters for {hostname} (comma-separated, blank=all)", "")
        drives = [d.strip().rstrip(":").upper() + ":" for d in drives_raw.split(",") if d.strip()]
        servers[hostname] = drives
        _ok(f"Added {hostname} → {drives or 'all drives'}")

    if not servers and ex:
        _warn("No servers entered — keeping existing list.")
        return ex
    if not servers:
        _warn("No servers configured. Add them later in config.json.")
    return servers


def _collect_schedule(existing_plain: dict) -> int:
    """Return collection interval in minutes."""
    print(_h("Collection Schedule"))
    current = existing_plain.get("interval_minutes", 60)
    return _ask_int("Collection interval (minutes)", current)


def _collect_flags(existing_plain: dict) -> dict:
    """Return updated operational flags."""
    print(_h("Agent Settings"))
    return {
        "agent_enabled":     _ask_bool("Enable agent?",              existing_plain.get("agent_enabled", True)),
        "sharepoint_enabled": _ask_bool("Enable SharePoint upload?", existing_plain.get("sharepoint_enabled", True)),
    }


# ---------------------------------------------------------------------------
# .gitignore guard
# ---------------------------------------------------------------------------

def _ensure_gitignore():
    """Add config.secrets.enc to .gitignore if not already present."""
    gitignore = ROOT / ".gitignore"
    entries = [
        "config.secrets.enc",
        "config.key",
        "config.json.bak",
        "storedCred.xml",
    ]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
    else:
        existing = ""

    to_add = [e for e in entries if e not in existing]
    if to_add:
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n# ServerMonitor — never commit secrets\n")
            for e in to_add:
                f.write(f"{e}\n")
        _ok(f".gitignore updated: {to_add}")


# ---------------------------------------------------------------------------
# Migration notice
# ---------------------------------------------------------------------------

def _check_legacy():
    legacy_key = ROOT / "config.key"
    if legacy_key.exists():
        print()
        _warn("Found legacy config.key. It will be migrated and deleted automatically.")
        _warn("After setup completes, delete config.key from your git history:")
        print(f"\n  {DIM}git filter-repo --path config.key --invert-paths{RESET}")
        print(f"  {DIM}git filter-repo --path config.json.bak --invert-paths{RESET}")
        print(f"  {DIM}git filter-repo --path storedCred.xml --invert-paths{RESET}\n")


# ---------------------------------------------------------------------------
# Main wizard flow
# ---------------------------------------------------------------------------

def run_wizard():
    print(f"\n{BOLD}ServerMonitor — Setup Wizard{RESET}")
    print(f"{DIM}Secrets are encrypted with a key derived from this machine's identity.")
    print(f"They cannot be decrypted on a different host.{RESET}")

    _check_legacy()

    # Load existing config if present (migration runs inside decrypt_config)
    try:
        existing_config  = decrypt_config() or {}
        existing_plain   = {k: v for k, v in existing_config.items()
                           if k not in ("sharepoint_credentials",)}
        existing_secrets = {k: v for k, v in existing_config.items()
                           if k in ("sharepoint_credentials",)}
    except Exception as exc:
        _warn(f"Could not read existing config: {exc}")
        existing_plain, existing_secrets = {}, {}

    is_update = bool(existing_plain or existing_secrets)
    if is_update:
        print(f"\n  {YELLOW}Existing configuration found.{RESET}")
        print(f"  Existing values shown as defaults — press Enter to keep them.\n")

    # Collect each section
    sp_creds  = _collect_sharepoint(existing_secrets)
    servers   = _collect_servers(existing_plain)
    interval  = _collect_schedule(existing_plain)
    flags     = _collect_flags(existing_plain)

    # Build final dicts
    new_plain = {
        "servers":          servers,
        "interval_minutes": interval,
        **flags,
        # Preserve any other plain keys that were already there
        **{k: v for k, v in existing_plain.items()
           if k not in ("servers", "interval_minutes", "agent_enabled", "sharepoint_enabled")},
    }
    new_secrets = {
        "sharepoint_credentials": sp_creds,
        # Preserve any other secrets already stored
        **{k: v for k, v in existing_secrets.items() if k != "sharepoint_credentials"},
    }

    # Preview
    print(_h("Summary"))
    print(f"  Servers:           {list(servers.keys()) or '(none)'}")
    print(f"  Interval:          {interval} minutes")
    print(f"  Agent enabled:     {flags['agent_enabled']}")
    print(f"  SharePoint enabled:{flags['sharepoint_enabled']}")
    print(f"  SP site URL:       {sp_creds.get('site_url', '(not set)')}")
    print(f"  SP client ID:      {sp_creds.get('client_id', '(not set)')}")
    print(f"  SP client secret:  {'(set)' if sp_creds.get('client_secret') else '(not set)'}")
    print()

    if not _ask_bool("Save this configuration?", default=True):
        _warn("Cancelled — nothing saved.")
        sys.exit(0)

    # Save
    try:
        encrypt_config({**new_plain, **new_secrets})
        _ensure_gitignore()
        print()
        _ok("config.json written (non-secret settings)")
        _ok("config.secrets.enc written (encrypted, machine-bound)")
        _ok(f"No key file created — key is derived from this machine's identity")
        print()
        print(f"  {BOLD}Setup complete.{RESET} Run 'python main.py' to start the agent.")
        print()
    except Exception as exc:
        _err(f"Failed to save config: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    run_wizard()