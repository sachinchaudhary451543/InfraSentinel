"""
Power BI Template Deployment Support
- Accepts SharePoint URL
- Validates data connectivity
- Provides import instructions
- Optionally automates dataset creation via Power BI REST API
"""
import requests
import logging

def validate_sharepoint_url(url):
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            return True
        return False
    except Exception as e:
        logging.error(f"SharePoint URL validation failed: {e}")
        return False

def deploy_powerbi_template(sharepoint_url, template_path="ServerMonitor.pbit"):
    if not validate_sharepoint_url(sharepoint_url):
        print(f"SharePoint URL {sharepoint_url} is not accessible.")
        return
    print(f"SharePoint URL validated: {sharepoint_url}")
    print(f"\nTo deploy Power BI dashboard:")
    print(f"1. Open Power BI Desktop.")
    print(f"2. Import the template: {template_path}")
    print(f"3. When prompted, enter your SharePoint site URL: {sharepoint_url}")
    print(f"4. Authenticate with your Microsoft 365 account.")
    print(f"5. Save and publish the report as needed.")
    # Optionally automate dataset creation via Power BI REST API (not implemented here)
    print("\n(Optional) For automated dataset creation, see Power BI REST API documentation.")

if __name__ == "__main__":
    url = input("Enter your SharePoint site URL: ").strip()
    deploy_powerbi_template(url)
