"""
sharepoint_uploader.py – ServerMonitor ISV
===========================================
Refactored to use MS Graph API instead of SharePoint REST.
Integrated with SharePoint Tenant Isolation for multi-tenant data security.
"""

import os
import sqlite3
import requests
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from web.sharepoint_tenant_isolation import SharePointTenantIsolation

logger = logging.getLogger("[SHAREPOINT_UPLOADER]")

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED LIST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_LISTS = {
    "ServerMetricsSummary": [
        {"name": "ServerName",   "type": "Text",   "indexed": True},
        {"name": "Timestamp",    "type": "Text",   "indexed": True},
        {"name": "AvgCPU",       "type": "Number"},
        {"name": "AvgDisk",      "type": "Number"},
        {"name": "AvgRAM",       "type": "Number"},
        {"name": "AvgSSD",       "type": "Number"},
        {"name": "TotalRAM",     "type": "Number"},
        {"name": "AvailableRAM", "type": "Number"},
        {"name": "TotalSSD",     "type": "Number"},
        {"name": "AvailableSSD", "type": "Number"},
        {"name": "OutOfRAM",     "type": "Number"},
        {"name": "OutOfSSD",     "type": "Number"},
        {"name": "HealthStatus", "type": "Text"},
        {"name": "Error",        "type": "Text"},
        {"name": "IsHyperVHost", "type": "Number"},
    ],
    "ServerMetricsHistory": [
        {"name": "ServerName",   "type": "Text",   "indexed": True},
        {"name": "Timestamp",    "type": "Text",   "indexed": True},
        {"name": "AvgCPU",       "type": "Number"},
        {"name": "AvgDisk",      "type": "Number"},
        {"name": "AvgRAM",       "type": "Number"},
        {"name": "AvgSSD",       "type": "Number"},
        {"name": "TotalRAM",     "type": "Number"},
        {"name": "AvailableRAM", "type": "Number"},
        {"name": "TotalSSD",     "type": "Number"},
        {"name": "AvailableSSD", "type": "Number"},
        {"name": "OutOfRAM",     "type": "Number"},
        {"name": "OutOfSSD",     "type": "Number"},
        {"name": "HealthStatus", "type": "Text"},
        {"name": "Error",        "type": "Text"},
    ],
    "ServerVMs": [
        {"name": "HostServer",    "type": "Text", "indexed": True},
        {"name": "VMName",        "type": "Text", "indexed": True},
        {"name": "State",         "type": "Text"},
        {"name": "CPUUsage",      "type": "Number"},
        {"name": "MemoryAssigned","type": "Number"},
        {"name": "Uptime",        "type": "Text"},
        {"name": "Path",          "type": "Text"},
        {"name": "HostIP",        "type": "Text"},
        {"name": "HostOS",        "type": "Text"},
        {"name": "ServerName",    "type": "Text"},
        {"name": "Title",         "type": "Text"},
    ],
    "ServerInventory": [
        {"name": "ServerName",  "type": "Text", "indexed": True},
        {"name": "IPAddress",   "type": "Text"},
        {"name": "MACAddress",  "type": "Text"},
        {"name": "Location",    "type": "Text"},
        {"name": "InstallDate", "type": "DateTime"},
        {"name": "LastModified","type": "DateTime"},
    ],
}

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(BASE_DIR, "data", "central.db")
SP_SITE      = "https://bafflesol.sharepoint.com/sites/BFS_OnPrem_Server_Report"


def get_graph_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def _get_site_id(site_url, token):
    parsed = urlparse(site_url)
    hostname = parsed.netloc
    path = parsed.path
    url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}?$select=id"
    resp = requests.get(url, headers=get_graph_headers(token))
    if resp.status_code == 200:
        return resp.json().get('id')
    print(f"Error fetching site id: {resp.status_code} - {resp.text}")
    return None


def _get_list_id(site_id, list_name, token):
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists?$filter=displayName eq '{list_name}'&$select=id"
    resp = requests.get(url, headers=get_graph_headers(token))
    if resp.status_code == 200:
        items = resp.json().get('value', [])
        if items:
            return items[0].get('id')
    return None


def normalize_hostname(name):
    name = str(name).strip()
    if name.isdigit():
        return f"BFSHOST{name}"
    return name.upper()


def health_status(cpu, ram, ssd):
    if max(cpu, ram, ssd) >= 85:
        return "Critical"
    elif max(cpu, ram, ssd) >= 70:
        return "Warning"
    return "Normal"


def safe(v):
    return 0 if v is None else v


def setup_sharepoint(site_url, client_id, client_secret):
    # This is essentially legacy now. Use sharepoint_provisioner or dynamic setup.
    print("Graph API replaces office365 schema setup.")


def push_metrics_to_sharepoint(creds=None, tenant_id=None):
    print(f"Starting SharePoint sync for Tenant ID {tenant_id} via MS Graph")
    logger.info(f"Starting SharePoint sync for Tenant ID {tenant_id} with tenant isolation enabled")

    if tenant_id is None:
        print("ERROR: tenant_id is required for SharePoint sync.")
        logger.error("ERROR: tenant_id is required for SharePoint sync.")
        return

    if not creds or not creds.get("access_token"):
        # Since we migrated from Client Credentials to Auth Code Flow, we need a delegated access_token
        # obtained from entra_auth instead of legacy SP_CLIENT_ID / SP_CLIENT_SECRET
        print("ERROR: access_token not provided. Cannot push metrics to Microsoft Graph.")
        logger.error("ERROR: access_token not provided. Cannot push metrics to Microsoft Graph.")
        return

    access_token = creds.get("access_token")
    site_url = creds.get("site_url", SP_SITE)
    
    # Get tenant name from database for tenant folder isolation
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        tenant_name = cur.execute(
            "SELECT name FROM tenant WHERE id = ?", 
            (tenant_id,)
        ).fetchone()
        tenant_name = tenant_name[0] if tenant_name else f"Tenant_{tenant_id}"
        conn.close()
        logger.info(f"Tenant name: {tenant_name}")
    except Exception as e:
        logger.warning(f"Failed to get tenant name from database: {e}")
        tenant_name = f"Tenant_{tenant_id}"
    
    # Ensure tenant folder structure exists on SharePoint
    try:
        folder_created = SharePointTenantIsolation.ensure_tenant_folder_exists(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            site_url=site_url,
            access_token=access_token
        )
        if folder_created:
            logger.info(f"✓ Tenant folder structure ready at: /sites/ServerMonitor/{tenant_name}/")
        else:
            logger.warning(f"⚠ Failed to create tenant folder structure, continuing with shared lists")
    except Exception as e:
        logger.warning(f"Tenant folder creation error (non-blocking): {e}")

    site_id = _get_site_id(site_url, access_token)
    if not site_id:
        print(f"ERROR: Could not resolve site ID for {site_url}")
        return

    # Check ServerVMs
    vm_list_id = _get_list_id(site_id, "ServerVMs", access_token)
    if vm_list_id:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        vms  = cur.execute(
            "SELECT Hostname, VMName, State, CPUUsage, MemoryAssigned, Uptime, Path, HostIP, HostOS "
            "FROM vms WHERE tenant_id = ? AND VMName IS NOT NULL AND TRIM(VMName) <> ''",
            (tenant_id,)
        ).fetchall()
        
        vm_post_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{vm_list_id}/items"
        headers = get_graph_headers(access_token)
        for vm in vms:
            (host, name, state, cpu, mem, uptime, path, ip, osinfo) = vm
            payload = {
                "fields": {
                    "Title":       name,
                    "HostServer":  host,
                    "VMName":      name,
                    "State":       state,
                    "CPUUsage":    cpu,
                    "MemoryAssigned": mem,
                    "Uptime":      uptime,
                    "Path":        path,
                    "HostIP":      ip,
                    "HostOS":      osinfo,
                    "ServerName":  host,
                }
            }
            requests.post(vm_post_url, headers=headers, json=payload)
        conn.close()
    else:
        print("[WARN] ServerVMs list not found on SharePoint site.")

    # Check ServerMetricsHistory
    hist_list_id = _get_list_id(site_id, "ServerMetricsHistory", access_token)
    if hist_list_id:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        rows = cur.execute("""
            SELECT s.hostname, t.cpu_util_percent, t.ram_util_percent, t.ssd_util_percent,
                   t.available_ram_gb, t.total_ram_gb, t.available_ssd_gb, t.total_ssd_gb,
                   t.used_ram_gb, t.used_ssd_gb, s.is_hyperv_host
            FROM metrics t
            JOIN server s ON t.server_id = s.id
            INNER JOIN (
                SELECT server_id, MAX(datetime(timestamp)) AS max_time
                FROM metrics
                GROUP BY server_id
            ) latest
            ON t.server_id = latest.server_id AND datetime(t.timestamp) = latest.max_time
            WHERE s.tenant_id = ?
        """, (tenant_id,)).fetchall()

        IST = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        hist_post_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{hist_list_id}/items"
        headers = get_graph_headers(access_token)

        for r in rows:
            (hostname, cpu_util, ram_util, ssd_util,
             avail_ram, total_ram, avail_ssd, total_ssd,
             used_ram, used_ssd, is_hyperv) = r

            hostname = normalize_hostname(hostname)
            health   = health_status(safe(cpu_util), safe(ram_util), safe(ssd_util))

            payload = {
                "fields": {
                    "ServerName":   hostname,
                    "Timestamp":    now,
                    "AvgCPU":       safe(cpu_util),
                    "AvgDisk":      safe(ssd_util),
                    "AvgRAM":       safe(ram_util),
                    "AvgSSD":       safe(ssd_util),
                    "TotalRAM":     safe(total_ram),
                    "AvailableRAM": safe(avail_ram),
                    "TotalSSD":     safe(total_ssd),
                    "AvailableSSD": safe(avail_ssd),
                    "OutOfRAM":     safe(used_ram),
                    "OutOfSSD":     safe(used_ssd),
                    "HealthStatus": health,
                    "IsHyperVHost": 1 if is_hyperv else 0,
                }
            }
            requests.post(hist_post_url, headers=headers, json=payload)

        conn.close()
        print("✅ SharePoint sync completed via MS Graph")
    else:
        print("[WARN] ServerMetricsHistory list not found on SharePoint site.")
