#!/usr/bin/env python3
"""
ServerMonitor Startup Diagnostics
===================================

Identifies and troubleshoots all startup issues.
Run: python startup_diagnostics.py
"""

import sys
import subprocess
import importlib
from pathlib import Path

print("\n" + "="*70)
print("  ServerMonitor Startup Diagnostics")
print("="*70 + "\n")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: Python Environment
# ════════════════════════════════════════════════════════════════════════════

print("1️⃣  PYTHON ENVIRONMENT")
print("-" * 70)

print(f"✓ Python executable:    {sys.executable}")
print(f"✓ Python version:       {sys.version.split()[0]}")
print(f"✓ Working directory:    {Path.cwd()}")

# Check if venv is active
if hasattr(sys, 'real_prefix'):
    print(f"✓ Virtual environment:  ACTIVE (using {sys.prefix})")
elif hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
    print(f"✓ Virtual environment:  ACTIVE (using {sys.prefix})")
else:
    print(f"⚠️  Virtual environment:  NOT ACTIVE (using system Python)")
    print(r"    Run: .\.venv\Scripts\Activate.ps1")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: Required Dependencies
# ════════════════════════════════════════════════════════════════════════════

print("\n2️⃣  REQUIRED DEPENDENCIES")
print("-" * 70)

REQUIRED = {
    'flask': 'Web framework',
    'flask_login': 'User authentication',
    'flask_sqlalchemy': 'Database ORM',
    'msal': 'Azure OAuth (MSAL)',
    'requests': 'HTTP requests',
    'office365': 'SharePoint integration',
}

missing = []
for package, desc in REQUIRED.items():
    try:
        imported = importlib.import_module(package.replace('-', '_'))
        version = getattr(imported, '__version__', 'unknown')
        print(f"✓ {package:<35} {desc:<30} v{version}")
    except ImportError as e:
        print(f"❌ {package:<35} {desc:<30} [MISSING]")
        missing.append(package)

if missing:
    print(f"\n  Action: Install missing packages")
    print(f"  Command: pip install {' '.join(missing)}")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: Core Module Imports
# ════════════════════════════════════════════════════════════════════════════

print("\n3️⃣  CORE MODULE IMPORTS")
print("-" * 70)

CORE_MODULES = [
    ('core.domain_discovery', 'Domain Discovery Engine'),
    ('core.graph_integration', 'Graph API Integration'),
    ('core.azure_discovery', 'Azure Device Discovery'),
    ('core.ldap_compat', 'LDAP Compatibility'),
    ('auth.entra_auth', 'Entra ID Authentication'),
    ('web.models', 'Database Models'),
    ('web.app', 'Flask Application'),
]

import_errors = []
for module_path, description in CORE_MODULES:
    try:
        importlib.import_module(module_path)
        print(f"✓ {module_path:<35} {description}")
    except ImportError as e:
        print(f"❌ {module_path:<35} {description}")
        print(f"   Error: {str(e)}")
        import_errors.append((module_path, str(e)))
    except Exception as e:
        print(f"⚠️  {module_path:<35} {description}")
        print(f"   Error: {type(e).__name__}: {str(e)}")
        import_errors.append((module_path, str(e)))

# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: Configuration Files
# ════════════════════════════════════════════════════════════════════════════

print("\n4️⃣  CONFIGURATION FILES")
print("-" * 70)

config_files = {
    'config.json': 'Application configuration',
    'config.secrets.enc': 'Encrypted secrets (machine-bound)',
    '.env': 'Environment variables (optional)',
}

for filename, description in config_files.items():
    path = Path(filename)
    if path.exists():
        size = path.stat().st_size
        print(f"✓ {filename:<35} {description:<30} ({size} bytes)")
    elif filename == '.env':
        print(f"⚠️  {filename:<35} {description:<30} (optional)")
    else:
        print(f"❌ {filename:<35} {description:<30} [MISSING]")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 5: Azure Configuration
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# SECTION 5: Azure Configuration
# ════════════════════════════════════════════════════════════════════════════

print("\n5️⃣  AZURE CONFIGURATION")
print("-" * 70)

import os
import json

# Check environment variables (primary source for Azure credentials)
client_id = os.environ.get("SERVERMONITOR_CLIENT_ID", "").strip()
tenant_id = os.environ.get("SERVERMONITOR_TENANT_ID", "").strip()

if client_id:
    print(f"✓ Azure Client ID (env): {client_id[:20]}...")
else:
    print(f"❌ Azure Client ID (env): [NOT SET]")

if tenant_id:
    print(f"✓ Azure Tenant ID (env):  {tenant_id[:20]}...")
else:
    print(f"❌ Azure Tenant ID (env):  [NOT SET]")

# Also check config.json for stored attributes
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    if 'sharepoint_site_url' in config:
        print(f"✓ SharePoint Site URL:    {config['sharepoint_site_url']}")
    else:
        print(f"⚠️  SharePoint Site URL:   [NOT CONFIGURED - Domain Discovery may be limited]")
        
    if 'azure_client_id' in config:
        print(f"  Azure Client ID (cfg):  {config['azure_client_id'][:20]}...")
    
except Exception as e:
    print(f"⚠️  Error reading config.json: {str(e)}")

# Summary
if not client_id or not tenant_id:
    print(f"\n  ⚠️  Missing Azure credentials in environment variables!")
    print(f"  Set these before running main.py:")
    print(f"     $env:SERVERMONITOR_CLIENT_ID = 'YOUR_CLIENT_ID'")
    print(f"     $env:SERVERMONITOR_TENANT_ID = 'YOUR_TENANT_ID'")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 6: WinRM Configuration
# ════════════════════════════════════════════════════════════════════════════

print("\n6️⃣  WINRM CONFIGURATION")
print("-" * 70)

try:
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', 
         "Get-Item -Path WSMan:\\localhost\\Client\\TrustedHosts"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    trusted = result.stdout.strip()
    if trusted and trusted != '':
        print(f"✓ TrustedHosts:         {trusted}")
    else:
        print(f"⚠️  TrustedHosts:         [EMPTY - Remote PS may fail]")
        print(f"   Action: Run as Admin:")
        print(f"   powershell> Set-Item -Path WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force")
except Exception as e:
    print(f"⚠️  Cannot check TrustedHosts: {str(e)}")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 7: Network Connectivity
# ════════════════════════════════════════════════════════════════════════════

print("\n7️⃣  NETWORK CONNECTIVITY")
print("-" * 70)

endpoints = {
    'Azure AD Graph': 'https://graph.microsoft.com/v1.0/organization',
    'SharePoint': 'https://bafflesol.sharepoint.com',
    'Microsoft Login': 'https://login.microsoft.com',
}

try:
    import requests
    for name, url in endpoints.items():
        try:
            response = requests.head(url, timeout=5)
            print(f"✓ {name:<25} {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"⚠️  {name:<25} [TIMEOUT]")
        except requests.exceptions.ConnectionError:
            print(f"❌ {name:<25} [NO CONNECTION]")
        except Exception as e:
            print(f"⚠️  {name:<25} [{type(e).__name__}]")
except ImportError:
    print("⚠️  requests library not available - skipping network checks")

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY & RECOMMENDATIONS
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("SUMMARY & RECOMMENDATIONS")
print("="*70 + "\n")

critical_issues = []

if missing:
    critical_issues.append(f"Missing Python packages: {', '.join(missing)}")

if import_errors:
    critical_issues.append(f"Module import errors: {len(import_errors)} issue(s)")

if critical_issues:
    print("❌ CRITICAL ISSUES FOUND:")
    for i, issue in enumerate(critical_issues, 1):
        print(f"   {i}. {issue}")
    
    print("\n📋 ACTION PLAN:")
    print("\n   Step 1: Install missing dependencies")
    print("   ──────────────────────────────────")
    if missing:
        print(f"   $ pip install {' '.join(missing)}")
    else:
        print("   $ pip install -r requirements.txt --upgrade")
    
    print("\n   Step 2: Fix import errors")
    print("   ──────────────────────────────────")
    if import_errors:
        for module_path, error in import_errors:
            print(f"   • {module_path}: {error}")
        print("\n   → Check module dependencies")
        print("   → Verify file paths exist")
        print("   → Test imports manually: python -c 'from {module} import *'")
    
    print("\n   Step 3: Re-run diagnostics")
    print("   ──────────────────────────────────")
    print("   $ python startup_diagnostics.py")
    
    print("\n   Step 4: Start ServerMonitor")
    print("   ──────────────────────────────────")
    print("   $ python main.py")

else:
    print("✅ ALL CHECKS PASSED!")
    print("\nYour system is ready. Next steps:")
    print("   1. Run: python main.py")
    print("   2. Open: http://localhost:5000")
    print("   3. Check logs for any runtime issues")

print("\n" + "="*70 + "\n")
