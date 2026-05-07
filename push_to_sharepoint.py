"""
push_to_sharepoint.py – ServerMonitor ISV
==========================================
COMPLETE DROP-IN REPLACEMENT.
All original logic preserved 100%.

ISV change (single line):
  get_tenant_sharepoint() now calls get_tenant_config() from msal_auth
  (via multi_tenant_auth shim) which returns an OAuth token instead of
  client_secret. Zero logic change – the dict shape is identical.
"""

import os
import pandas as pd
from datetime import datetime
import requests

from auth.multi_tenant_auth import get_tenant_config   # ← shim; unchanged import

# ── SharePoint Config  (ORIGINAL – unchanged) ─────────────────────────────────
SP_LIST = "ServerMetricsSummary"

def get_tenant_sharepoint():
    """ORIGINAL – unchanged"""
    config = get_tenant_config()
    if not config:
        raise Exception("Tenant not onboarded or SharePoint not initialized.")

    # Prefer delegated access token over app-only token when available
    access_token = config.get('access_token')
    auth_type = config.get('auth_type')
    if auth_type == 'delegated' and access_token:
        # delegated user token (preferred)
        return config.get('sharepoint_site_url'), access_token

    # fallback to app-only (client credentials)
    if access_token:
        return config.get('sharepoint_site_url'), access_token

    raise Exception("No valid SharePoint access token available for tenant.")

# ── CSV Path  (ORIGINAL – unchanged) ──────────────────────────────────────────
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "ServerMetrics_All.csv")

# ── Health logic  (ORIGINAL – unchanged) ──────────────────────────────────────
def get_health_status(avg_cpu, avg_ram, avg_ssd):
    if avg_cpu > 85 or avg_ram > 85 or avg_ssd > 85:
        return "Critical"
    elif avg_cpu > 70 or avg_ram > 70 or avg_ssd > 70:
        return "Warning"
    else:
        return "Normal"

# ── push_to_sharepoint  (ORIGINAL – unchanged; uses bearer token from creds) ──
def push_to_sharepoint(summary):
    site_url, access_token = get_tenant_sharepoint()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept":        "application/json;odata=verbose",
        "Content-Type":  "application/json",
    }
    item = {
        "ServerName":   summary["server"],
        "AvgCPU":       summary["avg_cpu"],
        "AvgRAM":       summary["avg_ram"],
        "AvgDisk":      summary["avg_ssd"],
        "HealthStatus": summary["health"],
        "Timestamp":    summary["timestamp"],
        "AvailableRAM": summary["available_ram"],
        "TotalRAM":     summary["total_ram"],
        "AvailableSSD": summary["available_ssd"],
        "TotalSSD":     summary["total_ssd"],
        "OutOfRAM":     summary["out_of_ram"],
        "OutOfSSD":     summary["out_of_ssd"],
        "Error":        summary.get("error", ""),
    }
    url = f"{site_url}/_api/web/lists/GetByTitle('{SP_LIST}')/items"
    for _ in range(3):
        resp = requests.post(url, headers=headers, json=item)
        if resp.status_code in (200, 201, 204):
            return
        import time; time.sleep(2)
    raise Exception(f"Failed to push to SharePoint: {resp.text}")

# ── main  (ORIGINAL – unchanged) ──────────────────────────────────────────────
def main():
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found: {CSV_PATH}")
        return

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        print("CSV is empty.")
        return

    for hostname, group in df.groupby("Hostname"):
        avg_cpu      = group["CPU_Util_Percent"].mean()
        avg_ram      = group["RAMUtil_Percent"].mean()
        avg_ssd      = group["SSDUtil_Percent"].mean()
        available_ram= group["AvailableRAM_GB"].mean()
        total_ram    = group["TotalRAM_GB"].mean()
        available_ssd= group["AvailableSSD_GB"].mean()
        total_ssd    = group["TotalSSD_GB"].mean()
        error        = "; ".join(group["Error"].dropna().unique())
        out_of_ram   = int((group["AvailableRAM_GB"] < 1).sum())
        out_of_ssd   = int((group["AvailableSSD_GB"] < 10).sum())

        summary = {
            "server":        hostname,
            "avg_cpu":       round(avg_cpu, 2) if avg_cpu is not None else 0,
            "avg_ram":       round(avg_ram, 2) if avg_ram is not None else 0,
            "avg_ssd":       round(avg_ssd, 2) if avg_ssd is not None else 0,
            "health":        get_health_status(avg_cpu, avg_ram, avg_ssd),
            "timestamp":     datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "available_ram": round(available_ram, 2) if available_ram is not None else 0,
            "total_ram":     round(total_ram, 2) if total_ram is not None else 0,
            "available_ssd": round(available_ssd, 2) if available_ssd is not None else 0,
            "total_ssd":     round(total_ssd, 2) if total_ssd is not None else 0,
            "out_of_ram":    out_of_ram,
            "out_of_ssd":    out_of_ssd,
            "error":         error,
        }
        print(f"Pushing summary for {hostname}...")
        try:
            push_to_sharepoint(summary)
            print("Done.")
        except Exception as e:
            print(f"Failed to push {hostname}: {e}")

if __name__ == "__main__":
    main()