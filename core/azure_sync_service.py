"""
core/azure_sync_service.py – Background Service for Azure AD Sync
==================================================================

Periodically syncs devices and users from Azure AD to local database.

Service:
  • Runs every N minutes
  • Fetches devices from Microsoft Graph API
  • Fetches users from Microsoft Graph API
  • Stores in local database
  • Maintains device-to-user relationships

Configuration:
  SYNC_INTERVAL_MINUTES - How often to sync (default: 30)
  MAX_WORKERS - Parallel sync threads (default: 4)
"""

import logging
import time
from datetime import datetime
from threading import Thread, Event
from typing import Optional, Any

from auth.entra_auth import get_token_silently, get_msal_app
from core.graph_integration import (
    get_devices_from_graph,
    get_users_from_graph,
    sync_devices_to_database,
    sync_users_to_database
)
from sqlalchemy.exc import OperationalError
from web.models import db, Tenant, AzureDevice, AzureUser, AzureDeviceOwner

logger = logging.getLogger("[AZURE-SYNC]")


class TokenProvider:
    """Manages acquisition, caching, and refresh of Microsoft Graph App access tokens."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.tenant_id = tenant_id.strip()
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def __call__(self, force_refresh: bool = False) -> Optional[str]:
        now = time.time()
        if force_refresh or not self._token or now >= self._expires_at - 300:
            logger.info("Acquiring/refreshing Microsoft Graph App token...")
            url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            try:
                import requests
                response = requests.post(url, data=data, timeout=15)
                response.raise_for_status()
                token_data = response.json()
                self._token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 3600)
                self._expires_at = now + expires_in
                logger.info(f"Successfully obtained app token, expires in {expires_in} seconds.")
            except Exception as e:
                logger.error(f"Failed to obtain Microsoft Graph App token: {e}")
                if not force_refresh and self._token:
                    logger.warning("Using cached/expired Graph App token as fallback.")
                    return self._token
                self._token = None
                self._expires_at = 0.0
        return self._token


class AzureSyncService:
    """Background service that syncs Azure AD data to local database."""
    
    def __init__(self, app, sync_interval_minutes: int = 30):
        """
        Initialize sync service.
        
        Args:
            app: Flask application instance
            sync_interval_minutes: How often to sync (in minutes)
        """
        self.app = app
        self.sync_interval_seconds = sync_interval_minutes * 60
        self.running = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
    
    def start(self):
        """Start the background sync service."""
        if self.running:
            logger.warning("Sync service already running")
            return
        
        self.running = True
        self.stop_event.clear()
        
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()
        
        logger.info(f"Azure sync service started (interval: {self.sync_interval_seconds}s)")
    
    def stop(self):
        """Stop the background sync service."""
        if not self.running:
            return
        
        logger.info("Stopping Azure sync service...")
        self.running = False
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=10)
        
        logger.info("Azure sync service stopped")
    
    def _run(self):
        """Main loop for background sync."""
        while self.running and not self.stop_event.is_set():
            try:
                # Perform sync
                self.sync_all_tenants()
                
                # Wait for next interval
                self.stop_event.wait(self.sync_interval_seconds)
                
            except Exception as e:
                logger.error(f"Sync service error: {e}", exc_info=True)
                # Continue running even if one sync fails
                time.sleep(60)
    
    def sync_all_tenants(self):
        """Sync all registered tenants."""
        with self.app.app_context():
            tenants = Tenant.query.filter_by(azure_registered=True).all()
            
            if not tenants:
                logger.debug("No Azure-registered tenants to sync")
                return
            
            logger.info(f"Syncing {len(tenants)} tenants...")
            
            for tenant in tenants:
                try:
                    self.sync_tenant(tenant)
                except Exception as e:
                    logger.error(f"Failed to sync tenant {tenant.id}: {e}")
    
    def sync_tenant(self, tenant):
        """
        Sync a single tenant using its stored Azure credentials.
        
        Args:
            tenant: Tenant model instance
        """
        logger.info(f"Syncing tenant: {tenant.name}")
        
        cid = (getattr(tenant, 'azure_client_id', None) or '').strip()
        csecret = (getattr(tenant, 'azure_client_secret', None) or '').strip()
        tid = (getattr(tenant, 'azure_tenant_id', None) or '').strip()
        
        if not (cid and csecret and tid):
            logger.warning(
                f"Tenant {tenant.name} sync skipped: "
                "Azure credentials (client_id / client_secret / tenant_id) not configured"
            )
            return
        
        try:
            token_provider = TokenProvider(cid, csecret, tid)
            token = token_provider()
            if not token:
                logger.error(f"Failed to acquire token for tenant {tenant.name}")
                return
            
            self.sync_tenant_with_token(tenant, token_provider)
        except Exception as e:
            logger.error(f"Failed to sync tenant {tenant.id}: {e}", exc_info=True)
        finally:
            try:
                db.session.remove()
            except Exception:
                pass
    
    def sync_tenant_with_token(self, tenant, access_token: Any):
        """
        Sync tenant using provided access token.
        
        Args:
            tenant: Tenant model instance
            access_token: Access token for Microsoft Graph API
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting sync for tenant: {tenant.name}")
        
        try:
            # Fetch devices
            logger.debug(f"Fetching devices for tenant {tenant.id}...")
            devices = get_devices_from_graph(access_token)
            device_count = sync_devices_to_database(devices, tenant.id, db.session)
            logger.info(f"Synced {device_count} devices")
            
            # Fetch users
            logger.debug(f"Fetching users for tenant {tenant.id}...")
            users = get_users_from_graph(access_token)
            user_count = sync_users_to_database(users, tenant.id, db.session)
            logger.info(f"Synced {user_count} users")
            
            # Sync device-to-user relationships (device -> registeredOwners)
            logger.debug(f"Syncing device ownership for tenant {tenant.id}...")
            owner_count = self._sync_user_registered_devices(
                tenant.id,
                devices,
                access_token
            )
            logger.info(f"Synced {owner_count} device-owner relationships")
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Tenant {tenant.name} sync completed in {elapsed:.1f}s: "
                f"{device_count} devices, {user_count} users, {owner_count} owners"
            )
            
            # Phase 2: Run Unified Identity Correlation to resolve backend models
            try:
                from core.identity_correlation import IdentityCorrelationService
                IdentityCorrelationService.resolve_device_ownership(tenant.id)
            except Exception as e:
                logger.error(f"Identity correlation background resolution failed: {e}")
            
            
        except Exception as e:
            logger.error(f"Sync failed for tenant {tenant.name}: {e}", exc_info=True)
    
    def _sync_user_registered_devices(
        self,
        tenant_id: int,
        devices: list,
        access_token: str
    ) -> int:
        """
        Sync device-to-user ownership by querying each device's registeredOwners.
        
        Args:
            tenant_id: Tenant ID
            devices: List of device objects from Graph API
            access_token: Access token
        
        Returns:
            Number of relationships synced
        """
        from core.graph_integration import _make_graph_request
        
        owner_count = 0
        with db.session.no_autoflush:
            local_devices = {
                device.device_id: device
                for device in db.session.query(AzureDevice).filter_by(tenant_id=tenant_id).all()
            }
            local_users = {
                user.user_id: user
                for user in db.session.query(AzureUser).filter_by(tenant_id=tenant_id).all()
            }

        for graph_device in devices:
            try:
                graph_device_id = graph_device.get("id")
                if not graph_device_id:
                    continue

                local_device = local_devices.get(graph_device_id)
                if not local_device:
                    logger.warning("Device owner sync skipped unknown device %s", graph_device_id)
                    continue

                result = _make_graph_request(
                    f"/devices/{graph_device_id}/registeredOwners",
                    access_token
                )

                if result is None:
                    logger.warning("Device owner sync preserved existing owners after failed Graph response for %s", graph_device_id)
                    continue

                owners = result.get("value", [])
                with db.session.no_autoflush:
                    db.session.query(AzureDeviceOwner).filter_by(
                        tenant_id=tenant_id,
                        device_id=local_device.id,
                    ).delete()

                for owner in owners:
                    try:
                        graph_user_id = owner.get("id")
                        if not graph_user_id:
                            continue

                        local_user = local_users.get(graph_user_id)
                        if not local_user:
                            logger.warning(
                                "Device owner sync skipped unknown user %s for device %s",
                                graph_user_id,
                                graph_device_id,
                            )
                            continue

                        relationship = AzureDeviceOwner(
                            tenant_id=tenant_id,
                            device_id=local_device.id,
                            user_id=local_user.id,
                            owner_type="registeredOwner",
                            linked_at=datetime.utcnow()
                        )
                        db.session.add(relationship)
                        owner_count += 1

                    except Exception as e:
                        logger.warning("Failed to sync owner %s for device %s: %s", owner.get("id"), graph_device_id, e)
                        try:
                            db.session.rollback()
                        except Exception:
                            pass

            except Exception as e:
                logger.warning("Failed to sync registered owners for device %s: %s", graph_device.get("id"), e)
                try:
                    db.session.rollback()
                except Exception:
                    pass

        for attempt in range(3):
            try:
                db.session.commit()
                break
            except OperationalError as exc:
                message = str(exc).lower()
                db.session.rollback()
                if 'database is locked' in message and attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue
                logger.error(f"Failed to commit device-owner sync: {exc}")
                break
            except Exception as exc:
                logger.error(f"Failed to commit device-owner sync: {exc}")
                db.session.rollback()
                break

        return owner_count


# Global service instance
_sync_service: Optional[AzureSyncService] = None


def init_sync_service(app, sync_interval_minutes: int = 30) -> AzureSyncService:
    """
    Initialize the Azure sync service.
    
    Args:
        app: Flask application
        sync_interval_minutes: Sync interval in minutes
    
    Returns:
        AzureSyncService instance
    """
    global _sync_service
    
    _sync_service = AzureSyncService(app, sync_interval_minutes)
    _sync_service.start()
    
    return _sync_service


def get_sync_service() -> Optional[AzureSyncService]:
    """Get the global sync service instance."""
    return _sync_service


def stop_sync_service():
    """Stop the sync service."""
    global _sync_service
    
    if _sync_service:
        _sync_service.stop()
        _sync_service = None
