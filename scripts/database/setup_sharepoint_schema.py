"""
SharePoint Auto-Provisioning for Multi-Tenant Monitoring

- Detects tenant SharePoint domain
- Creates site, lists, columns as needed
- Sets initialization flag in config
- Never recreates columns at runtime

Column names here are the single source of truth.
sharepoint_uploader.py must match these names exactly.
"""

import logging
import requests
import time
from contextlib import contextmanager
from urllib.parse import urlparse
from auth.multi_tenant_auth import encrypt_config
from auth.msal_auth import get_silent_token

try:
    from office365.runtime.auth.client_credential import ClientCredential
    from office365.sharepoint.client_context import ClientContext
    from office365.sharepoint.lists.creation_information import ListCreationInformation
    _OFFICE365_AVAILABLE = True
except Exception:
    ClientCredential = None  # type: ignore[assignment]
    ClientContext = None  # type: ignore[assignment]
    ListCreationInformation = None  # type: ignore[assignment]
    _OFFICE365_AVAILABLE = False

# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH — all column names defined here.
# sharepoint_uploader.py reads from REQUIRED_LISTS, never hardcodes its own.
# ---------------------------------------------------------------------------
REQUIRED_LISTS = {
    "ServerMetricsSummary": [
        # Identity
        "ServerName",       # Text  – hostname (also used as Title / upsert key)
        "Timestamp",        # Text  – ISO datetime of last update
        # CPU
        "AvgCPU",           # Number – average CPU utilisation %
        # RAM
        "AvgRAM",           # Number – average RAM utilisation %
        "TotalRAM",         # Number – total RAM in GB
        "AvailableRAM",     # Number – available RAM in GB
        "OutOfRAM",         # Number – sample count where available RAM < 1 GB
        # Disk
        "AvgDisk",          # Number – average disk (SSD) utilisation %
        "AvgSSD",           # Number – alias kept for Power BI compat (same value)
        "TotalSSD",         # Number – total disk in GB
        "AvailableSSD",     # Number – available disk in GB
        "OutOfSSD",         # Number – sample count where available disk < 10 GB
        # Health
        "HealthStatus",     # Text  – "Normal" | "Warning" | "Critical"
        "Error",            # Text  – last error string, empty if none
    ],
    "ServerMetricsHistory": [
        # Same columns as Summary — history is append-only, summary is upserted
        "ServerName",
        "Timestamp",
        "AvgCPU",
        "AvgRAM",
        "TotalRAM",
        "AvailableRAM",
        "OutOfRAM",
        "AvgDisk",
        "AvgSSD",
        "TotalSSD",
        "AvailableSSD",
        "OutOfSSD",
        "HealthStatus",
        "Error",
    ],
    "ServerVMs": [
        "ServerName",       # Text  – host server name (also stored as Title)
        "HostServer",       # Text  – same as ServerName, kept for query compat
        "VMName",           # Text  – virtual machine name
        "State",            # Text  – Running | Off | Paused | Saved
        "CPUUsage",         # Number – VM CPU usage %
        "MemoryAssigned",   # Number – MB of RAM assigned to VM
        "Uptime",           # Text  – uptime string from Hyper-V
        "Path",             # Text  – VM storage path
        "HostIP",           # Text  – IP address of host server
        "HostOS",           # Text  – OS platform string of host
    ],
    "ServerControl": [
        # Bidirectional control channel (polled by agent)
        "ServerName",       # Text  – target server hostname
        "Status",           # Text  – "Enabled" | "Disabled"
        "Action",           # Text  – "None" | "Delete" | "Restart"
    ],
    "ServerInventory": [
        "ServerName",       # Text
        "IPAddress",        # Text
        "MACAddress",       # Text
        "OS",               # Text
        "Location",         # Text
        "InstallDate",      # DateTime
        "LastModified",     # DateTime
    ],
}

# Columns that should be indexed for fast CAML / OData queries
INDEXED_COLUMNS = ["ServerName", "Timestamp"]

# SharePoint field type codes
FIELD_TYPE_TEXT = 2
FIELD_TYPE_NUMBER = 3
FIELD_TYPE_DATETIME = 4

# Column type mapping — any column not listed here defaults to Text
COLUMN_TYPES = {
    "AvgCPU": FIELD_TYPE_NUMBER,
    "AvgRAM": FIELD_TYPE_NUMBER,
    "AvgDisk": FIELD_TYPE_NUMBER,
    "AvgSSD": FIELD_TYPE_NUMBER,
    "TotalRAM": FIELD_TYPE_NUMBER,
    "AvailableRAM": FIELD_TYPE_NUMBER,
    "TotalSSD": FIELD_TYPE_NUMBER,
    "AvailableSSD": FIELD_TYPE_NUMBER,
    "OutOfRAM": FIELD_TYPE_NUMBER,
    "OutOfSSD": FIELD_TYPE_NUMBER,
    "CPUUsage": FIELD_TYPE_NUMBER,
    "MemoryAssigned": FIELD_TYPE_NUMBER,
    "InstallDate": FIELD_TYPE_DATETIME,
    "LastModified": FIELD_TYPE_DATETIME,
}

logging.basicConfig(
    level=logging.INFO,
    format="[SP-PROVISION] %(asctime)s %(levelname)s: %(message)s",
)


@contextmanager
def _temporarily_disable_dead_proxy():
    """Bypass only the known-invalid local proxy that breaks outbound HTTPS here."""
    import os

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=verbose",
        "Content-Type": "application/json",
    }


def _retry_get(url: str, headers: dict, retries: int = 3, delay: float = 2.0):
    for attempt in range(retries):
        try:
            with _temporarily_disable_dead_proxy():
                resp = requests.get(url, headers=headers, timeout=15)
            return resp
        except Exception as exc:
            logging.warning(f"GET {url} attempt {attempt + 1} failed: {exc}")
            time.sleep(delay * (2 ** attempt))
    raise Exception(f"GET {url} failed after {retries} retries")


def _retry_post(url: str, headers: dict, payload: dict, retries: int = 3, delay: float = 2.0):
    for attempt in range(retries):
        try:
            with _temporarily_disable_dead_proxy():
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
            return resp
        except Exception as exc:
            logging.warning(f"POST {url} attempt {attempt + 1} failed: {exc}")
            time.sleep(delay * (2 ** attempt))
    raise Exception(f"POST {url} failed after {retries} retries")


# ---------------------------------------------------------------------------
# Domain / site discovery
# ---------------------------------------------------------------------------

def get_sharepoint_domain(tenant_id: str, access_token: str) -> str:
    """Return the root SharePoint URL, e.g. https://contoso.sharepoint.com"""
    url = "https://graph.microsoft.com/v1.0/sites/root"
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(3):
        try:
            with _temporarily_disable_dead_proxy():
                resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                web_url = resp.json().get("webUrl", "")
                if web_url:
                    return web_url.split("/sites/")[0]
            logging.warning(f"Failed to get SP domain (attempt {attempt + 1}): {resp.text[:200]}")
        except Exception as exc:
            logging.error(f"SP domain error: {exc}")
        time.sleep(2 ** attempt)
    raise Exception("Unable to determine SharePoint domain for tenant.")


def ensure_site_exists(domain: str, access_token: str) -> str:
    """Return the ServerMonitoring site URL, creating it if necessary."""
    site_url = f"{domain}/sites/ServerMonitoring"
    hdrs = _headers(access_token)
    resp = _retry_get(site_url, hdrs)
    if resp.status_code == 200:
        logging.info(f"Site already exists: {site_url}")
        return site_url
    # Site not found — create via Graph API
    create_url = "https://graph.microsoft.com/v1.0/sites/root/sites"
    payload = {
        "displayName": "ServerMonitoring",
        "name": "ServerMonitoring",
        "siteCollection": {"hostname": domain.replace("https://", "")},
    }
    for attempt in range(3):
        try:
            with _temporarily_disable_dead_proxy():
                resp = requests.post(
                    create_url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=15,
                )
            if resp.status_code in (200, 201):
                logging.info(f"Site created: {site_url}")
                return site_url
            logging.warning(f"Site creation attempt {attempt + 1}: {resp.status_code} {resp.text[:200]}")
        except Exception as exc:
            logging.error(f"Site creation error: {exc}")
        time.sleep(2 ** attempt)
    raise Exception("Failed to create SharePoint site.")


def _normalize_site_url(site_url: str) -> str:
    """Return a cleaned SharePoint site URL without a trailing slash."""
    return site_url.rstrip("/")


def _domain_from_site_url(site_url: str) -> str:
    """Extract the SharePoint domain from a full site URL."""
    parsed = urlparse(site_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid SharePoint site URL: {site_url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_sharepoint_access_token(config: dict, site_url: str) -> str:
    """Acquire a token scoped for SharePoint REST on the configured site."""
    sp_creds = config.get("sharepoint_credentials", {})
    client_secret = sp_creds.get("client_secret")
    tenant_id = sp_creds.get("tenant_id") or config.get("tenant_id")
    domain = _domain_from_site_url(site_url)
    # Background-safe: attempt silent-only acquisition (no interactive login).
    token_data = get_silent_token(
        client_secret=client_secret,
        tenant_id=tenant_id,
        scopes=[f"{domain}/.default"],
    )
    if not token_data or "access_token" not in token_data:
        raise RuntimeError("No silent OAuth token available for SharePoint provisioning")
    return token_data["access_token"]


def _get_sharepoint_client_credentials(config: dict) -> tuple[str, str]:
    """Return the configured SharePoint app credentials."""
    sp_creds = config.get("sharepoint_credentials", {})
    client_id = sp_creds.get("client_id", "")
    client_secret = sp_creds.get("client_secret", "")
    if not client_id or not client_secret:
        raise ValueError("SharePoint client_id/client_secret not found in config")
    return client_id, client_secret


# ---------------------------------------------------------------------------
# List + column provisioning
# ---------------------------------------------------------------------------

def _get_existing_fields(site_url: str, list_name: str, hdrs: dict) -> set:
    """Return a set of existing field InternalNames for a list."""
    url = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')/fields"
    resp = _retry_get(url, hdrs)
    if resp.status_code != 200:
        return set()
    results = resp.json().get("d", {}).get("results", [])
    return {f.get("InternalName", "") for f in results}


def _create_list(site_url: str, list_name: str, hdrs: dict) -> bool:
    """Create a generic SharePoint list. Returns True on success."""
    url = f"{site_url}/_api/web/lists"
    payload = {
        "__metadata": {"type": "SP.List"},
        "Title": list_name,
        "BaseTemplate": 100,  # Generic list
    }
    resp = _retry_post(url, hdrs, payload)
    if resp.status_code in (200, 201):
        logging.info(f"Created list: {list_name}")
        return True
    logging.error(f"Failed to create list '{list_name}': {resp.status_code} {resp.text[:300]}")
    return False


def _create_column(site_url: str, list_name: str, col_name: str, hdrs: dict) -> bool:
    """Add a single column to a list. Returns True on success."""
    field_type = COLUMN_TYPES.get(col_name, FIELD_TYPE_TEXT)
    url = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')/fields"
    payload = {
        "__metadata": {"type": "SP.Field"},
        "Title": col_name,
        "FieldTypeKind": field_type,
    }
    resp = _retry_post(url, hdrs, payload)
    if resp.status_code in (200, 201):
        logging.info(f"  + column '{col_name}' ({field_type}) on '{list_name}'")
        return True
    # SharePoint column limit exceeded
    if "-2130246218" in resp.text:
        logging.error(
            f"SharePoint column limit exceeded on '{list_name}'. "
            f"Cannot add '{col_name}'. Delete unused columns in the SP UI first."
        )
        return False
    logging.error(f"Failed to add column '{col_name}' to '{list_name}': {resp.status_code} {resp.text[:300]}")
    return False


def _ensure_column_indexed(site_url: str, list_name: str, col_name: str, hdrs: dict):
    url = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')/fields/GetByTitle('{col_name}')"
    resp = _retry_get(url, hdrs)
    if resp.status_code != 200:
        return
    if resp.json().get("d", {}).get("Indexed"):
        return  # already indexed
    patch_url = url
    merge_hdrs = {**hdrs, "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}
    with _temporarily_disable_dead_proxy():
        requests.post(
            patch_url,
            headers=merge_hdrs,
            json={"__metadata": {"type": "SP.Field"}, "Indexed": True},
            timeout=10,
        )
    logging.info(f"  ~ indexed column '{col_name}' on '{list_name}'")


def _list_exists(site_url: str, list_name: str, access_token: str) -> bool:
    """Return True when the target SharePoint list already exists."""
    check_url = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')"
    resp = _retry_get(check_url, _headers(access_token))
    return resp.status_code == 200


def _schema_ready(site_url: str, access_token: str) -> bool:
    """
    Treat the tenant as initialized only when all required lists and columns exist.
    """
    hdrs = _headers(access_token)
    for list_name, required_columns in REQUIRED_LISTS.items():
        if not _list_exists(site_url, list_name, access_token):
            return False
        try:
            existing_fields = _get_existing_fields(site_url, list_name, hdrs)
        except Exception:
            return False
        for col in required_columns:
            if col not in existing_fields:
                return False
    return True


def _create_office365_context(site_url: str, config: dict):
    """Build a SharePoint client context using stored app credentials."""
    if not _OFFICE365_AVAILABLE or ClientContext is None or ClientCredential is None:
        raise RuntimeError("office365-rest-python-client is not available")
    client_id, client_secret = _get_sharepoint_client_credentials(config)
    return ClientContext(site_url).with_credentials(
        ClientCredential(client_id, client_secret)
    )


def _validate_office365_context(ctx, site_url: str) -> None:
    """Fail fast with a clear message if SharePoint app-only auth is not permitted."""
    try:
        with _temporarily_disable_dead_proxy():
            ctx.web.get().execute_query()
    except Exception as exc:
        raise RuntimeError(
            "SharePoint app-only authentication failed for "
            f"{site_url}. The Azure app likely lacks SharePoint application "
            "permission/admin consent for this site, or the environment proxy is "
            "blocking SharePoint connectivity. Grant SharePoint app permission such "
            "as Sites.Selected on this site or Sites.FullControl.All, ensure outbound "
            "HTTPS to SharePoint is allowed, then re-run the setup."
        ) from exc


def _ensure_list_office365(ctx, list_name: str):
    """Get or create a SharePoint list through office365-rest-python-client."""
    try:
        sp_list = ctx.web.lists.get_by_title(list_name)
        with _temporarily_disable_dead_proxy():
            sp_list.get().execute_query()
        return sp_list
    except Exception:
        if ListCreationInformation is None:
            raise RuntimeError("office365 list creation type is unavailable")
        list_info = ListCreationInformation()
        list_info.Title = list_name
        list_info.BaseTemplate = 100
        with _temporarily_disable_dead_proxy():
            return ctx.web.lists.add(list_info).execute_query()


def _ensure_field_office365(ctx, sp_list, list_name: str, field_name: str) -> bool:
    """Add a missing field to a SharePoint list via office365 client APIs."""
    with _temporarily_disable_dead_proxy():
        sp_list.fields.get().execute_query()
    existing = {
        getattr(field, "internal_name", None) or field.properties.get("InternalName", "")
        for field in sp_list.fields
    }
    if field_name in existing:
        return True

    field_type = COLUMN_TYPES.get(field_name, FIELD_TYPE_TEXT)
    try:
        with _temporarily_disable_dead_proxy():
            sp_list.fields.add_field({"Title": field_name, "FieldTypeKind": field_type}).execute_query()
        logging.info(f"  + column '{field_name}' ({field_type}) on '{list_name}'")
        return True
    except Exception as exc:
        logging.error(f"Failed to add column '{field_name}' to '{list_name}': {exc}")
        return False


def _ensure_list_and_columns_office365(site_url: str, config: dict) -> tuple[bool, list[str]]:
    """Provision all required lists and fields via office365-rest-python-client."""
    ctx = _create_office365_context(site_url, config)
    _validate_office365_context(ctx, site_url)
    failures: list[str] = []

    for list_name, columns in REQUIRED_LISTS.items():
        try:
            sp_list = _ensure_list_office365(ctx, list_name)
        except Exception as exc:
            logging.error(f"Failed to create list '{list_name}': {exc}")
            failures.append(list_name)
            continue

        for col in columns:
            if not _ensure_field_office365(ctx, sp_list, list_name, col):
                failures.append(list_name)
                break

    return (len(failures) == 0, failures)


def ensure_list_and_columns(site_url: str, access_token: str) -> tuple[bool, list[str]]:
    """
    For every list in REQUIRED_LISTS:
      1. Create the list if it does not exist.
      2. Add any missing columns (using COLUMN_TYPES for correct field type).
      3. Index INDEXED_COLUMNS.
    Uses REQUIRED_LISTS as the single source of truth.
    """
    hdrs = _headers(access_token)
    failures: list[str] = []

    for list_name, columns in REQUIRED_LISTS.items():
        # 1. Ensure list exists
        check_url = f"{site_url}/_api/web/lists/GetByTitle('{list_name}')"
        resp = _retry_get(check_url, hdrs)
        if resp.status_code != 200:
            if not _create_list(site_url, list_name, hdrs):
                logging.error(f"Skipping columns for '{list_name}' — list creation failed.")
                failures.append(list_name)
                continue

        # 2. Ensure every required column exists
        existing = _get_existing_fields(site_url, list_name, hdrs)
        for col in columns:
            if col not in existing:
                ok = _create_column(site_url, list_name, col, hdrs)
                if not ok and col in COLUMN_TYPES and COLUMN_TYPES[col] == FIELD_TYPE_NUMBER:
                    # Column limit hit — abort this list
                    break

        # 3. Index key columns
        for idx_col in INDEXED_COLUMNS:
            if idx_col in columns:
                _ensure_column_indexed(site_url, list_name, idx_col, hdrs)

    return (len(failures) == 0, failures)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def initialize_sharepoint_for_tenant():
    # Use silent-only tenant config acquisition to avoid interactive login in background
    from auth.msal_auth import decrypt_config, get_silent_token

    config = decrypt_config() or {}
    if not config:
        raise Exception("No tenant config found.")

    tenant_id = config.get("tenant_id")
    configured_site_url = (
        config.get("sharepoint_site_url")
        or config.get("sharepoint_credentials", {}).get("site_url")
        or ""
    )

    access_token = config.get("access_token")
    if not access_token:
        # Try silent-only acquisition (no interactive prompts)
        sp_client_secret = config.get("sharepoint_credentials", {}).get("client_secret")
        token = get_silent_token(
            client_secret=sp_client_secret,
            tenant_id=tenant_id,
            scopes=["https://graph.microsoft.com/.default"],
        )
        if token and "access_token" in token:
            access_token = token["access_token"]
        else:
            raise Exception("No silent OAuth token available for SharePoint provisioning")

    if configured_site_url:
        site_url = _normalize_site_url(configured_site_url)
        domain = _domain_from_site_url(site_url)
        logging.info(f"Using configured SharePoint site: {site_url}")
    else:
        # tenant_id may be None; get_sharepoint_domain only needs access_token for Graph root
        domain = get_sharepoint_domain(tenant_id or "", access_token)
        site_url = ensure_site_exists(domain, access_token)

    if _OFFICE365_AVAILABLE:
        if config.get("initialized"):
            try:
                sharepoint_token = _get_sharepoint_access_token(config, site_url)
                if _schema_ready(site_url, sharepoint_token):
                    logging.info("SharePoint already initialized for this tenant. Skipping.")
                    return
            except Exception:
                pass
        success, failures = _ensure_list_and_columns_office365(site_url, config)
    else:
        sharepoint_token = _get_sharepoint_access_token(config, site_url)
        if config.get("initialized") and _schema_ready(site_url, sharepoint_token):
            logging.info("SharePoint already initialized for this tenant. Skipping.")
            return
        success, failures = ensure_list_and_columns(site_url, sharepoint_token)

    if not success:
        raise Exception(
            "SharePoint schema provisioning failed for list(s): "
            + ", ".join(failures)
        )

    config["sharepoint_domain"] = domain
    config["sharepoint_site_url"] = site_url
    config["initialized"] = True
    encrypt_config(config)

    logging.info(f"SharePoint initialized for tenant {tenant_id} at {site_url}")


if __name__ == "__main__":
    initialize_sharepoint_for_tenant()
