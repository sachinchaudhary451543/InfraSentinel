#!/usr/bin/env python3
"""
Verify Microsoft Entra ID Configuration

This script validates that all necessary environment variables are set
and that the MSAL library can initialize properly.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_env_file():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
    return env_path

def verify_config():
    """Verify Microsoft Entra ID configuration."""
    
    print("\n" + "="*60)
    print("Microsoft Entra ID Configuration Verification")
    print("="*60 + "\n")
    
    env_path = load_env_file()
    
    # Check required environment variables
    required_vars = {
        'SERVERMONITOR_CLIENT_ID': 'Azure App Registration Client ID',
        'SERVERMONITOR_CLIENT_SECRET': 'Azure App Registration Client Secret',
        'REDIRECT_URI': 'OAuth Redirect URI',
    }
    
    optional_vars = {
        'AZURE_TENANT_ID': 'Azure Tenant ID (defaults to common)',
    }
    
    print(f"✓ Configuration file: {env_path}\n")
    
    # Check required variables
    print("REQUIRED VARIABLES:")
    print("-" * 60)
    all_set = True
    for var, description in required_vars.items():
        value = os.environ.get(var, '')
        if value:
            masked = value[:10] + '...' if len(value) > 10 else value
            print(f"✓ {var:30} = {masked}")
        else:
            print(f"✗ {var:30} = NOT SET")
            all_set = False
    
    # Check optional variables
    print("\nOPTIONAL VARIABLES:")
    print("-" * 60)
    for var, description in optional_vars.items():
        value = os.environ.get(var, '')
        if value:
            print(f"✓ {var:30} = {value}")
        else:
            print(f"ℹ {var:30} = NOT SET (will use 'common')")
    
    # Try to import MSAL
    print("\nMSAL LIBRARY CHECK:")
    print("-" * 60)
    try:
        import msal
        print(f"✓ MSAL library is installed (version: {msal.__version__ if hasattr(msal, '__version__') else 'unknown'})")
        
        # Try to create MSAL app
        if all_set:
            try:
                app = msal.PublicClientApplication(
                    client_id=os.environ.get('SERVERMONITOR_CLIENT_ID'),
                    authority=f"https://login.microsoftonline.com/{os.environ.get('AZURE_TENANT_ID', 'common')}"
                )
                print("✓ MSAL PublicClientApplication created successfully")
            except Exception as e:
                print(f"✗ Failed to create MSAL app: {e}")
                all_set = False
    except ImportError:
        print("✗ MSAL library is NOT installed")
        print("  Install it with: pip install msal")
        all_set = False
    
    # Final status
    print("\n" + "="*60)
    if all_set:
        print("✓ Microsoft Entra ID is properly configured!")
        print("="*60 + "\n")
        print("You can now use Microsoft Entra ID for authentication.")
        print("The login page will show the 'Continue with Microsoft' button.\n")
        return True
    else:
        print("✗ Microsoft Entra ID is NOT properly configured")
        print("="*60 + "\n")
        print("SETUP INSTRUCTIONS:")
        print("-" * 60)
        print("1. Create an Azure App Registration:")
        print("   - Go to Azure Portal > App registrations > New registration")
        print("   - Create an app with name like 'ServerMonitor'")
        print("\n2. Configure the app:")
        print("   - Copy the Client ID (Application ID)")
        print("   - Create a Client Secret (Certificates & secrets)")
        print("   - Add Redirect URI: http://localhost:8080/auth/entra/callback")
        print("\n3. Update .env file:")
        print(f"   SERVERMONITOR_CLIENT_ID=<your_client_id>")
        print(f"   SERVERMONITOR_CLIENT_SECRET=<your_client_secret>")
        print(f"   AZURE_TENANT_ID=<your_tenant_id>")
        print(f"   REDIRECT_URI=http://localhost:8080/auth/entra/callback")
        print("\n4. Restart the Flask app:")
        print("   python web/app.py\n")
        return False

if __name__ == '__main__':
    success = verify_config()
    sys.exit(0 if success else 1)
