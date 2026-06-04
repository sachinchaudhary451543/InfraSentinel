"""
core/graph_integration.py – Microsoft Graph API Integration
===========================================================

Fetch devices, users, and device registrations from Azure AD using Graph API.

Functions:
  • get_devices_from_graph() - Fetch all devices in tenant
  • get_users_from_graph() - Fetch all users
  • get_device_owners() - Get owner info for device
  • get_registered_devices() - Devices registered to specific user
  • sync_devices_to_database() - Store device data locally
"""

import logging
import time
from typing import List, Dict, Optional
import requests
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("[GRAPH-API]")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _make_graph_request(
    endpoint: str,
    access_token: str,
    method: str = "GET",
    data: Optional[Dict] = None
) -> Optional[Dict]:
    """
    Make authenticated request to Microsoft Graph API.
    
    Args:
        endpoint: Graph API endpoint (e.g., "/devices")
        access_token: Bearer token for authentication
        method: HTTP method (GET, POST, etc.)
        data: Request body data
    
    Returns:
        Response JSON or None if failed
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        url = f"{GRAPH_BASE}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            return None
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            if response.status_code == 403:
                logger.warning(f"Graph API 403: Missing permissions for endpoint {endpoint}")
            else:
                logger.warning(f"Graph API error {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Graph request failed: {e}")
        return None


def get_devices_from_graph(access_token: str) -> List[Dict]:
    """
    Fetch all devices in the Azure AD tenant.
    
    Args:
        access_token: Access token with Device.Read.All scope
    
    Returns:
        List of device objects
    """
    devices = []
    next_url = "/devices?$select=id,displayName,operatingSystem,operatingSystemVersion,accountEnabled,deviceId"
    
    while next_url:
        result = _make_graph_request(next_url, access_token)
        if not result:
            break
        
        devices.extend(result.get("value", []))
        
        # Handle pagination
        next_url = result.get("@odata.nextLink")
        if next_url:
            # Extract path from full URL
            next_url = next_url.replace(GRAPH_BASE, "")
    
    return devices


def get_users_from_graph(access_token: str) -> List[Dict]:
    """
    Fetch all users in the Azure AD tenant.
    
    Args:
        access_token: Access token with Directory.Read.All scope
    
    Returns:
        List of user objects
    """
    users = []
    # Only fetch active (enabled) accounts to prevent importing stale data
    next_url = "/users?$select=id,userPrincipalName,mail,displayName,jobTitle,department,mailNickname,onPremisesSamAccountName,employeeId,accountEnabled&$filter=accountEnabled eq true"
    
    while next_url:
        result = _make_graph_request(next_url, access_token)
        if not result:
            break
        
        users.extend(result.get("value", []))
        
        # Handle pagination
        next_url = result.get("@odata.nextLink")
        if next_url:
            next_url = next_url.replace(GRAPH_BASE, "")
    
    return users


def get_user_registered_devices(user_id: str, access_token: str) -> List[Dict]:
    """
    Get devices registered to a specific user.
    
    Args:
        user_id: User's object ID (OID)
        access_token: Access token
    
    Returns:
        List of registered devices
    """
    result = _make_graph_request(
        f"/users/{user_id}/registeredDevices",
        access_token
    )
    
    return result.get("value", []) if result else []


def get_device_details(device_id: str, access_token: str) -> Optional[Dict]:
    """
    Fetch detailed information about a device.
    
    Args:
        device_id: Device's object ID
        access_token: Access token
    
    Returns:
        Device object or None
    """
    return _make_graph_request(f"/devices/{device_id}", access_token)


def get_device_owners(device_id: str, access_token: str) -> List[Dict]:
    """
    Get owners of a device.
    
    Args:
        device_id: Device's object ID
        access_token: Access token
    
    Returns:
        List of owner objects
    """
    result = _make_graph_request(
        f"/devices/{device_id}/owners",
        access_token
    )
    
    return result.get("value", []) if result else []


def get_device_member_of(device_id: str, access_token: str) -> List[Dict]:
    """
    Get groups that contain the device.
    
    Args:
        device_id: Device's object ID
        access_token: Access token
    
    Returns:
        List of group objects
    """
    result = _make_graph_request(
        f"/devices/{device_id}/memberOf",
        access_token
    )
    
    return result.get("value", []) if result else []


def search_devices_by_hostname(hostname: str, access_token: str) -> List[Dict]:
    """
    Search for devices by hostname/display name.
    
    Args:
        hostname: Device hostname to search for
        access_token: Access token
    
    Returns:
        List of matching devices
    """
    # Use OData filter
    filter_query = f"startswith(displayName,'{hostname}')"
    endpoint = f"/devices?$filter={filter_query}"
    
    result = _make_graph_request(endpoint, access_token)
    return result.get("value", []) if result else []


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SYNC
# ─────────────────────────────────────────────────────────────────────────────

def _commit_with_retry(db_session, tenant_id, operation_name, retries=3, delay=1):
    for attempt in range(retries):
        try:
            db_session.commit()
            return True
        except OperationalError as exc:
            message = str(exc).lower()
            db_session.rollback()
            if 'database is locked' in message and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            logger.error(f"Failed to commit {operation_name} for tenant {tenant_id}: {exc}")
            return False
        except Exception as exc:
            db_session.rollback()
            logger.error(f"Failed to commit {operation_name} for tenant {tenant_id}: {exc}")
            return False
    return False


def sync_devices_to_database(devices: List[Dict], tenant_id: str, db_session) -> int:
    """
    Sync devices from Graph API to local database.
    
    Args:
        devices: List of device objects from Graph API
        tenant_id: Tenant ID for these devices
        db_session: SQLAlchemy session
    
    Returns:
        Number of devices synced
    """
    from web.models import AzureDevice
    from core.identity_correlation import normalize_hostname
    from datetime import datetime
    
    synced_count = 0
    
    for device in devices:
        try:
            device_id = device.get("id")
            hostname = device.get("displayName", "Unknown")

            with db_session.no_autoflush:
                existing = db_session.query(AzureDevice).filter_by(
                    device_id=device_id,
                    tenant_id=tenant_id
                ).first()

            if existing:
                existing.display_name = hostname
                existing.normalized_hostname = normalize_hostname(hostname)
                existing.device_type = device.get("deviceType")
                existing.os_version = device.get("operatingSystem")
                existing.os_platform = device.get("operatingSystem")
                existing.is_compliant = device.get("isCompliant", False)
                existing.last_graph_sync = datetime.utcnow()
            else:
                new_device = AzureDevice(
                    tenant_id=tenant_id,
                    device_id=device_id,
                    display_name=hostname,
                    normalized_hostname=normalize_hostname(hostname),
                    device_type=device.get("deviceType"),
                    os_version=device.get("operatingSystem"),
                    is_compliant=device.get("isCompliant", False),
                    os_platform=device.get("operatingSystem") or device.get("osPlatform"),
                    is_managed_by_intune=device.get("isManaged", False),
                    last_graph_sync=datetime.utcnow()
                )
                db_session.add(new_device)

            synced_count += 1

        except Exception as e:
            logger.error(f"Failed to sync device {device.get('id')}: {e}")
            try:
                db_session.rollback()
            except Exception:
                pass

    if _commit_with_retry(db_session, tenant_id, 'device sync'):
        logger.info(f"Synced {synced_count} devices for tenant {tenant_id}")

    return synced_count


def sync_users_to_database(users: List[Dict], tenant_id: str, db_session) -> int:
    """
    Sync users from Graph API to local database.
    
    Args:
        users: List of user objects from Graph API
        tenant_id: Tenant ID for these users
        db_session: SQLAlchemy session
    
    Returns:
        Number of users synced
    """
    from web.models import AzureUser
    from datetime import datetime
    
    synced_count = 0
    
    for user in users:
        try:
            user_id = user.get("id")
            email = user.get("userPrincipalName")
            display_name = user.get("displayName", "Unknown")
            prefix = (email or "").split("@", 1)[0]

            with db_session.no_autoflush:
                existing = db_session.query(AzureUser).filter_by(
                    user_id=user_id,
                    tenant_id=tenant_id
                ).first()

            if existing:
                existing.email = email
                existing.display_name = display_name
                existing.job_title = user.get("jobTitle")
                existing.department = user.get("department")
                existing.employee_id = user.get("employeeId") or user.get("mailNickname") or prefix
                existing.mail_nickname = user.get("mailNickname")
                existing.sam_account_name = user.get("onPremisesSamAccountName")
                existing.last_synced = datetime.utcnow()
            else:
                new_user = AzureUser(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    email=email,
                    display_name=display_name,
                    job_title=user.get("jobTitle"),
                    department=user.get("department"),
                    employee_id=user.get("employeeId") or user.get("mailNickname") or prefix,
                    mail_nickname=user.get("mailNickname"),
                    sam_account_name=user.get("onPremisesSamAccountName"),
                    last_synced=datetime.utcnow()
                )
                db_session.add(new_user)

            synced_count += 1

        except Exception as e:
            logger.error(f"Failed to sync user {user.get('id')}: {e}")
            try:
                db_session.rollback()
            except Exception:
                pass

    if _commit_with_retry(db_session, tenant_id, 'user sync'):
        logger.info(f"Synced {synced_count} users for tenant {tenant_id}")

    return synced_count
