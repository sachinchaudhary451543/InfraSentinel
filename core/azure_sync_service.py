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
from typing import Optional

from auth.entra_auth import get_token_silently, get_msal_app
from core.graph_integration import (
    get_devices_from_graph,
    get_users_from_graph,
    get_device_owners,
    sync_devices_to_database,
    sync_users_to_database
)
from web.models import db, Tenant, AzureDevice, AzureUser, AzureDeviceOwner

logger = logging.getLogger("[AZURE-SYNC]")


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
        Sync a single tenant.
        
        Args:
            tenant: Tenant model instance
        """
        logger.info(f"Syncing tenant: {tenant.name}")
        
        # Get access token for this tenant
        # (This would need to use the tenant's Azure credentials)
        # For now, assume we have the token from user session
        
        # In a real scenario, you'd use the tenant's service principal
        # credentials stored in Tenant.azure_client_id, etc.
        
        try:
            # Get token (placeholder - would use tenant's credentials)
            # token = self._get_tenant_token(tenant)
            
            # For now, skip if we can't get a token
            logger.warning(
                f"Tenant {tenant.name} sync skipped: "
                "Service principal setup needed"
            )
            return
            
        except Exception as e:
            logger.error(f"Failed to get token for tenant {tenant.id}: {e}")
            return
    
    def sync_tenant_with_token(self, tenant, access_token: str):
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
            
            # Sync device-to-user relationships
            logger.debug(f"Syncing device owners for tenant {tenant.id}...")
            owner_count = self._sync_device_owners(
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
            
        except Exception as e:
            logger.error(f"Sync failed for tenant {tenant.name}: {e}", exc_info=True)
    
    def _sync_device_owners(
        self,
        tenant_id: int,
        devices: list,
        access_token: str
    ) -> int:
        """
        Sync device-to-user ownership relationships.
        
        Args:
            tenant_id: Tenant ID
            devices: List of device objects from Graph API
            access_token: Access token
        
        Returns:
            Number of relationships synced
        """
        owner_count = 0
        
        for device in devices:
            try:
                device_id = device.get("id")
                
                # Get device owners from Graph API
                owners = get_device_owners(device_id, access_token)
                
                for owner in owners:
                    try:
                        owner_id = owner.get("id")
                        owner_type = owner.get("@odata.type", "").split(".")[-1].lower()
                        
                        # Check if relationship already exists
                        existing = AzureDeviceOwner.query.filter_by(
                            tenant_id=tenant_id,
                            device_id=device_id,
                            user_id=owner_id
                        ).first()
                        
                        if not existing:
                            # Create relationship
                            relationship = AzureDeviceOwner(
                                tenant_id=tenant_id,
                                device_id=device_id,
                                user_id=owner_id,
                                owner_type=owner_type or "primary"
                            )
                            db.session.add(relationship)
                            owner_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to sync owner {owner.get('id')}: {e}")
                
                db.session.commit()
                
            except Exception as e:
                logger.warning(f"Failed to sync owners for device {device_id}: {e}")
                db.session.rollback()
        
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
