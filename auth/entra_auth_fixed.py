"""
auth/entra_auth.py – MSAL Client Credentials Flow for Microservices
=====================================================================

Fixed implementation for backend server-to-server authentication.

Features:
  • MSAL client credentials flow (no interactive login needed)
  • File-based token caching (replaces buggy Windows Credential Manager)
  • Graph API access with proper scopes
  • Automatic token refresh
  • Multi-tenant support
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import msal
import requests

logger = logging.getLogger("[ENTRA-AUTH]")

# ─────────────────────────────────────────────────────────────────────────────
# MSAL Configuration
# ─────────────────────────────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("SERVERMONITOR_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SERVERMONITOR_CLIENT_SECRET", "").strip()
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "common").strip()

GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]  # For Graph API
SHAREPOINT_SCOPES = ["https://graph.microsoft.com/.default"]  # Same scopes

# Token cache file (machine-bound)
TOKEN_CACHE_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    ".token_cache"
)


def _ensure_cache_dir():
    """Create cache directory if needed."""
    Path(TOKEN_CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)


def _load_token_cache() -> msal.SerializableTokenCache:
    """Load token cache from file (not Windows Credential Manager)."""
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, 'r') as f:
                cache.deserialize(f.read())
        except Exception as e:
            logger.warning(f"Token cache load failed: {e}. Starting fresh.")
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache):
    """Save token cache to file."""
    try:
        _ensure_cache_dir()
        if cache.has_state_changed:
            with open(TOKEN_CACHE_FILE, 'w') as f:
                f.write(cache.serialize())
    except Exception as e:
        logger.warning(f"Token cache save failed (non-blocking): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT CREDENTIALS FLOW (Backend Services)
# ─────────────────────────────────────────────────────────────────────────────

def get_valid_token(
    scopes: Optional[list] = None,
    tenant_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Dict:
    """
    Acquire access token using client credentials flow.
    
    Args:
        scopes: List of scopes (defaults to Graph API scopes)
        tenant_id: Azure tenant ID (defaults to configured TENANT_ID)
        client_secret: Client secret (defaults to env var)
    
    Returns:
        Dict with keys: access_token, token_type, expires_in, tenant_id
        Raises: Exception if token acquisition fails
    """
    if not CLIENT_ID or not (client_secret or CLIENT_SECRET):
        raise ValueError(
            "Missing CLIENT_ID or CLIENT_SECRET. "
            "Set SERVERMONITOR_CLIENT_ID and SERVERMONITOR_CLIENT_SECRET env vars."
        )
    
    secret = (client_secret or CLIENT_SECRET).strip()
    tid = (tenant_id or TENANT_ID or "common").strip()
    scopes_to_use = scopes or GRAPH_SCOPES
    
    authority = f"https://login.microsoftonline.com/{tid}"
    
    # Create MSAL app with file-based cache
    cache = _load_token_cache()
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=secret,
        authority=authority,
        token_cache=cache
    )
    
    # Try to get token from cache first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes_to_use, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            tenant = result.get("id_token_claims", {}).get("tid", tid)
            logger.info(f"✓ Token acquired via cache (tenant: {tenant})")
            return {
                "access_token": result["access_token"],
                "token_type": result.get("token_type", "Bearer"),
                "expires_in": result.get("expires_in", 3600),
                "tenant_id": tenant,
            }
    
    # Fall back to token endpoint
    try:
        result = app.acquire_token_for_client(scopes=scopes_to_use)
        if "access_token" in result:
            _save_token_cache(cache)
            tenant = result.get("id_token_claims", {}).get("tid", tid)
            logger.info(f"✓ Token acquired via client credentials (tenant: {tenant})")
            return {
                "access_token": result["access_token"],
                "token_type": result.get("token_type", "Bearer"),
                "expires_in": result.get("expires_in", 3600),
                "tenant_id": tenant,
            }
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise Exception(f"Token acquisition failed: {error}")
    except Exception as e:
        logger.error(f"MSAL error: {e}")
        raise


def get_silent_token(
    scopes: Optional[list] = None,
    tenant_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Optional[Dict]:
    """
    Try to get token from cache only (no token endpoint call).
    Returns None if cache miss (doesn't block waiting for interactive login).
    """
    secret = (client_secret or CLIENT_SECRET).strip()
    tid = (tenant_id or TENANT_ID or "common").strip()
    scopes_to_use = scopes or GRAPH_SCOPES
    
    authority = f"https://login.microsoftonline.com/{tid}"
    cache = _load_token_cache()
    
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=secret,
        authority=authority,
        token_cache=cache
    )
    
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes_to_use, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            return {
                "access_token": result["access_token"],
                "token_type": result.get("token_type", "Bearer"),
                "expires_in": result.get("expires_in", 3600),
                "tenant_id": tid,
            }
    return None
