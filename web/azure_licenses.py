"""Azure license sync helpers.

This module provides lightweight functions to fetch tenant license SKUs and per-user
license assignments using Microsoft Graph. It uses MSAL for auth and requests for
Graph calls. The functions are designed to be called from a background job that
persists license info into your DB.

Notes:
- Requires `msal` and `requests` packages (add to dev/prod requirements as needed).
- The code favors simplicity and clarity; adapt paging, error handling and rate-limit
  handling for production.
"""
from typing import Dict, List, Any
import time
import logging
import requests

try:
    import msal
except Exception:  # pragma: no cover - MSAL may not be installed in all envs
    msal = None

LOG = logging.getLogger(__name__)


def acquire_token(client_id: str, client_secret: str, tenant_id: str, scope: List[str] = None) -> str:
    """Acquire an app-only access token using MSAL client credentials.

    Returns the access token string for use in Graph API Authorization header.
    """
    if scope is None:
        scope = ["https://graph.microsoft.com/.default"]

    if msal is None:
        raise RuntimeError("msal library is required for acquire_token")

    app = msal.ConfidentialClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant_id}", client_credential=client_secret)
    result = app.acquire_token_silent(scope, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=scope)

    if "access_token" not in result:
        LOG.error("Failed to acquire token: %s", result)
        raise RuntimeError("Failed to acquire access token for Microsoft Graph")

    return result["access_token"]


def _get(url: str, token: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """HTTP GET wrapper that never raises for Graph permission errors.
    On a 403 it logs a warning and returns an empty dict so callers can continue.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as http_err:
        if r.status_code == 403:
            LOG.warning(f"Graph API 403 forbidden for {url}: {http_err}")
            return {}
        else:
            LOG.error(f"Graph API request failed for {url}: {http_err}")
            raise


def list_subscribed_skus(token: str) -> List[Dict[str, Any]]:
    """Return tenant SKUs (licenses) with counts.

    Example output items include skuId, skuPartNumber, prepaidUnits, consumedUnits.
    """
    url = "https://graph.microsoft.com/v1.0/subscribedSkus"
    data = _get(url, token)
    return data.get("value", [])


def list_users_with_assigned_licenses(token: str, top: int = 100) -> List[Dict[str, Any]]:
    """Iterate users with assignedLicenses in one paged collection query."""
    users = []
    url = "https://graph.microsoft.com/v1.0/users"
    params = {
        "$select": "id,displayName,mail,userPrincipalName,assignedLicenses,department,jobTitle,mailNickname,onPremisesSamAccountName,employeeId",
        "$top": top,
    }
    while url:
        data = _get(url, token, params=params)
        users.extend(data.get("value", []))
        # paging
        url = data.get("@odata.nextLink")
        params = None
    return users


def list_users_with_license_details(token: str, top: int = 100) -> List[Dict[str, Any]]:
    """Backward-compatible alias that no longer calls /licenseDetails per user."""
    return list_users_with_assigned_licenses(token, top=top)


def summarize_license_assignments(token: str) -> Dict[str, Any]:
    """Return a summary dictionary with tenant SKUs and per-user assignments.

    Structure:
    {
      "skus": [ ... ],
      "users": [ {id, displayName, userPrincipalName, licenseDetails: [...]}, ... ]
    }
    """
    skus = list_subscribed_skus(token)
    users = list_users_with_assigned_licenses(token)
    return {"skus": skus, "users": users, "fetched_at": int(time.time())}
