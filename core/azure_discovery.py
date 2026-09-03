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
import uuid
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


GRAPH_CAPABILITY_CHECKS = (
    {
        "key": "organization",
        "label": "Organization identity",
        "endpoint": "/organization?$select=id,displayName",
        "permission": "Organization.Read.All or Directory.Read.All",
        "purpose": "Confirms that this app is connected to the intended Microsoft Entra tenant.",
    },
    {
        "key": "employees",
        "label": "Employee directory",
        "endpoint": "/users?$top=1&$select=id,displayName,userPrincipalName",
        "permission": "User.Read.All or Directory.Read.All",
        "purpose": "Allows employee directory synchronization.",
    },
    {
        "key": "entra_devices",
        "label": "Entra registered devices",
        "endpoint": "/devices?$top=1&$select=id,displayName,deviceId",
        "permission": "Device.Read.All",
        "purpose": "Allows registered device discovery.",
    },
    {
        "key": "intune_devices",
        "label": "Intune managed devices",
        "endpoint": "/deviceManagement/managedDevices?$top=1&$select=id,deviceName",
        "permission": "DeviceManagementManagedDevices.Read.All",
        "purpose": "Allows Intune-managed device inventory synchronization.",
    },
    {
        "key": "licenses",
        "label": "License inventory",
        "endpoint": "/subscribedSkus?$top=1",
        "permission": "LicenseAssignment.Read.All or Organization.Read.All",
        "purpose": "Allows Microsoft 365 license inventory synchronization.",
    },
)


def _configuration_error(message: str) -> str:
    """Convert common Entra errors into an actionable, safe configuration message."""
    text = message or "Microsoft Entra did not return an error description."
    lowered = text.lower()
    if "aadsts700016" in lowered or "application with identifier" in lowered:
        return "The Client ID was not found in this tenant. Copy the Application (client) ID from the correct app registration."
    if "aadsts7000215" in lowered or "invalid client secret" in lowered:
        return "The Client Secret value is invalid. Create a new client secret and paste its Value (not its Secret ID)."
    if "aadsts7000222" in lowered or "expired" in lowered:
        return "The Client Secret has expired. Create a new secret value in Microsoft Entra ID and update this configuration."
    if "aadsts90002" in lowered or "tenant.*not found" in lowered:
        return "The Tenant ID was not found. Copy the Directory (tenant) ID from Microsoft Entra ID Overview."
    if "invalid_client" in lowered:
        return "Microsoft Entra rejected the client credentials. Check the Client ID, secret Value, and tenant association."
    return text[:1000]


def verify_graph_configuration(client_id: str, client_secret: str, tenant_id: str) -> Dict[str, Any]:
    """Perform live Graph checks required by ServerMonitor; never report untested capabilities as available."""
    report: Dict[str, Any] = {
        "ok": False,
        "can_save": False,
        "organization_name": None,
        "summary": None,
        "checks": [],
    }
    values = {"Tenant ID": tenant_id, "Client ID": client_id, "Client Secret": client_secret}
    missing = [label for label, value in values.items() if not (value or "").strip()]
    if missing:
        report["summary"] = "Missing required value(s): " + ", ".join(missing) + "."
        return report
    try:
        uuid.UUID(tenant_id.strip())
    except ValueError:
        report["summary"] = "Tenant ID must be a valid Directory (tenant) ID GUID."
        return report
    try:
        uuid.UUID(client_id.strip())
    except ValueError:
        report["summary"] = "Client ID must be a valid Application (client) ID GUID."
        return report

    try:
        token_result = get_token_result(client_id.strip(), client_secret.strip(), tenant_id.strip())
    except Exception as exc:
        report["summary"] = f"Could not contact Microsoft Entra: {str(exc)[:500]}"
        return report
    token = token_result.get("access_token")
    if not token:
        report["summary"] = _configuration_error(token_result.get("error_description") or str(token_result))
        return report

    report["can_save"] = True
    if requests is None:
        report["summary"] = "The requests package is unavailable; live Microsoft Graph checks cannot run."
        return report

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    for item in GRAPH_CAPABILITY_CHECKS:
        check = {key: item[key] for key in ("key", "label", "permission", "purpose")}
        try:
            response = requests.get(
                "https://graph.microsoft.com/v1.0" + item["endpoint"], headers=headers, timeout=15
            )
            check["status_code"] = response.status_code
            if response.ok:
                check["ok"] = True
                if item["key"] == "organization":
                    value = response.json().get("value", [])
                    if value:
                        report["organization_name"] = value[0].get("displayName")
            else:
                payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                graph_error = payload.get("error", {}) if isinstance(payload, dict) else {}
                check["ok"] = False
                check["issue"] = graph_error.get("message") or response.text[:500] or "Microsoft Graph denied this request."
        except Exception as exc:
            check["ok"] = False
            check["status_code"] = None
            check["issue"] = f"Network request failed: {str(exc)[:500]}"
        report["checks"].append(check)

    failed = [check for check in report["checks"] if not check["ok"]]
    report["ok"] = not failed
    if report["ok"]:
        report["summary"] = "Microsoft Entra and every required Microsoft Graph capability were verified live."
    else:
        report["summary"] = f"Credentials are valid, but {len(failed)} required Microsoft Graph capability check(s) failed. Review the exact results below, then grant admin consent."
    return report


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
