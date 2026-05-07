"""
Azure AD / Microsoft Graph discovery helper.

Uses MSAL to acquire an app-only token and queries Microsoft Graph to list
devices and (if available) managed devices. Returns results in the
DiscoveredSystem-like dicts expected by the domain discovery engine.

This module is intentionally minimal and safe for local diagnostic use. It
requires environment variables or explicit parameters for credentials:
AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID.
"""
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import msal
    import requests
except Exception:
    msal = None  # type: ignore
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


def _get_token(client_id: str, client_secret: str, tenant_id: str) -> Optional[str]:
    if msal is None:
        raise ImportError("msal is not installed; install with `pip install msal requests`")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
    scope = ["https://graph.microsoft.com/.default"]
    result = app.acquire_token_for_client(scopes=scope)
    if "access_token" in result:
        return result["access_token"]
    logger.error(f"Failed to obtain access token: {result}")
    # return None to keep backward compatibility for callers that expect a token string
    return None


def get_token_result(client_id: str, client_secret: str, tenant_id: str) -> Dict[str, Any]:
    """Return the raw MSAL token acquisition result dict for diagnostics.

    This is useful for caller code that wants to inspect error codes and
    error_descriptions returned by AAD (e.g., invalid_client, invalid_scope,
    insufficient privileges).
    """
    if msal is None:
        raise ImportError("msal is not installed; install with `pip install msal requests`")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
    scope = ["https://graph.microsoft.com/.default"]
    result = app.acquire_token_for_client(scopes=scope)
    return result


def discover_devices(client_id: Optional[str]=None, client_secret: Optional[str]=None, tenant_id: Optional[str]=None) -> List[Dict[str, Any]]:
    """Discover devices via Microsoft Graph and return list of dicts compatible with DiscoveredSystem."""
    client_id = client_id or os.environ.get("AZURE_CLIENT_ID")
    client_secret = client_secret or os.environ.get("AZURE_CLIENT_SECRET")
    tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID")

    if not (client_id and client_secret and tenant_id):
        logger.debug("Azure credentials not provided; skipping Azure discovery")
        return []

    token = _get_token(client_id, client_secret, tenant_id)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    devices = []

    # Query registered devices
    try:
        url = "https://graph.microsoft.com/v1.0/devices"
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("value", []):
                devices.append({
                    "hostname": item.get("displayName") or item.get("deviceId"),
                    "ip_address": None,
                    "os_name": item.get("operatingSystem") or "Unknown",
                    "os_version": item.get("operatingSystemVersion"),
                    "system_type": item.get("deviceCategory") or "Unknown",
                    "domain": tenant_id,
                    "ou_path": "",
                    "mac_address": None,
                    "serial_number": item.get("deviceId"),
                    "discovered_at": datetime.utcnow().isoformat(),
                    "last_seen": datetime.utcnow().isoformat(),
                    "enabled": True,
                    "description": item.get("description"),
                })
        else:
            logger.warning(f"Graph /devices returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Azure Graph /devices query failed: {e}")

    # Query managed devices if Intune is present
    try:
        url2 = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        resp2 = requests.get(url2, headers=headers, timeout=20)
        if resp2.status_code == 200:
            data2 = resp2.json()
            for item in data2.get("value", []):
                devices.append({
                    "hostname": item.get("deviceName") or item.get("id"),
                    "ip_address": item.get("ipAddress"),
                    "os_name": item.get("operatingSystem") or "Unknown",
                    "os_version": item.get("osVersion"),
                    "system_type": item.get("deviceType") or "Unknown",
                    "domain": tenant_id,
                    "ou_path": "",
                    "mac_address": item.get("macAddress"),
                    "serial_number": item.get("serialNumber"),
                    "discovered_at": datetime.utcnow().isoformat(),
                    "last_seen": datetime.utcnow().isoformat(),
                    "enabled": item.get("isEncrypted", True),
                    "description": None,
                })
        else:
            logger.debug(f"Graph /deviceManagement/managedDevices returned {resp2.status_code}")
    except Exception as e:
        logger.debug(f"Graph managedDevices query failed: {e}")

    logger.info(f"Azure discovery found {len(devices)} devices")
    return devices
