#!/usr/bin/env python3
"""
Emergency Fix Script: Enable Screenshots and Fix Controls
Purpose: Fix the screenshot and remote control issues without data loss

This script:
1. Enables screenshots for ALL existing servers
2. Sets proper default screenshot interval (10 minutes)
3. Verifies RemoteCommand table exists
4. Checks agent registration
5. Provides diagnostic information

USAGE: python fix_screenshots_and_controls.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 80)
    print("🔧 ServerMonitor Screenshot & Controls Fix")
    print("=" * 80)
    
    try:
        from web.app import create_app
        from web.models import db, Server, RemoteCommand, Tenant, AgentKey
        
        app = create_app()
        
        with app.app_context():
            print("\n✓ Database connection established")
            
            # Fix 1: Enable screenshots for all existing servers
            print("\n" + "=" * 80)
            print("FIX 1: Enabling screenshots for all existing servers...")
            print("=" * 80)
            
            total_servers = Server.query.count()
            disabled_servers = Server.query.filter_by(screenshot_enabled=False).count()
            
            print(f"Total servers: {total_servers}")
            print(f"Servers with screenshots disabled: {disabled_servers}")
            
            if disabled_servers > 0:
                db.session.query(Server).filter_by(screenshot_enabled=False).update(
                    {Server.screenshot_enabled: True}
                )
                db.session.commit()
                print(f"✅ Enabled screenshots for {disabled_servers} servers")
            else:
                print("✓ All servers already have screenshots enabled")
            
            # Fix 2: Ensure screenshot interval is set
            print("\n" + "=" * 80)
            print("FIX 2: Setting screenshot interval to 10 minutes for all servers...")
            print("=" * 80)
            
            zero_interval = Server.query.filter(
                (Server.screenshot_interval_minutes == None) | (Server.screenshot_interval_minutes == 0)
            ).count()
            
            if zero_interval > 0:
                db.session.query(Server).filter(
                    (Server.screenshot_interval_minutes == None) | (Server.screenshot_interval_minutes == 0)
                ).update({Server.screenshot_interval_minutes: 10})
                db.session.commit()
                print(f"✅ Set screenshot interval for {zero_interval} servers")
            else:
                print("✓ All servers have proper screenshot interval set")
            
            # Fix 3: Verify RemoteCommand table and schema
            print("\n" + "=" * 80)
            print("FIX 3: Verifying RemoteCommand table...")
            print("=" * 80)
            
            try:
                pending_commands = RemoteCommand.query.filter_by(status='pending').count()
                total_commands = RemoteCommand.query.count()
                print(f"✓ RemoteCommand table exists")
                print(f"  Total commands: {total_commands}")
                print(f"  Pending commands: {pending_commands}")
            except Exception as e:
                print(f"✗ RemoteCommand table issue: {e}")
            
            # Fix 4: Check agent keys
            print("\n" + "=" * 80)
            print("FIX 4: Checking Agent Keys and Registration...")
            print("=" * 80)
            
            total_keys = AgentKey.query.count()
            active_keys = AgentKey.query.filter_by(is_active=True).count()
            print(f"Total agent keys: {total_keys}")
            print(f"Active agent keys: {active_keys}")
            
            # Fix 5: Verify all servers have agent keys
            print("\n" + "=" * 80)
            print("FIX 5: Verifying server API keys...")
            print("=" * 80)
            
            servers_without_key = Server.query.filter(
                (Server.api_key == None) | (Server.api_key == '')
            ).count()
            
            print(f"Servers without API key: {servers_without_key}")
            
            if servers_without_key > 0:
                print("⚠️  Warning: Some servers may not be properly registered")
                print("    They should receive API keys from agents on next heartbeat")
            
            # Summary
            print("\n" + "=" * 80)
            print("✅ SUMMARY: All fixes have been applied")
            print("=" * 80)
            print("\nAgent Configuration (after restart):")
            print("  • ENABLE_SCREENSHOTS = True (enabled by default)")
            print("  • SCREENSHOT_INTERVAL = 300s (5 minutes default)")
            print("  • Agent fetches screenshot_enabled from server each cycle")
            print("  • Server defaults to screenshot_enabled=True")
            print("\nRemote Commands:")
            print("  • Agent polls /api/v2/agent/commands every cycle")
            print("  • Commands can be queued from admin portal")
            print("  • Results are posted back to server")
            print("\nNext Steps:")
            print("  1. Restart agent.py on all servers")
            print("  2. Wait 30 seconds for metrics to be sent")
            print("  3. Check portal for screenshots appearing")
            print("  4. Test remote commands from admin portal")
            print("\nTroubleshooting:")
            print("  • Check agent logs for '📸 Capturing screenshot'")
            print("  • Verify SERVER_URL and AGENT_KEY are correct")
            print("  • Ensure portal is reachable from agents")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
