"""
auth/entra_auth.py – Enterprise OAuth2 via Microsoft Entra ID (Azure AD)
=========================================================================

Consolidated authentication for ServerMonitor using MSAL.

Features:
  • OAuth2 flow via Microsoft Entra ID
  • Tenant auto-detection from token claims
  • Role extraction from Azure AD groups
  • Token caching and refresh
  • User profile sync
"""

import json
import logging
import os
from functools import wraps
from typing import Dict, Optional, Tuple

import msal
import requests
from flask import redirect, session, url_for

logger = logging.getLogger("[ENTRA-AUTH]")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("SERVERMONITOR_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SERVERMONITOR_CLIENT_SECRET", "").strip()
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "common").strip()
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8080/auth/callback").strip()

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = [
    "User.Read",
    "Directory.Read.All",
    "Device.Read.All",
    "Sites.ReadWrite.All",
    "DeviceManagementManagedDevices.Read.All"
]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def validate_configuration() -> None:
    """Validate that all required environment variables are set."""
    required = {
        "SERVERMONITOR_CLIENT_ID": CLIENT_ID,
        "SERVERMONITOR_CLIENT_SECRET": CLIENT_SECRET,
        "REDIRECT_URI": REDIRECT_URI
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Setup instructions:\n"
            "  1. Create app registration in Azure Portal\n"
            "  2. Add credentials (Client Secret)\n"
            "  3. Configure Redirect URIs\n"
            "  4. Set environment variables"
        )


# ─────────────────────────────────────────────────────────────────────────────
# MSAL CLIENT
# ─────────────────────────────────────────────────────────────────────────────

def get_msal_app() -> msal.PublicClientApplication:
    """Create MSAL public client application."""
    return msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        token_cache=_load_cache()
    )


def _load_cache():
    """Load token cache from session."""
    cache = msal.SerializableTokenCache()
    if "token_cache" in session:
        cache.deserialize(session["token_cache"])
    return cache


def _save_cache(cache):
    """Save token cache to session."""
    if cache.has_state_changed:
        session["token_cache"] = cache.serialize()


# ─────────────────────────────────────────────────────────────────────────────
# AUTHORIZATION CODE FLOW
# ─────────────────────────────────────────────────────────────────────────────

def get_authorization_url() -> Tuple[str, str]:
    """
    Generate authorization URL for user to login.
    
    Returns:
        Tuple of (auth_url, state) for redirecting user
    """
    app = get_msal_app()
    auth_url = app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return auth_url, None


def handle_auth_callback(code: str) -> Optional[Dict]:
    """
    Handle OAuth callback and acquire token.
    
    Args:
        code: Authorization code from Azure AD
    
    Returns:
        Token result dict with access_token and id_token, or None if failed
    """
    app = get_msal_app()
    
    try:
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        if "access_token" in result:
            _save_cache(app.token_cache)
            return result
        else:
            logger.error(f"Token acquisition failed: {result.get('error_description')}")
            return None
            
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return None


def get_token_silently() -> Optional[str]:
    """
    Get access token silently from cache.
    
    Returns:
        Access token or None if not available/expired
    """
    try:
        app = get_msal_app()
        
        # Try silent acquisition
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(
                scopes=SCOPES,
                account=accounts[0]
            )
            
            if result and "access_token" in result:
                _save_cache(app.token_cache)
                return result["access_token"]
        
        return None
    except Exception as e:
        logger.error(f"Silent token acquisition failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# USER & TENANT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_user_info(id_token: str) -> Dict:
    """
    Extract user information from ID token claims.
    
    Args:
        id_token: ID token from Azure AD
    
    Returns:
        Dict with email, name, oid, tenant_id
    """
    # ID token is JWT, decode without verification (assuming Azure signed it)
    import json
    import base64
    
    parts = id_token.split(".")
    if len(parts) != 3:
        return {}
    
    # Decode payload (second part)
    payload = parts[1]
    # Add padding if needed
    padding = 4 - len(payload) % 4
    if padding != 4:
        payload += "=" * padding
    
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
        
        return {
            "email": claims.get("preferred_username") or claims.get("upn"),
            "name": claims.get("name", "").strip(),
            "oid": claims.get("oid"),  # Object ID in Azure AD
            "tenant_id": claims.get("tid"),  # Tenant ID
            "roles": claims.get("roles", []),  # App roles
            "groups": claims.get("groups", [])  # Azure AD groups
        }
    except Exception as e:
        logger.error(f"Failed to extract user info: {e}")
        return {}


def get_user_info_from_graph(access_token: str) -> Optional[Dict]:
    """
    Fetch user profile from Microsoft Graph API.
    
    Args:
        access_token: Access token for Graph API
    
    Returns:
        User profile dict or None
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"{GRAPH_BASE}/me",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Graph API error: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to fetch user info from Graph: {e}")
        return None


def get_user_tenant_from_token(id_token: str) -> Optional[str]:
    """
    Extract tenant ID from ID token.
    
    Args:
        id_token: ID token from Azure AD
    
    Returns:
        Tenant ID or None
    """
    user_info = extract_user_info(id_token)
    return user_info.get("tenant_id")


# ─────────────────────────────────────────────────────────────────────────────
# ROLE MAPPING
# ─────────────────────────────────────────────────────────────────────────────

ROLE_MAPPING = {
    "ServerMonitor.Admin": "super_admin",
    "ServerMonitor.TenantAdmin": "tenant_admin",
    "ServerMonitor.User": "user"
}


def get_user_role(id_token: str, access_token: str) -> str:
    """
    Determine user role from Azure AD claims and group membership.
    
    Args:
        id_token: ID token with claims
        access_token: Access token for Graph API
    
    Returns:
        Role: "super_admin", "tenant_admin", or "user"
    """
    user_info = extract_user_info(id_token)
    
    # Check app roles
    for role in user_info.get("roles", []):
        if role in ROLE_MAPPING:
            return ROLE_MAPPING[role]
    
    # Check group membership
    # (Could fetch from Graph if needed)
    
    # Default to user
    return "user"


# ─────────────────────────────────────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────────────────────────────────────

def require_login(f):
    """Decorator to require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session or "id_token" not in session:
            return redirect(url_for("auth.login"))
        
        # Verify token still valid
        token = get_token_silently()
        if not token:
            return redirect(url_for("auth.login"))
        
        return f(*args, **kwargs)
    return decorated_function


def require_role(required_role: str):
    """
    Decorator to require specific role.
    
    Args:
        required_role: "super_admin", "tenant_admin", or "user"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("auth.login"))
            
            user_role = session.get("user", {}).get("role", "user")
            
            # Role hierarchy
            if required_role == "super_admin" and user_role != "super_admin":
                return {"error": "Unauthorized"}, 403
            elif required_role == "tenant_admin" and user_role not in ["super_admin", "tenant_admin"]:
                return {"error": "Unauthorized"}, 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user() -> Optional[Dict]:
    """Get current logged-in user from session."""
    return session.get("user")


def get_current_tenant() -> Optional[str]:
    """Get current tenant ID from session."""
    user = get_current_user()
    return user.get("tenant_id") if user else None
