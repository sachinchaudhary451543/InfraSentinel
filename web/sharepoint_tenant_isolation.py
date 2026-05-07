"""
SharePoint Tenant Isolation Module
===================================
Ensures each client/tenant has separate data storage on SharePoint.
Implements folder structure: /sites/ServerMonitor/{TenantName}/...

This prevents cross-tenant data visibility and ensures compliance.
"""

import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger("[SHAREPOINT_ISOLATION]")


class SharePointTenantIsolation:
    """Manages tenant-isolated SharePoint storage"""
    
    @staticmethod
    def get_tenant_folder_path(tenant_id: int, tenant_name: str, base_site: str) -> str:
        """
        Get tenant-specific folder path on SharePoint.
        
        Pattern: /sites/ServerMonitor/{Tenant-Name-Sanitized}/
        
        Args:
            tenant_id: Database tenant ID
            tenant_name: Tenant display name
            base_site: Base SharePoint site URL
        
        Returns:
            Tenant-specific folder path
        """
        # Sanitize tenant name for SharePoint folder
        safe_name = "".join(c if c.isalnum() or c in ['-', '_'] else '-' 
                           for c in tenant_name).replace('--', '-')[:100]
        
        return f"/sites/ServerMonitor/{safe_name}"
    
    @staticmethod
    def ensure_tenant_folder_exists(
        tenant_id: int,
        tenant_name: str,
        site_url: str,
        access_token: str
    ) -> bool:
        """
        Create tenant folder structure on SharePoint if it doesn't exist.
        
        Structure created:
        - /{Tenant}/Metrics/
        - /{Tenant}/Screenshots/
        - /{Tenant}/Reports/
        - /{Tenant}/Logs/
        
        Args:
            tenant_id: Database tenant ID
            tenant_name: Tenant display name
            site_url: SharePoint site URL
            access_token: Microsoft Graph API access token
        
        Returns:
            True if folder structure exists/created, False on error
        """
        try:
            tenant_path = SharePointTenantIsolation.get_tenant_folder_path(
                tenant_id, tenant_name, site_url
            )
            
            folders = [
                tenant_path,
                f"{tenant_path}/Metrics",
                f"{tenant_path}/Screenshots",
                f"{tenant_path}/Reports",
                f"{tenant_path}/Logs",
            ]
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Get site ID
            parsed = urlparse(site_url)
            site_id_url = f"https://graph.microsoft.com/v1.0/sites/{parsed.netloc}:{parsed.path}"
            resp = requests.get(site_id_url, headers=headers)
            
            if resp.status_code != 200:
                logger.error(f"Failed to get site ID: {resp.status_code}")
                return False
            
            site_id = resp.json().get('id')
            
            # Create folders
            for folder_path in folders:
                folder_name = folder_path.split('/')[-1]
                
                # Check if folder exists
                check_url = (
                    f"https://graph.microsoft.com/v1.0/sites/{site_id}/"
                    f"drive/root:/{folder_path}?$select=id"
                )
                check_resp = requests.get(check_url, headers=headers)
                
                if check_resp.status_code == 200:
                    logger.debug(f"Folder already exists: {folder_path}")
                    continue
                
                # Create folder
                parent_path = '/'.join(folder_path.split('/')[:-1]) or "/"
                create_url = (
                    f"https://graph.microsoft.com/v1.0/sites/{site_id}/"
                    f"drive/root:/{parent_path}:/children"
                )
                
                create_payload = {
                    "name": folder_name,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename"
                }
                
                create_resp = requests.post(
                    create_url,
                    headers=headers,
                    json=create_payload
                )
                
                if create_resp.status_code in [201, 200]:
                    logger.info(f"✓ Created folder: {folder_path}")
                else:
                    logger.warning(f"Failed to create folder {folder_path}: {create_resp.status_code}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring tenant folder: {e}")
            return False
    
    @staticmethod
    def upload_metric_to_tenant_folder(
        tenant_id: int,
        tenant_name: str,
        site_url: str,
        access_token: str,
        metric_data: Dict,
        server_name: str
    ) -> Optional[str]:
        """
        Upload metric data to tenant-specific SharePoint location.
        
        File path: /{Tenant}/Metrics/{ServerName}_{Timestamp}.json
        
        Args:
            tenant_id: Database tenant ID
            tenant_name: Tenant display name
            site_url: SharePoint site URL
            access_token: Microsoft Graph API access token
            metric_data: Metric data to upload
            server_name: Server name for file naming
        
        Returns:
            SharePoint item ID if successful, None on error
        """
        try:
            tenant_path = SharePointTenantIsolation.get_tenant_folder_path(
                tenant_id, tenant_name, site_url
            )
            
            timestamp = datetime.utcnow().isoformat().replace(':', '-')
            filename = f"{server_name}_{timestamp}.json"
            folder_path = f"{tenant_path}/Metrics"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Get site ID
            parsed = urlparse(site_url)
            site_id_url = f"https://graph.microsoft.com/v1.0/sites/{parsed.netloc}:{parsed.path}"
            resp = requests.get(site_id_url, headers=headers)
            
            if resp.status_code != 200:
                logger.error(f"Failed to get site ID: {resp.status_code}")
                return None
            
            site_id = resp.json().get('id')
            
            # Upload file
            upload_url = (
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/"
                f"drive/root:/{folder_path}/{filename}:/content"
            )
            
            import json
            file_content = json.dumps(metric_data, indent=2)
            
            upload_resp = requests.put(
                upload_url,
                headers={**headers, "Content-Type": "application/json"},
                data=file_content
            )
            
            if upload_resp.status_code in [200, 201]:
                item_id = upload_resp.json().get('id')
                logger.debug(f"✓ Uploaded metric for {server_name}")
                return item_id
            else:
                logger.warning(f"Failed to upload metric: {upload_resp.status_code}")
                return None
            
        except Exception as e:
            logger.error(f"Error uploading metric: {e}")
            return None
    
    @staticmethod
    def list_tenant_items(
        tenant_id: int,
        tenant_name: str,
        site_url: str,
        access_token: str,
        folder: str = "Metrics"
    ) -> List[Dict]:
        """
        List all items in a tenant folder (e.g., all metrics).
        
        Args:
            tenant_id: Database tenant ID
            tenant_name: Tenant display name
            site_url: SharePoint site URL
            access_token: Microsoft Graph API access token
            folder: Folder name (Metrics, Screenshots, Reports, Logs)
        
        Returns:
            List of items in the tenant folder
        """
        try:
            tenant_path = SharePointTenantIsolation.get_tenant_folder_path(
                tenant_id, tenant_name, site_url
            )
            
            folder_path = f"{tenant_path}/{folder}"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Get site ID
            parsed = urlparse(site_url)
            site_id_url = f"https://graph.microsoft.com/v1.0/sites/{parsed.netloc}:{parsed.path}"
            resp = requests.get(site_id_url, headers=headers)
            
            if resp.status_code != 200:
                return []
            
            site_id = resp.json().get('id')
            
            # List files
            list_url = (
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/"
                f"drive/root:/{folder_path}:/children"
            )
            
            list_resp = requests.get(list_url, headers=headers)
            
            if list_resp.status_code == 200:
                items = list_resp.json().get('value', [])
                logger.debug(f"Found {len(items)} items in {folder_path}")
                return items
            else:
                logger.warning(f"Failed to list items: {list_resp.status_code}")
                return []
            
        except Exception as e:
            logger.error(f"Error listing tenant items: {e}")
            return []
    
    @staticmethod
    def validate_tenant_access(
        tenant_id: int,
        site_url: str,
        access_token: str
    ) -> bool:
        """
        Validate that tenant has valid access to SharePoint site.
        
        Returns True if token is valid, False otherwise.
        """
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
            }
            
            # Simple test: Get site info
            parsed = urlparse(site_url)
            site_id_url = f"https://graph.microsoft.com/v1.0/sites/{parsed.netloc}:{parsed.path}"
            resp = requests.get(site_id_url, headers=headers, timeout=10)
            
            return resp.status_code == 200
            
        except Exception as e:
            logger.error(f"Tenant access validation failed: {e}")
            return False
