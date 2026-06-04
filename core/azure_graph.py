"""
core/azure_graph.py – Microsoft Graph API Client
=================================================
All Graph calls use delegated token from user session.
Falls back to session['access_token'] if MSAL silent fails.
Never crashes — returns empty list on failure.
"""

import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger("azure-graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_token_for_tenant(tenant_record: Optional[Any] = None) -> Optional[str]:
    """
    Get access token for Graph API calls.
    Priority:
      1. Tenant stored credentials (app-level token)
      2. MSAL silent token (from entra_auth cache)
      3. session['access_token'] (stored on Entra callback)
    """
    try:
        # Priority 1: Use tenant's stored Azure credentials (app-level token)
        if tenant_record and hasattr(tenant_record, 'azure_client_id'):
            if (tenant_record.azure_client_id and 
                tenant_record.azure_client_secret and 
                tenant_record.azure_tenant_id):
                try:
                    token = _get_app_token(
                        tenant_record.azure_client_id,
                        tenant_record.azure_client_secret,
                        tenant_record.azure_tenant_id
                    )
                    if token:
                        logger.debug(f"Using tenant app-level token")
                        return token
                except Exception as e:
                    logger.warning(f"Failed to get app-level token: {e}")
        
        from flask import has_request_context, session
        if not has_request_context():
            logger.debug("No request context for Graph API")
            return None

        # Try MSAL silent first
        try:
            from auth.entra_auth import get_token_silently
            token = get_token_silently()
            if token:
                return token
        except Exception:
            pass

        # Fallback: session access_token
        token = session.get('access_token')
        if token:
            return token

        # Also check nested user dict
        user_data = session.get('user', {})
        if isinstance(user_data, dict):
            token = user_data.get('access_token')
            if token:
                return token

        logger.debug("No Graph API token available")
        return None
    except Exception as e:
        logger.error(f"Token acquisition error: {e}")
        return None


def _get_app_token(client_id: str, client_secret: str, tenant_id: str) -> Optional[str]:
    """Get app-level access token using client credentials flow."""
    try:
        import requests
        
        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        token = token_data.get('access_token')
        
        if token:
            logger.debug(f"Successfully obtained app-level token for tenant {tenant_id}")
            return token
        else:
            logger.warning("No access_token in response")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get app-level token: {e}")
        return None


def _paged_get(url: str, token: str) -> List[Dict[str, Any]]:
    """Fetch all pages from a Graph API endpoint."""
    items: List[Dict[str, Any]] = []
    headers = {'Authorization': f'Bearer {token}'}
    next_url = url
    while next_url:
        try:
            resp = requests.get(next_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                if resp.status_code == 403:
                    logger.warning(f"Graph API 403: Missing permissions for endpoint {url}")
                else:
                    logger.error(f"Graph API error {resp.status_code}: {resp.text[:200]}")
                break
            j = resp.json()
            value = j.get('value', [])
            items.extend(value)
            next_url = j.get('@odata.nextLink')
        except Exception as e:
            logger.error(f"Graph API request failed: {e}")
            break
    return items


def get_devices(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch Azure AD devices – filtered to active, physical endpoints only.

    Applies server-side OData filters to exclude:
      • Disabled devices (accountEnabled eq false)
    Then client-side filters to remove non-physical/stale entries:
      • Mobile / phone devices (Android, iOS without macOS)
      • Devices with no OS information (ghost entries)
    """
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        # Only fetch enabled devices with relevant fields
        url = (GRAPH_BASE +
               "/devices"
               "?$select=id,displayName,operatingSystem,operatingSystemVersion,accountEnabled,deviceId"
               "&$filter=accountEnabled eq true")
        raw_devices = _paged_get(url, token)

        # Client-side post-filter: keep only physical computers (Windows, macOS, Linux)
        PHYSICAL_OS_KEYWORDS = {'windows', 'macos', 'mac os', 'linux', 'ubuntu', 'redhat', 'centos', 'debian'}
        filtered = []
        for d in raw_devices:
            os_val = (d.get('operatingSystem') or '').lower()
            # Skip devices with no OS or mobile-only OS
            if not os_val:
                continue
            if any(kw in os_val for kw in PHYSICAL_OS_KEYWORDS):
                filtered.append(d)

        logger.info(f"get_devices: {len(raw_devices)} raw → {len(filtered)} after physical-OS filter")
        return filtered
    except Exception as e:
        logger.error(f"get_devices failed: {e}")
        return []


def get_users(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch Azure AD users."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        # Append filter for active users only
        url = GRAPH_BASE + "/users?$select=id,userPrincipalName,displayName,jobTitle,department,mail,employeeId,mailNickname,onPremisesSamAccountName&$filter=accountEnabled eq true"
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_users failed: {e}")
        return []


def get_device_owners(device_id: str, tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch registered owners for a device."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        url = GRAPH_BASE + f"/devices/{device_id}/registeredOwners"
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_device_owners failed: {e}")
        return []


def get_managed_devices(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch Intune managed devices."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        url = (GRAPH_BASE + "/deviceManagement/managedDevices"
               "?$select=id,deviceName,operatingSystem,osVersion,emailAddress,"
               "userPrincipalName,serialNumber,isEncrypted,complianceState")
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_managed_devices failed: {e}")
        return []


def get_organization(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch organization/tenant info."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        url = GRAPH_BASE + "/organization"
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_organization failed: {e}")
        return []


def get_subscribed_skus(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch subscribed SKUs (licenses) for a tenant."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        url = GRAPH_BASE + "/subscribedSkus"
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_subscribed_skus failed: {e}")
        return []


def get_users_with_licenses(tenant_record: Optional[object] = None) -> List[Dict[str, Any]]:
    """Fetch users and their assigned license details."""
    token = _get_token_for_tenant(tenant_record)
    if not token:
        return []
    try:
        url = GRAPH_BASE + "/users?$select=id,userPrincipalName,displayName,assignedLicenses,employeeId,mailNickname,onPremisesSamAccountName"
        return _paged_get(url, token)
    except Exception as e:
        logger.error(f"get_users_with_licenses failed: {e}")
        return []


class AzureGraphClient:
    """Graph API client wrapper expected by AzureSyncService."""

    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id

        # Class to mimic Tenant model for token retrieval
        class DummyTenant:
            def __init__(self, cid, csec, tid):
                self.azure_client_id = cid
                self.azure_client_secret = csec
                self.azure_tenant_id = tid
        self.tenant_record = DummyTenant(client_id, client_secret, tenant_id)

    def get_devices(self) -> List[Dict[str, Any]]:
        return get_devices(self.tenant_record)

    def get_users(self) -> List[Dict[str, Any]]:
        return get_users(self.tenant_record)

    def get_subscribed_skus(self) -> List[Dict[str, Any]]:
        return get_subscribed_skus(self.tenant_record)

    def get_users_with_licenses(self) -> List[Dict[str, Any]]:
        return get_users_with_licenses(self.tenant_record)

    def get_device_owners(self, device_id: str) -> List[Dict[str, Any]]:
        return get_device_owners(device_id, self.tenant_record)

