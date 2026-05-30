"""
SharePoint Sync Service - Enterprise Graph Edition (Client Credentials)
Exports metrics, VMs, and logs to SharePoint for cold storage and reporting.
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import requests

from web.models import db, Server, Metric, VM, AuditLog, Tenant, SyncNotification
from core.azure_graph import _get_token_for_tenant

logger = logging.getLogger("sharepoint_sync")


def _create_sync_notification(tenant_id: int, category: str, title: str, message: str, breakdown: dict):
    """Create a sync notification record for the notification bell"""
    try:
        notif = SyncNotification(
            tenant_id=tenant_id,
            category=category,
            title=title,
            message=message,
            breakdown=json.dumps(breakdown) if breakdown else None,
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()
        
        # Prune old notifications (keep latest 50 per tenant)
        old_ids = db.session.query(SyncNotification.id).filter_by(
            tenant_id=tenant_id
        ).order_by(SyncNotification.created_at.desc()).offset(50).all()
        if old_ids:
            db.session.query(SyncNotification).filter(
                SyncNotification.id.in_([r[0] for r in old_ids])
            ).delete(synchronize_session=False)
            db.session.commit()
    except Exception as e:
        logger.debug(f"Failed to create sync notification: {e}")
        try:
            db.session.rollback()
        except:
            pass

class SharePointSyncService:
    """
    Syncs ServerMonitor data to SharePoint Lists via Microsoft Graph.
    Uses Application Permissions (Client Credentials).
    """

    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.token = _get_token_for_tenant(tenant)
        self.site_url = tenant.sharepoint_site_url
        self.site_id = None
        
        if self.token and self.site_url:
            self.headers = {
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            # Attempt to resolve site ID from URL
            self._resolve_site_id()
        elif not self.token:
            logger.warning(f"[SharePoint Init] No auth token for tenant '{tenant.name}' - Azure credentials may be missing or invalid")
        elif not self.site_url:
            logger.warning(f"[SharePoint Init] No SharePoint site URL configured for tenant '{tenant.name}'")

    def _resolve_site_id(self):
        """Resolves SharePoint Site ID from the provided URL using Graph"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.site_url)
            hostname = parsed.netloc
            site_path = parsed.path.strip('/')
            
            # site_path for root is empty, for subsite it's 'sites/name'
            # Graph format: hostname:/sites/name
            lookup_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:/{site_path}"
            logger.debug(f"[SharePoint] Resolving site ID via Graph: {lookup_url}")
            
            resp = requests.get(lookup_url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                self.site_id = resp.json().get('id')
                logger.info(f"[SharePoint] Successfully resolved Site ID for tenant '{self.tenant.name}': {self.site_id}")
            else:
                logger.error(f"[SharePoint] Failed to resolve site ID for URL '{self.site_url}': HTTP {resp.status_code} - {resp.text[:300]}")
        except Exception as e:
            logger.error(f"[SharePoint] Error resolving site ID for tenant '{self.tenant.name}': {e}", exc_info=True)

    def _ensure_list(self, list_name: str) -> bool:
        """Checks if a list exists, or creates it"""
        if not self.site_id: 
            raise Exception("SharePoint Site ID is missing. Cannot ensure list.")
            
        try:
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/{list_name}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                return True
            elif resp.status_code == 403:
                raise Exception(f"Access Denied (403) reading list '{list_name}'. Please ensure Azure AD App has 'Sites.Manage.All' or 'Sites.ReadWrite.All'.")
            
            # Auto-create list
            logger.warning(f"List {list_name} not found in site {self.site_id}. Attempting to create it...")
            create_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists"
            payload = {
                "displayName": list_name,
                "columns": [],
                "list": {
                    "template": "genericList"
                }
            }
            
            if list_name == 'Metrics':
                payload["columns"] = [
                    {"name": "ServerName", "text": {}},
                    {"name": "CPU", "number": {}},
                    {"name": "RAM", "number": {}},
                    {"name": "Disk", "number": {}},
                    {"name": "Timestamp", "dateTime": {}}
                ]
            elif list_name == 'VMs':
                payload["columns"] = [
                    {"name": "HostServer", "text": {}},
                    {"name": "State", "text": {}},
                    {"name": "CPUUsage", "number": {}},
                    {"name": "Memory", "number": {}}
                ]
            elif list_name == 'Activity':
                payload["columns"] = [
                    {"name": "ServerName", "text": {}},
                    {"name": "User", "text": {}},
                    {"name": "App", "text": {}},
                    {"name": "WindowTitle", "text": {}},
                    {"name": "IdleTime", "number": {}},
                    {"name": "Timestamp", "dateTime": {}}
                ]
            elif list_name == 'Logs':
                payload["columns"] = [
                    {"name": "Resource", "text": {}},
                    {"name": "Message", "text": {}},
                    {"name": "Severity", "text": {}},
                    {"name": "Timestamp", "dateTime": {}}
                ]
            elif list_name == 'Employees':
                payload["columns"] = [
                    {"name": "Email", "text": {}},
                    {"name": "Department", "text": {}},
                    {"name": "Designation", "text": {}},
                    {"name": "LocalUsername", "text": {}},
                    {"name": "Status", "text": {}}
                ]

            resp = requests.post(create_url, headers=self.headers, json=payload, timeout=25)
            if resp.status_code in [200, 201]:
                logger.info(f"Created list {list_name} successfully.")
                return True
            elif resp.status_code == 403:
                raise Exception(f"Access Denied (403) creating list '{list_name}'. Please ensure Azure AD App has 'Sites.Manage.All' permissions.")
            else:
                logger.error(f"Failed to create list {list_name}: {resp.text}")
                raise Exception(f"Failed to create list '{list_name}': {resp.status_code} - {resp.text[:100]}")
                
        except requests.Timeout:
            logger.error(f"Timeout ensuring list {list_name}")
            raise Exception(f"Microsoft Graph API timed out while trying to access/create list '{list_name}'.")
        except Exception as e:
            logger.error(f"Error ensuring list {list_name}: {e}")
            raise e

    def sync_metrics_batch(self, minutes: int = 5) -> int:
        """Batch sync aggregated metrics for the last N minutes"""
        if not self.site_id: return 0
        
        # Prevent 404 infinite loops if list is not configured
        if not self._ensure_list("Metrics"):
            logger.error("SharePoint list 'Metrics' not found. Skipping sync.")
            return 0
            
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        # In a real SaaS, we would track 'last_synced_id'
        metrics = Metric.query.join(Server).filter(
            Server.tenant_id == self.tenant.id,
            Metric.timestamp >= cutoff
        ).all()

        synced = 0
        logger.info(f"Starting metrics sync for tenant {self.tenant.id}. Found {len(metrics)} metrics.")
        
        for m in metrics:
            payload = {
                "fields": {
                    "Title": f"{m.server.hostname} - {m.timestamp.isoformat()}",
                    "ServerName": m.server.hostname,
                    "CPU": m.cpu_util_percent,
                    "RAM": m.ram_util_percent,
                    "Disk": m.ssd_util_percent,
                    "Timestamp": m.timestamp.isoformat()
                }
            }
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/Metrics/items"
            try:
                resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
                if resp.status_code in [201, 200]:
                    synced += 1
                else:
                    logger.error(f"Failed to sync metric {m.id}: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"Error syncing {m.id}: {e}")
        
        return synced

    def sync_vms_snapshot(self) -> int:
        """Sync current VM state snapshot"""
        if not self.site_id: return 0
        
        if not self._ensure_list("VMs"):
            logger.error("SharePoint list 'VMs' not found. Skipping sync.")
            return 0
        
        # Get all current VMs for tenant
        vms = VM.query.join(Server).filter(Server.tenant_id == self.tenant.id).all()
        
        synced = 0
        for v in vms:
            payload = {
                "fields": {
                    "Title": v.name or v.vm_name or 'Unknown',
                    "HostServer": v.host_server.hostname if v.host_server else 'Unknown',
                    "State": v.state,
                    "CPUUsage": v.cpu or v.cpu_usage or 0,
                    "Memory": v.ram or v.memory_assigned or 0
                }
            }
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/VMs/items"
            try:
                resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
                if resp.status_code in [201, 200]:
                    synced += 1
            except Exception:
                pass
        return synced

    def sync_activity_batch(self, minutes: int = 5) -> int:
        """Sync employee activity logs"""
        if not self.site_id: return 0
        
        if not self._ensure_list("Activity"):
            logger.debug("SharePoint list 'Activity' not found or not configured. Skipping activity sync.")
            return 0
            
        from web.models import EmployeeActivity
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        activities = EmployeeActivity.query.join(Server).filter(
            Server.tenant_id == self.tenant.id,
            EmployeeActivity.timestamp >= cutoff
        ).all()

        synced = 0
        for a in activities:
            try:
                server = db.session.get(Server, a.server_id) if a.server_id else None
                server_name = server.hostname if server else 'Unknown'
                payload = {
                    "fields": {
                        "Title": f"{a.user} - {a.app}",
                        "ServerName": server_name,
                        "User": a.user,
                        "App": a.app,
                        "WindowTitle": a.window_title,
                        "IdleTime": a.idle_time,
                        "Timestamp": a.timestamp.isoformat()
                    }
                }
                url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/Activity/items"
                resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
                if resp.status_code in [201, 200]: synced += 1
            except Exception as e:
                logger.debug(f"Failed to sync activity: {e}")
        return synced

    def sync_screenshots_batch(self, minutes: int = 5) -> int:
        """Sync recently captured screenshots to SharePoint"""
        if not self.site_id: return 0
        from web.models import Screenshot
        import os
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        screenshots = Screenshot.query.filter(
            Screenshot.tenant_id == self.tenant.id,
            Screenshot.captured_at >= cutoff,
            Screenshot.sharepoint_url == None
        ).all()

        synced = 0
        for ss in screenshots:
            local_path = ss.local_file_path
            if not local_path or not os.path.exists(local_path):
                continue
                
            try:
                with open(local_path, 'rb') as f:
                    file_bytes = f.read()
                    
                filename = os.path.basename(local_path)
                # Use hostname from screenshot directly (already stored during capture)
                hostname = ss.hostname or ss.server.hostname or 'Unknown'
                web_url = self.upload_screenshot(file_bytes, filename, hostname)
                
                if web_url:
                    ss.sharepoint_url = web_url
                    db.session.commit()
                    synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync screenshot {ss.id}: {e}")
                if "Access Denied" in str(e) or "403" in str(e):
                    raise Exception(f"SharePoint Screenshot Upload Failed: {str(e)}")
        return synced

    def sync_logs_instant(self, minutes: int = 15) -> int:
        """Sync recent audit/agent logs"""
        if not self.site_id: return 0
        
        if not self._ensure_list("Logs"):
            logger.error("SharePoint list 'Logs' not found. Skipping sync.")
            return 0
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        logs = AuditLog.query.filter(
            AuditLog.tenant_id == self.tenant.id,
            AuditLog.timestamp >= cutoff,
            AuditLog.user == 'SystemAgent'
        ).all()

        synced = 0
        for l in logs:
            payload = {
                "fields": {
                    "Title": l.action,
                    "Resource": l.resource,
                    "Message": l.details,
                    "Severity": "Info", # Maps to enterprise requirements
                    "Timestamp": l.timestamp.isoformat()
                }
            }
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/Logs/items"
            resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if resp.status_code in [201, 200]:
                synced += 1
        return synced

    def sync_employees(self) -> int:
        """Sync employee/identity directory to SharePoint for reporting"""
        if not self.site_id: return 0
        
        from web.models import Employee, EmployeeAssetLog
        employees = Employee.query.filter_by(tenant_id=self.tenant.id).all()
        
        # Build list of unique emails to sync
        employee_data = {}
        for emp in employees:
            employee_data[emp.email.lower()] = {
                "Title": emp.name,
                "Email": emp.email,
                "Department": emp.department or 'N/A',
                "Designation": emp.designation or 'N/A',
                "LocalUsername": emp.local_username or 'N/A',
                "Status": "Active" if emp.is_active else "Inactive"
            }
            
        # Add auto-discovered employees from agents
        discovered_logs = EmployeeAssetLog.query.filter_by(tenant_id=self.tenant.id).all()
        for log in discovered_logs:
            email = log.employee_email.lower()
            if email not in employee_data:
                employee_data[email] = {
                    "Title": log.employee_email.split('@')[0],
                    "Email": log.employee_email,
                    "Department": "Auto-Discovered",
                    "Designation": "N/A",
                    "LocalUsername": log.hostname or 'N/A',
                    "Status": "Active"
                }
                
        if not employee_data:
            return 0
            
        # Only ensure list if there's actually data to sync
        self._ensure_list("Employees")

        synced = 0
        for email, emp_dict in employee_data.items():
            payload = { "fields": emp_dict }
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/Employees/items"
            resp = requests.post(url, headers=self.headers, json=payload, timeout=20)
            if resp.status_code in [201, 200]:
                synced += 1
        return synced


    def upload_screenshot(self, file_bytes, filename, hostname):
        """
        Upload a screenshot image to a SharePoint Document Library.
        Path: ServerMonitor/Screenshots/{hostname}/{filename}
        Returns the SharePoint web URL of the uploaded file, or None on failure.
        Includes retry logic for transient failures and better error handling.
        """
        if not self.site_id:
            logger.warning("Cannot upload screenshot: no site_id resolved")
            return None

        try:
            safe_hostname = (hostname or 'Unknown').replace(' ', '_').replace('/', '_')
            safe_tenant = (self.tenant.name or 'UnknownOrg').replace(' ', '_').replace('/', '_')
            upload_path = f"ServerMonitor/{safe_tenant}/Screenshots/{safe_hostname}/{filename}"
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive/root:/{upload_path}:/content"

            # Retry logic for transient failures
            max_retries = 3
            retry_count = 0
            last_error = None

            while retry_count < max_retries:
                try:
                    # Refresh token on each attempt to handle expired tokens
                    if retry_count > 0:
                        self.token = _get_token_for_tenant(self.tenant)
                        if not self.token:
                            logger.error("Failed to refresh SharePoint auth token")
                            return None

                    headers = {
                        'Authorization': f'Bearer {self.token}',
                        'Content-Type': 'image/jpeg'
                    }

                    resp = requests.put(url, headers=headers, data=file_bytes, timeout=30)

                    if resp.status_code in [200, 201]:
                        result = resp.json()
                        web_url = result.get('webUrl', '')
                        logger.info(f"Screenshot uploaded: {upload_path} -> {web_url}")
                        return web_url
                    elif resp.status_code == 403:
                        # 403 suggests permission issue
                        last_error = f"Access Denied (403) - Please ensure the Azure AD App has 'Sites.ReadWrite.All' or 'Files.ReadWrite.All' Application permissions. Response: {resp.text[:200]}"
                        logger.warning(f"Attempt {retry_count + 1}: {last_error}")
                        retry_count += 1
                        if retry_count < max_retries:
                            import time
                            time.sleep(1)  # Wait before retry
                        continue
                    elif resp.status_code in [500, 502, 503, 504]:
                        # Service error, retry
                        last_error = f"Service Error ({resp.status_code}) - retrying"
                        logger.warning(f"Attempt {retry_count + 1}: {last_error}")
                        retry_count += 1
                        if retry_count < max_retries:
                            import time
                            time.sleep(2)  # Wait longer for service errors
                        continue
                    else:
                        logger.error(f"Screenshot upload failed ({resp.status_code}): {resp.text[:500]}")
                        return None
                        
                except requests.Timeout:
                    last_error = "Request timeout"
                    logger.warning(f"Attempt {retry_count + 1}: {last_error}")
                    retry_count += 1
                    if retry_count < max_retries:
                        import time
                        time.sleep(1)
                    continue
                except requests.RequestException as req_err:
                    last_error = f"Request error: {str(req_err)}"
                    logger.warning(f"Attempt {retry_count + 1}: {last_error}")
                    retry_count += 1
                    if retry_count < max_retries:
                        import time
                        time.sleep(1)
                    continue

            # All retries failed
            logger.error(f"Screenshot upload failed after {max_retries} attempts. Last error: {last_error}")
            raise Exception(last_error or "Screenshot upload failed.")

        except Exception as e:
            logger.error(f"Screenshot upload error: {e}", exc_info=True)
            raise e

def sync_all_tenants():
    """Background Job entry point - Syncs all enabled tenants"""
    logger.info("[SharePoint Sync] Starting sync cycle for all tenants")
    tenants = Tenant.query.filter_by(sharepoint_connected=True, sharepoint_auto_sync=True).all()
    results = []
    
    if not tenants:
        logger.info("[SharePoint Sync] No tenants enabled for auto-sync")
        return results
    
    logger.info(f"[SharePoint Sync] Found {len(tenants)} tenants to sync")
    
    for t in tenants:
        try:
            # Check interval
            interval = t.sharepoint_sync_interval_minutes or 60
            
            # Check if it's time to sync
            now = datetime.utcnow()
            if t.last_sharepoint_sync_timestamp:
                time_since_last_sync = (now - t.last_sharepoint_sync_timestamp).total_seconds() / 60.0
                if time_since_last_sync < interval:
                    # Not time yet
                    logger.debug(f"[SharePoint Sync] Tenant '{t.name}' sync skipped (last sync: {time_since_last_sync:.1f} mins ago, interval: {interval} mins)")
                    continue
            
            logger.info(f"[SharePoint Sync] Processing tenant: {t.name}")
            
            # Use interval for batching to ensure we cover the period since the last sync
            # To be safe, we add a small buffer (e.g. +5 mins) if they had downtime
            batch_minutes = interval + 5

            service = SharePointSyncService(t)
            if not service.token:
                logger.error(f"[SharePoint Sync] No token obtained for tenant '{t.name}' - check Azure AD app configuration")
                continue
            
            if not service.site_id:
                logger.error(f"[SharePoint Sync] Could not resolve SharePoint site ID for tenant '{t.name}' - check site URL")
                continue
            
            # Sync all data types safely
            m_count, v_count, a_count, s_count, l_count, e_count = 0, 0, 0, 0, 0, 0
            
            try:
                logger.info(f"[SharePoint Sync] Syncing metrics (last {batch_minutes} minutes)...")
                m_count = service.sync_metrics_batch(minutes=batch_minutes)
            except Exception as e:
                logger.error(f"[SharePoint Sync] Metrics failed: {e}")
                db.session.rollback()
                
            try:
                logger.info(f"[SharePoint Sync] Syncing VM snapshots...")
                v_count = service.sync_vms_snapshot()
            except Exception as e:
                logger.error(f"[SharePoint Sync] VMs failed: {e}")
                db.session.rollback()
                
            try:
                logger.info(f"[SharePoint Sync] Syncing activity logs...")
                a_count = service.sync_activity_batch(minutes=batch_minutes)
            except Exception as e:
                logger.error(f"[SharePoint Sync] Activity failed: {e}")
                db.session.rollback()
                
            try:
                logger.info(f"[SharePoint Sync] Syncing screenshots...")
                s_count = service.sync_screenshots_batch(minutes=batch_minutes)
            except Exception as e:
                logger.error(f"[SharePoint Sync] Screenshots failed: {e}")
                db.session.rollback()
                
            try:
                logger.info(f"[SharePoint Sync] Syncing audit logs...")
                l_count = service.sync_logs_instant(minutes=batch_minutes)
            except Exception as e:
                logger.error(f"[SharePoint Sync] Audit logs failed: {e}")
                db.session.rollback()
                
            try:
                logger.info(f"[SharePoint Sync] Syncing employee directory...")
                e_count = service.sync_employees()
            except Exception as e:
                logger.error(f"[SharePoint Sync] Employees failed: {e}")
                db.session.rollback()
            
            # Update last sync timestamp
            t.previous_sharepoint_sync_timestamp = t.last_sharepoint_sync_timestamp
            t.last_sharepoint_sync_timestamp = now
            db.session.commit()
            
            result = {
                'tenant': t.name,
                'metrics': m_count,
                'vms': v_count,
                'activity': a_count,
                'screenshots': s_count,
                'logs': l_count,
                'employees': e_count
            }
            results.append(result)
            
            total_items = m_count + v_count + a_count + s_count + l_count + e_count
            logger.info(f"[SharePoint Sync] Tenant '{t.name}' sync completed: {total_items} total items synced (Metrics: {m_count}, VMs: {v_count}, Activity: {a_count}, Screenshots: {s_count}, Logs: {l_count}, Employees: {e_count})")
            
            # Create notification for background sync
            _create_sync_notification(t.id, 'sync',
                f'Auto-sync completed for {t.name}',
                f"Synced {total_items} items ({m_count} metrics, {a_count} activity, {s_count} screenshots, {l_count} logs, {v_count} VMs, {e_count} employees)",
                result)
            
        except Exception as e:
            logger.error(f"[SharePoint Sync] Sync failed for tenant '{t.name}': {str(e)}", exc_info=True)
            try:
                _create_sync_notification(t.id, 'error',
                    f'Auto-sync failed for {t.name}',
                    str(e), {})
            except:
                pass
            try:
                db.session.rollback()
            except:
                pass
            
    logger.info(f"[SharePoint Sync] Sync cycle completed: {len(results)} tenants processed")
    return results


def force_sync_tenant(tenant_id: int) -> Dict[str, Any]:
    """
    Force immediate sync for a specific tenant (bypasses interval check)
    Useful for testing and manual sync operations
    """
    logger.info(f"[SharePoint Sync] Force sync initiated for tenant_id={tenant_id}")
    
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found")
            return {'success': False, 'error': 'Tenant not found'}
        
        if not tenant.sharepoint_connected:
            logger.warning(f"Tenant {tenant.name} is not configured for SharePoint")
            return {'success': False, 'error': 'SharePoint not configured for this tenant'}
        
        logger.info(f"[SharePoint Sync] Force syncing: {tenant.name}")
        
        # Determine batch window (since last successful sync, or 24h if never synced)
        if tenant.last_sharepoint_sync_timestamp:
            minutes_back = int((datetime.utcnow() - tenant.last_sharepoint_sync_timestamp).total_seconds() / 60) + 10
        else:
            minutes_back = 24 * 60  # Default to 24 hours if never synced
        
        service = SharePointSyncService(tenant)
        
        if not service.token:
            msg = "Failed to obtain authentication token. Check Azure AD configuration."
            logger.error(f"[SharePoint Sync] {msg}")
            return {'success': False, 'error': msg}
        
        if not service.site_id:
            msg = "Failed to resolve SharePoint site ID. Check site URL configuration."
            logger.error(f"[SharePoint Sync] {msg}")
            return {'success': False, 'error': msg}
        
        logger.info(f"[SharePoint Sync] Starting data sync for {tenant.name}...")
        
        # Perform sync for each category, collecting errors instead of aborting
        m_count, v_count, a_count, s_count, l_count, e_count = 0, 0, 0, 0, 0, 0
        errors = []
        
        try:
            m_count = service.sync_metrics_batch(minutes=minutes_back)
        except Exception as e:
            errors.append(f"Metrics Sync Error: {str(e)}")
            db.session.rollback()
            
        try:
            v_count = service.sync_vms_snapshot()
        except Exception as e:
            errors.append(f"VM Sync Error: {str(e)}")
            db.session.rollback()
            
        try:
            a_count = service.sync_activity_batch(minutes=minutes_back)
        except Exception as e:
            errors.append(f"Activity Sync Error: {str(e)}")
            db.session.rollback()
            
        try:
            s_count = service.sync_screenshots_batch(minutes=minutes_back)
        except Exception as e:
            errors.append(f"Screenshot Sync Error: {str(e)}")
            db.session.rollback()
            
        try:
            l_count = service.sync_logs_instant(minutes=minutes_back)
        except Exception as e:
            errors.append(f"Logs Sync Error: {str(e)}")
            db.session.rollback()
            
        try:
            e_count = service.sync_employees()
        except Exception as e:
            errors.append(f"Employee Sync Error: {str(e)}")
            db.session.rollback()
        
        # Update timestamps
        tenant.previous_sharepoint_sync_timestamp = tenant.last_sharepoint_sync_timestamp
        tenant.last_sharepoint_sync_timestamp = datetime.utcnow()
        db.session.commit()
        
        # Calculate total synced across all data types
        total = m_count + v_count + a_count + s_count + l_count + e_count
        
        if errors and total == 0:
            # If everything failed — create error notification
            _create_sync_notification(tenant.id, 'error', 
                f'SharePoint sync failed for {tenant.name}',
                " | ".join(errors), {})
            return {'success': False, 'error': " | ".join(errors)}
            
        result = {
            'success': True,
            'tenant': tenant.name,
            'total_synced': total,
            'breakdown': {
                'metrics': m_count,
                'vms': v_count,
                'activity': a_count,
                'screenshots': s_count,
                'logs': l_count,
                'employees': e_count
            },
            'message': f'Successfully synced {total} items. Errors: {len(errors)}',
            'error': " | ".join(errors) if errors else None
        }
        
        # Create success/warning notification
        if errors:
            _create_sync_notification(tenant.id, 'alert',
                f'SharePoint sync completed with warnings',
                f"Synced {total} items. Some categories failed: {' | '.join(errors)}",
                result['breakdown'])
        else:
            _create_sync_notification(tenant.id, 'sync',
                f'SharePoint sync completed successfully',
                f"Synced {total} items ({m_count} metrics, {a_count} activity, {s_count} screenshots, {l_count} logs, {v_count} VMs, {e_count} employees)",
                result['breakdown'])
        
        logger.info(f"[SharePoint Sync] Force sync completed for {tenant.name}: {result['message']}")
        return result
        
    except Exception as e:
        logger.error(f"[SharePoint Sync] Force sync failed: {str(e)}", exc_info=True)
        try:
            _create_sync_notification(tenant_id, 'error',
                f'SharePoint sync crashed',
                str(e), {})
        except:
            pass
        try:
            db.session.rollback()
        except:
            pass
        return {'success': False, 'error': str(e)}


def get_sync_status(tenant_id: int) -> Dict[str, Any]:
    """
    Get detailed sync status for a tenant
    """
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return {'success': False, 'error': 'Tenant not found'}
        
        now = datetime.utcnow()
        status = {
            'success': True,
            'tenant_name': tenant.name,
            'sharepoint_connected': tenant.sharepoint_connected,
            'auto_sync_enabled': tenant.sharepoint_auto_sync,
            'sharepoint_site_url': tenant.sharepoint_site_url,
            'sync_interval_minutes': tenant.sharepoint_sync_interval_minutes or 60,
            'last_sync': tenant.last_sharepoint_sync_timestamp.isoformat() if tenant.last_sharepoint_sync_timestamp else None,
            'time_since_last_sync_minutes': None,
            'next_sync_due': False
        }
        
        if tenant.last_sharepoint_sync_timestamp:
            minutes_since = (now - tenant.last_sharepoint_sync_timestamp).total_seconds() / 60.0
            status['time_since_last_sync_minutes'] = round(minutes_since, 1)
            interval = status['sync_interval_minutes']
            status['next_sync_due'] = minutes_since >= interval
        else:
            status['next_sync_due'] = True
        
        # Data counts
        from web.models import Server, Metric, Screenshot
        status['data_counts'] = {
            'servers': Server.query.filter_by(tenant_id=tenant_id).count(),
            'metrics': Metric.query.join(Server).filter(Server.tenant_id == tenant_id).count(),
            'unsynced_screenshots': Screenshot.query.filter_by(tenant_id=tenant_id, sharepoint_url=None).count(),
            'total_screenshots': Screenshot.query.filter_by(tenant_id=tenant_id).count()
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting sync status for tenant {tenant_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
