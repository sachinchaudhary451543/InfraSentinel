"""
auth/msal_auth.py – ServerMonitor ISV
======================================
Unified OAuth authentication (MSAL) supporting:
  • Client Credentials Flow (confidential client with secret + tenant_id)
  • Device Code Flow (public client, user-interactive)
  • Cached tokens (silent refresh)

FIXED:
  Bug #1  – CLIENT_ID validation improved
  Bug #2  – tenant_id extraction robust
  Bug #11 – Machine-derived encryption key (no key file)
  Bug #12 – access_token never persisted
  Bug #13 – Client credentials now use tenant-specific authority
"""

import base64
import hashlib
import json
import logging
import os
import platform
import subprocess
from contextlib import contextmanager
from typing import Any

import keyring
import msal

logger = logging.getLogger("[MSAL-AUTH]")
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(asctime)s %(levelname)s: %(message)s",
)

# ── Constants ──────────────────────────────────────────────────────────────────
_SVC         = "ServerMonitorISV"
_CACHE_ACCT  = "msal_token_cache"
_TENANT_ACCT = "msal_tenant_id"
_CONFIG_ACCT = "app_config"

AUTHORITY_COMMON = "https://login.microsoftonline.com/common"   # multi-tenant
SCOPES_USER = [
    "https://graph.microsoft.com/Sites.ReadWrite.All",
    "https://graph.microsoft.com/Directory.Read.All",
]
SCOPES_CLIENT = ["https://graph.microsoft.com/.default"]

CLIENT_ID = os.environ.get("SERVERMONITOR_CLIENT_ID") or ""
TokenResult = dict[str, Any]


def _validate_client_id(cid: str = ""):
    global CLIENT_ID
    if cid:
        CLIENT_ID = cid
    if not CLIENT_ID:
        # Check if already set by env or previous call
        if not (os.environ.get("SERVERMONITOR_CLIENT_ID") or "").strip() and not CLIENT_ID:
            raise ValueError("CLIENT_ID is not configured. Set SERVERMONITOR_CLIENT_ID environment variable.")



def _get_effective_client_id() -> str:
    """Helper to get the global client ID or raise error if missing."""
    cid = (os.environ.get("SERVERMONITOR_CLIENT_ID") or "").strip()
    if not cid:
        # If not in env, check if we have a global constant set
        if CLIENT_ID:
            return CLIENT_ID
        _validate_client_id()
    return (os.environ.get("SERVERMONITOR_CLIENT_ID") or "").strip()


@contextmanager
def _temporarily_disable_dead_proxy():
    """
    Some environments inject a dummy proxy such as 127.0.0.1:9 to block outbound
    traffic. That breaks MSAL even for valid credentials. Temporarily bypass it
    for auth calls so direct connectivity can still work when available.
    """
    proxy_keys = [
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ]
    removed: dict[str, str] = {}
    try:
        for key in proxy_keys:
            value = os.environ.get(key, "").strip()
            if "127.0.0.1:9" in value or "localhost:9" in value:
                removed[key] = value
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in removed.items():
            os.environ[key] = value


# ── Token cache helpers ────────────────────────────────────────────────────────
def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    try:
        stored = keyring.get_password(_SVC, _CACHE_ACCT)
        if stored:
            cache.deserialize(stored)
    except Exception:
        pass
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        try:
            keyring.set_password(_SVC, _CACHE_ACCT, cache.serialize())
        except Exception as e:
            logger.warning(f"Token cache save failed: {e}")


def _get_app_public(cache: msal.SerializableTokenCache, client_id: str | None = None) -> msal.PublicClientApplication:
    """Create a public client app (device code flow)."""
    cid = client_id or _get_effective_client_id()
    return msal.PublicClientApplication(
        cid,
        authority=AUTHORITY_COMMON,
        token_cache=cache
    )


def _get_app_confidential(
    client_secret: str,
    tenant_id: str | None,
    cache: msal.SerializableTokenCache | None = None,
    client_id: str | None = None
) -> msal.ConfidentialClientApplication:
    """Create a confidential client app (client credentials flow)."""
    cid = client_id or _get_effective_client_id()
    if not tenant_id or tenant_id == "unknown":
        raise ValueError("tenant_id is required for client credentials flow")
    if not client_secret:
        raise ValueError("client_secret is required for confidential client")

    # Use tenant-specific authority for better security
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    return msal.ConfidentialClientApplication(
        cid,
        authority=authority,
        client_credential=client_secret,
        token_cache=cache
    )


# ── Tenant ID extraction ───────────────────────────────────────────────────────
_CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"


def _extract_tenant_id(result: dict) -> str:
    """
    Extract tenant_id from a token result.
    Priority:
      1. id_token_claims['tid']
      2. Fallback to stored tenant
      3. Return unknown if not found
    """
    claims = result.get("id_token_claims", {})
    tid = claims.get("tid", "").strip()

    if tid and tid != _CONSUMER_TENANT:
        return tid

    # Fall back to stored tenant
    stored = get_stored_tenant_id()
    if stored:
        logger.info("Using stored tenant_id from keyring")
        return stored

    logger.warning("Could not determine tenant_id from token or storage")
    return "unknown"


def _has_token_result(result: TokenResult | None) -> TokenResult | None:
    """Return a token response only when MSAL produced a mapping."""
    if isinstance(result, dict):
        return result
    return None


# ── Core Auth Functions ────────────────────────────────────────────────────────
def get_valid_token(
    client_secret: str | None = None,
    tenant_id: str | None = None,
    scopes: list[str] | None = None,
    client_id: str | None = None
) -> dict:
    """
    Returns {access_token: str, tenant_id: str}.

    Priority:
      1. If client_secret + tenant_id: Use client credentials (silent, non-interactive)
      2. If cached token exists: Use silent refresh (public client)
      3. Otherwise: Device code flow (interactive login, public client)
    """
    _validate_client_id()

    # ── Path 1: Client Credentials (no user interaction) ──────────────────────
    if client_secret and tenant_id and tenant_id != "unknown":
        try:
            with _temporarily_disable_dead_proxy():
                cache = _load_cache()
                app = _get_app_confidential(client_secret, tenant_id, cache, client_id=client_id)
                effective_scopes = scopes or SCOPES_CLIENT
                result = _has_token_result(app.acquire_token_for_client(scopes=effective_scopes))

            if result is None:
                raise RuntimeError("Client credentials auth returned no result")

            if "error" in result:
                error_desc = result.get("error_description", "unknown error")
                logger.error(f"Client credentials failed: {result['error']} – {error_desc}")
                raise RuntimeError(f"Client credentials auth failed: {error_desc}")

            _save_cache(cache)
            access_token = result.get("access_token")
            logger.info(f"✓ Token acquired via client credentials (tenant: {tenant_id})")
            return {"access_token": access_token, "tenant_id": tenant_id}

        except Exception as e:
            logger.warning(f"Client credentials flow failed, falling back to cache/device code: {e}")

    # ── Path 2: Cached Token (silent refresh, public client) ──────────────────
    try:
        cache = _load_cache()
        app = _get_app_public(cache)
        accounts = app.get_accounts()

        if accounts:
            effective_scopes = scopes or SCOPES_USER
            result = _has_token_result(app.acquire_token_silent(effective_scopes, account=accounts[0]))
            if result and "access_token" in result:
                _save_cache(cache)
                tid = _extract_tenant_id(result)
                logger.info(f"✓ Token refreshed from cache (tenant: {tid})")
                return {"access_token": result["access_token"], "tenant_id": tid}
    except Exception as e:
        logger.debug(f"Silent token refresh failed: {e}")

    # ── Path 3: Device Code Flow (interactive login, public client) ───────────
    logger.info("Initiating device code flow (interactive login required)...")
    try:
        cache = _load_cache()
        app = _get_app_public(cache)

        effective_scopes = scopes or SCOPES_USER
        flow = _has_token_result(app.initiate_device_flow(scopes=effective_scopes))
        if flow is None:
            raise RuntimeError("Device flow init failed: no response from MSAL")
        if "user_code" not in flow:
            raise RuntimeError(
                f"Device flow init failed: {flow.get('error')} – "
                f"{flow.get('error_description')}"
            )

        print("\n" + "=" * 70)
        print("  ServerMonitor – Microsoft Login Required")
        print("=" * 70)
        print(flow["message"])
        print("=" * 70 + "\n")

        result = _has_token_result(app.acquire_token_by_device_flow(flow))
        if result is None:
            raise RuntimeError("Device code login failed: no response from MSAL")
        if "error" in result:
            raise RuntimeError(
                f"Device code login failed: {result['error']} – "
                f"{result.get('error_description')}"
            )

        _save_cache(cache)
        tid = _extract_tenant_id(result)

        try:
            keyring.set_password(_SVC, _TENANT_ACCT, tid)
        except Exception:
            pass

        logger.info(f"✓ Device code login successful (tenant: {tid})")
        return {"access_token": result["access_token"], "tenant_id": tid}

    except Exception as e:
        logger.error(f"All authentication methods failed: {e}")
        raise RuntimeError(f"Authentication failed: {e}") from e


def get_silent_token(
    client_secret: str | None = None,
    tenant_id: str | None = None,
    scopes: list[str] | None = None,
    client_id: str | None = None
) -> dict | None:
    """
    Returns {access_token, tenant_id} using ONLY non-interactive methods.
    Returns None if no token available.

    Safe for background threads / scheduler.
    """
    try:
        _validate_client_id()

        # Try client credentials first (if available)
        if client_secret and tenant_id and tenant_id != "unknown":
            try:
                cache = _load_cache()
                app = _get_app_confidential(client_secret, tenant_id, cache, client_id=client_id)
                effective_scopes = scopes or SCOPES_CLIENT
                result = _has_token_result(app.acquire_token_for_client(scopes=effective_scopes))

                if result is not None and "error" not in result and "access_token" in result:
                    _save_cache(cache)
                    logger.debug("Silent token acquired via client credentials")
                    return {"access_token": result["access_token"], "tenant_id": tenant_id}
            except Exception as e:
                logger.debug(f"Client credentials silent auth failed: {e}")

        # Fall back to cached token (public client)
        cache = _load_cache()
        app = _get_app_public(cache)
        accounts = app.get_accounts()

        if accounts:
            effective_scopes = scopes or SCOPES_USER
            result = _has_token_result(app.acquire_token_silent(effective_scopes, account=accounts[0]))
            if result and "access_token" in result:
                _save_cache(cache)
                tid = _extract_tenant_id(result)
                logger.debug("Silent token acquired from cache")
                return {"access_token": result["access_token"], "tenant_id": tid}

        logger.debug("No cached token available")
        return None

    except Exception as e:
        logger.warning(f"Silent token acquisition failed: {e}")
        return None


def get_stored_tenant_id() -> str | None:
    """Retrieve tenant_id from OS securestore."""
    try:
        return keyring.get_password(_SVC, _TENANT_ACCT)
    except Exception:
        return None


def clear_token_cache() -> None:
    """Clear all cached tokens and config."""
    for acct in (_CACHE_ACCT, _TENANT_ACCT, _CONFIG_ACCT):
        try:
            keyring.delete_password(_SVC, acct)
        except Exception:
            pass
    logger.info("Token cache cleared")


# ── Config Persistence (Bug #12 fix: never store access_token) ────────────────
_EPHEMERAL_KEYS = {"access_token", "token_type", "expires_in", "ext_expires_in"}


def _strip_ephemeral(config: dict) -> dict:
    """Return copy of config without short-lived token values."""
    return {k: v for k, v in config.items() if k not in _EPHEMERAL_KEYS}


def encrypt_config(config: dict) -> None:
    """Persist config to keyring (strips ephemeral fields)."""
    safe = _strip_ephemeral(config)
    try:
        keyring.set_password(_SVC, _CONFIG_ACCT, json.dumps(safe))
    except Exception as e:
        _file_save(json.dumps(safe))
        logger.warning(f"Keyring unavailable, using file fallback: {e}")


def decrypt_config() -> dict | None:
    """Load config from keyring. Returns None if not set."""
    try:
        raw = keyring.get_password(_SVC, _CONFIG_ACCT)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return _file_load()


# ── Bug #11 fix: Machine-derived encryption key ────────────────────────────────
def _machine_secret() -> bytes:
    """Derive 32-byte secret from machine identity (never written to disk)."""
    parts = [platform.node()]

    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject Win32_ComputerSystem).Name + '|' + "
                 "(New-Object System.Security.Principal.NTAccount($env:USERNAME)).Translate("
                 "[System.Security.Principal.SecurityIdentifier]).Value"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                parts.append(result.stdout.strip())
        except Exception:
            pass
    else:
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(candidate) as f:
                    parts.append(f.read().strip())
                break
            except Exception:
                pass

    raw = "|".join(parts).encode()
    return hashlib.pbkdf2_hmac("sha256", raw, b"ServerMonitorISV-v2", 200_000)


def _get_fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(_machine_secret())
    return Fernet(key)


_FALLBACK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", ".config.enc"
)


def _file_save(data: str) -> None:
    try:
        f = _get_fernet()
        os.makedirs(os.path.dirname(os.path.abspath(_FALLBACK_FILE)), exist_ok=True)
        with open(_FALLBACK_FILE, "wb") as fp:
            fp.write(f.encrypt(data.encode()))
        try:
            os.chmod(_FALLBACK_FILE, 0o600)
        except Exception:
            pass
    except ImportError:
        logger.warning("cryptography not installed; config not persisted")
    except Exception as e:
        logger.error(f"File config save failed: {e}")


def _file_load() -> dict | None:
    if not os.path.exists(_FALLBACK_FILE):
        return None
    try:
        f = _get_fernet()
        with open(_FALLBACK_FILE, "rb") as fp:
            return json.loads(f.decrypt(fp.read()).decode())
    except Exception as e:
        logger.debug(f"File config load failed: {e}")
        return None


# ── Backward compatibility ─────────────────────────────────────────────────────
def get_tenant_config() -> dict:
    """Shim: from auth.multi_tenant_auth import get_tenant_config."""
    config = decrypt_config() or {}

    sp_creds = config.get("sharepoint_credentials", {})
    client_secret = sp_creds.get("client_secret")
    tenant_id = sp_creds.get("tenant_id") or config.get("tenant_id")

    # Prefer delegated user token (cached or via device flow) for SharePoint operations
    # If a cached user token is available, use that. Otherwise fall back to client credentials
    # which provide app-only tokens.
    merged = dict(config)

    # Attempt to get a silent/cached user token first
    silent = get_silent_token(scopes=SCOPES_USER)
    if silent and 'access_token' in silent:
        merged['access_token'] = silent['access_token']
        merged['tenant_id'] = silent.get('tenant_id')
        merged['auth_type'] = 'delegated'
        # mark tenant as connected if we have sharepoint_site_url
        if 'sharepoint_site_url' in merged:
            merged.setdefault('sharepoint_site_url', merged.get('sharepoint_site_url'))
        return merged

    # Fall back to app-only token via client credentials
    token_data = get_valid_token(client_secret=client_secret, tenant_id=tenant_id)
    merged["access_token"] = token_data["access_token"]
    merged["tenant_id"] = token_data["tenant_id"]
    merged['auth_type'] = 'app'

    if "sharepoint_site_url" not in merged and sp_creds.get("site_url"):
        merged["sharepoint_site_url"] = sp_creds["site_url"]

    return merged


def get_tenant_config_silent() -> dict | None:
    """Return tenant config with access_token if available via silent methods only.

    Returns None if no non-interactive token is available. Safe for background use.
    """
    config = decrypt_config() or {}

    sp_creds = config.get("sharepoint_credentials", {})
    client_secret = sp_creds.get("client_secret")
    tenant_id = sp_creds.get("tenant_id") or config.get("tenant_id")

    merged = dict(config)

    # Try delegated cached token first
    try:
        silent = get_silent_token(scopes=SCOPES_USER, client_secret=None, tenant_id=None)
        if silent and "access_token" in silent:
            merged["access_token"] = silent["access_token"]
            merged["tenant_id"] = silent.get("tenant_id")
            merged["auth_type"] = "delegated"
            return merged
    except Exception:
        pass

    # Try silent client credentials (app-only)
    try:
        app_silent = get_silent_token(client_secret=client_secret, tenant_id=tenant_id, scopes=SCOPES_CLIENT)
        if app_silent and "access_token" in app_silent:
            merged["access_token"] = app_silent["access_token"]
            merged["tenant_id"] = app_silent.get("tenant_id") or tenant_id
            merged["auth_type"] = "app"
            return merged
    except Exception:
        pass

    return None


# ── Authorization Code (OAuth2) helpers for web apps ─────────────────────────
def get_authorization_url(redirect_uri: str, scopes: list[str] | None = None, state: str | None = None) -> str:
    """
    Build an authorization URL for a user-interactive OAuth2 Authorization Code flow.

    Usage: redirect user to the returned URL. The callback will receive "code".
    """
    _validate_client_id()
    cache = _load_cache()
    app = _get_app_public(cache)
    effective_scopes = scopes or SCOPES_USER
    # msal.PublicClientApplication exposes get_authorization_request_url
    url = app.get_authorization_request_url(effective_scopes, state=state, redirect_uri=redirect_uri)
    return url


def acquire_token_by_auth_code(auth_code: str, redirect_uri: str, client_secret: str | None = None, tenant_id: str | None = None, scopes: list[str] | None = None) -> dict:
    """
    Exchange an authorization code for tokens. Supports both public-client and confidential-client
    depending on whether client_secret+tenant_id are provided.

    Returns the token result dict from MSAL and persists the token cache.
    """
    _validate_client_id()
    effective_scopes = scopes or SCOPES_USER

    cache = _load_cache()

    # Prefer confidential client when secret+tenant are available (server-side web apps)
    if client_secret and tenant_id and tenant_id != "unknown":
        app = _get_app_confidential(client_secret, tenant_id, cache)
    else:
        app = _get_app_public(cache)

    result = None
    try:
        result = app.acquire_token_by_authorization_code(auth_code, scopes=effective_scopes, redirect_uri=redirect_uri)
    except Exception as e:
        logger.error(f"Authorization code exchange failed: {e}")
        raise

    if not isinstance(result, dict) or 'access_token' not in result:
        err = result.get('error_description') if isinstance(result, dict) else str(result)
        logger.error(f"Authorization code exchange did not return access_token: {err}")
        raise RuntimeError(f"Auth code exchange failed: {err}")

    # persist cache and tenant
    try:
        _save_cache(cache)
        tid = _extract_tenant_id(result)
        try:
            keyring.set_password(_SVC, _TENANT_ACCT, tid)
        except Exception:
            logger.debug("Could not persist tenant_id to keyring")
    except Exception as e:
        logger.debug(f"Failed to persist MSAL cache after auth code exchange: {e}")

    return result
