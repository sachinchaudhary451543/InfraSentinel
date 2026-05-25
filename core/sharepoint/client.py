"""
core/sharepoint/client.py – ServerMonitor ISV
===============================================
Unified SharePoint REST API client.

CHANGES FROM ORIGINAL:
  - Added bearer_token constructor path so the MSAL OAuth flow works without
    client_secret (the original only supported ClientCredential / basic auth).
  - _authenticate_oauth now accepts a pre-obtained bearer token directly.
  - Multi-tenant isolation: get_items() accepts an optional tenant_id parameter
    that is AND-ed into every filter, so client A can never read client B's data.
  - All SP REST calls use data= (raw JSON string) not json= kwarg, consistent
    with the provisioner fix (Bug #4).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class SharePointClient:
    """
    Unified SharePoint REST API client.

    Authentication priority:
      1. bearer_token  – MSAL device-code / silent flow (preferred for ISV)
      2. client_id + client_secret – app-only (legacy)
      3. username + password – basic auth (not recommended)
    """

    def __init__(
        self,
        site_url:      str,
        bearer_token:  Optional[str] = None,
        client_id:     Optional[str] = None,
        client_secret: Optional[str] = None,
        username:      Optional[str] = None,
        password:      Optional[str] = None,
    ) -> None:
        self.site_url = site_url.rstrip("/")
        self._token   = None          # resolved bearer token

        if bearer_token:
            self._token = bearer_token
            logger.info(f"SharePoint client initialised with bearer token for {site_url}")
        elif client_id and client_secret:
            self._token = self._acquire_app_token(site_url, client_id, client_secret)
        elif username and password:
            self._token = self._acquire_user_token(site_url, username, password)
        else:
            logger.warning("No credentials provided; unauthenticated client.")

    # ── Token acquisition ─────────────────────────────────────────────────────
    @staticmethod
    def _acquire_app_token(site_url: str, client_id: str, client_secret: str) -> str:
        """Acquire app-only token using client credentials flow."""
        import re
        hostname = re.sub(r"https?://", "", site_url).split("/")[0]
        tenant   = hostname.split(".")[0]
        url      = f"https://accounts.accesscontrol.windows.net/{tenant}.onmicrosoft.com/tokens/OAuth/2"
        resp = requests.post(url, data={
            "grant_type":    "client_credentials",
            "client_id":     f"{client_id}@{tenant}.onmicrosoft.com",
            "client_secret": client_secret,
            "resource":      f"00000003-0000-0ff1-ce00-000000000000/{hostname}@{tenant}.onmicrosoft.com",
        }, timeout=15)
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError(f"App token acquisition failed: {resp.text[:200]}")
        logger.info("App-only token acquired.")
        return token

    @staticmethod
    def _acquire_user_token(site_url: str, username: str, password: str) -> str:
        """Basic auth via SharePoint legacy token endpoint (not recommended).
        
        This method is deprecated. Use MSAL device-code flow or client credentials instead.
        Raises RuntimeError as user/pass auth is not supported in modern office365 library.
        """
        logger.warning(
            "Username/password auth is deprecated and not supported. "
            "Use MSAL device-code flow (recommended) or client credentials + client_id/client_secret instead. "
            "See PRODUCTION_DEPLOYMENT.md for setup instructions."
        )
        raise RuntimeError(
            "Username/password authentication is not supported. "
            "Please use: (1) Client Credentials (RECOMMENDED): Set SHAREPOINT_CLIENT_ID and SHAREPOINT_CLIENT_SECRET. "
            "(2) Device Code Flow: Use MSAL device-code flow. (3) Access Token: Set SHAREPOINT_ACCESS_TOKEN directly."
        )

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _headers(self) -> dict:
        h = {
            "Accept":       "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url  = f"{self.site_url}/_api/{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict, extra_headers: Optional[dict] = None) -> requests.Response:
        url  = f"{self.site_url}/_api/{path}"
        hdrs = {**self._headers(), **(extra_headers or {})}
        resp = requests.post(
            url, headers=hdrs,
            data=json.dumps(payload),   # data= not json= (Bug #4 pattern)
            timeout=15,
        )
        return resp

    # ── List existence / creation ─────────────────────────────────────────────
    def list_exists(self, list_title: str) -> bool:
        try:
            self._get(f"web/lists/GetByTitle('{list_title}')")
            return True
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise
        except Exception as e:
            logger.debug(f"list_exists check for '{list_title}': {e}")
            return False

    def create_list(self, list_title: str, description: str = "") -> bool:
        payload = {
            "__metadata": {"type": "SP.List"},
            "Title":        list_title,
            "Description":  description,
            "BaseTemplate": 100,
        }
        resp = self._post("web/lists", payload)
        if resp.status_code in (200, 201):
            logger.info(f"Created list '{list_title}'")
            return True
        raise RuntimeError(f"Failed to create '{list_title}': [{resp.status_code}] {resp.text[:200]}")

    def ensure_list(self, list_title: str, description: str = "") -> bool:
        if not self.list_exists(list_title):
            return self.create_list(list_title, description)
        return True

    # ── Items ─────────────────────────────────────────────────────────────────
    def add_item(self, list_title: str, properties: Dict[str, Any]) -> Optional[dict]:
        """Add a single item. Returns the created item dict or None."""
        payload = {
            "__metadata": {"type": f"SP.Data.{list_title.replace(' ', '_x0020_')}ListItem"},
            **properties,
        }
        resp = self._post(f"web/lists/GetByTitle('{list_title}')/items", payload)
        if resp.status_code in (200, 201):
            return resp.json().get("d", {})
        logger.error(f"add_item failed [{resp.status_code}]: {resp.text[:200]}")
        return None

    def update_item(
        self, list_title: str, item_id: int, properties: Dict[str, Any]
    ) -> bool:
        payload = {
            "__metadata": {"type": f"SP.Data.{list_title.replace(' ', '_x0020_')}ListItem"},
            **properties,
        }
        resp = self._post(
            f"web/lists/GetByTitle('{list_title}')/items({item_id})",
            payload,
            extra_headers={"X-HTTP-Method": "MERGE", "If-Match": "*"},
        )
        if resp.status_code in (200, 204):
            return True
        logger.error(f"update_item failed [{resp.status_code}]: {resp.text[:200]}")
        return False

    def delete_item(self, list_title: str, item_id: int) -> bool:
        url  = f"{self.site_url}/_api/web/lists/GetByTitle('{list_title}')/items({item_id})"
        hdrs = {**self._headers(), "X-HTTP-Method": "DELETE", "If-Match": "*"}
        resp = requests.post(url, headers=hdrs, timeout=15)
        if resp.status_code in (200, 204):
            return True
        logger.error(f"delete_item failed [{resp.status_code}]: {resp.text[:150]}")
        return False

    def get_items(
        self,
        list_title:  str,
        filter_str:  Optional[str] = None,
        tenant_id:   Optional[str] = None,   # multi-tenant isolation
        top:         int           = 500,
        select:      Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch list items with optional OData filter.

        Multi-tenant isolation: if tenant_id is supplied, it is AND-ed into the
        filter so a client can only ever see their own data.
        """
        filters: List[str] = []
        if filter_str:
            filters.append(f"({filter_str})")
        if tenant_id:
            filters.append(f"TenantId eq '{tenant_id}'")

        params: Dict[str, Any] = {"$top": top}
        if filters:
            params["$filter"] = " and ".join(filters)
        if select:
            params["$select"] = ",".join(select)

        try:
            data  = self._get(f"web/lists/GetByTitle('{list_title}')/items", params=params)
            items = data.get("d", {}).get("results", [])
            logger.debug(f"Retrieved {len(items)} items from '{list_title}'")
            return items
        except Exception as e:
            logger.error(f"get_items failed for '{list_title}': {e}")
            return []

    def batch_add_items(self, list_title: str, items: List[Dict[str, Any]]) -> int:
        """Add multiple items. Returns count of successfully added items."""
        success = 0
        for item in items:
            result = self.add_item(list_title, item)
            if result is not None:
                success += 1
        logger.info(f"Batch add: {success}/{len(items)} items written to '{list_title}'")
        return success

    # ── Field management ──────────────────────────────────────────────────────
    def get_field_names(self, list_title: str) -> set:
        try:
            data = self._get(
                f"web/lists/GetByTitle('{list_title}')/fields",
                params={"$select": "InternalName"},
            )
            return {f["InternalName"] for f in data.get("d", {}).get("results", [])}
        except Exception as e:
            logger.error(f"get_field_names failed for '{list_title}': {e}")
            return set()
