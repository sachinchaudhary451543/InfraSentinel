"""
auth/multi_tenant_auth.py – ServerMonitor ISV
===============================================
DROP-IN REPLACEMENT (backward-compat shim).

All existing imports like:
    from auth.multi_tenant_auth import get_tenant_config, encrypt_config, decrypt_config
continue to work without ANY change in calling code.

The actual implementation now lives in auth/msal_auth.py (OAuth, no client_secret).
"""

from auth.msal_auth import (          # noqa: F401
    get_valid_token,
    get_stored_tenant_id,
    get_tenant_config,
    encrypt_config,
    decrypt_config,
    clear_token_cache,
)

__all__ = [
    "get_valid_token",
    "get_stored_tenant_id",
    "get_tenant_config",
    "encrypt_config",
    "decrypt_config",
    "clear_token_cache",
]
