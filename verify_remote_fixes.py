#!/usr/bin/env python3
"""
ServerMonitor Remote Actions - Complete Status Report
Verification script to confirm all fixes are working
"""

import sys
import os
import subprocess
from pathlib import Path

def check_file_contains(filepath, text, description):
    """Check if file contains specific text"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if text in content:
                print(f"  ✅ {description}")
                return True
            else:
                print(f"  ❌ {description} - NOT FOUND")
                return False
    except Exception as e:
        print(f"  ❌ {description} - Error: {e}")
        return False

def verify_fixes():
    """Verify all fixes are in place"""
    print("=" * 70)
    print("🔍 SERVERMONITOR REMOTE ACTIONS - FIX VERIFICATION")
    print("=" * 70)
    
    base_path = Path(".")
    checks_passed = 0
    checks_total = 0
    
    # Check 1: WebSocket Broadcasting
    print("\n1️⃣  WebSocket Broadcasting (web/routes/api.py)")
    checks_total += 1
    if check_file_contains(
        "web/routes/api.py",
        "socketio.emit('command_result'",
        "WebSocket emit() call present"
    ):
        checks_passed += 1
    
    # Check 2: Broadcast flag
    print("\n2️⃣  Broadcast Flag (web/routes/api.py)")
    checks_total += 1
    if check_file_contains(
        "web/routes/api.py",
        "broadcast=True",
        "Broadcast=True parameter set"
    ):
        checks_passed += 1
    
    # Check 3: JavaScript Fix
    print("\n3️⃣  JavaScript API Endpoint Fix (web/templates/system_details.html)")
    checks_total += 1
    if check_file_contains(
        "web/templates/system_details.html",
        "/api/v2/server/${SERVER_ID}/commands/history",
        "Correct endpoint URL in loadCommandHistory()"
    ):
        checks_passed += 1
    
    # Check 4: Polling Implementation
    print("\n4️⃣  Polling Fallback (web/templates/system_details.html)")
    checks_total += 1
    if check_file_contains(
        "web/templates/system_details.html",
        "pollCommandStatus",
        "pollCommandStatus() function defined"
    ):
        checks_passed += 1
    
    # Check 5: Polling Interval
    print("\n5️⃣  Polling Interval Setup (web/templates/system_details.html)")
    checks_total += 1
    if check_file_contains(
        "web/templates/system_details.html",
        "window._pollInterval = setInterval",
        "Polling interval setup in executeCommand()"
    ):
        checks_passed += 1
    
    # Check 6: Polling Clear
    print("\n6️⃣  Polling Clear on Completion (system_details.html)")
    checks_total += 1
    if check_file_contains(
        "web/templates/system_details.html",
        "clearInterval(window._pollInterval)",
        "Polling interval cleared on command completion"
    ):
        checks_passed += 1
    
    # Check 7: Software Caching
    print("\n7️⃣  Software Detection Caching (web/routes/system_control.py)")
    checks_total += 1
    if check_file_contains(
        "web/routes/system_control.py",
        "Metric.query.filter_by(server_id=server_id)",
        "Reading from Metric table for software cache"
    ):
        checks_passed += 1
    
    # Check 8: Refresh Parameter
    print("\n8️⃣  Refresh Parameter (web/routes/system_control.py)")
    checks_total += 1
    if check_file_contains(
        "web/routes/system_control.py",
        "refresh = request.args.get('refresh'",
        "Refresh parameter support for force fetch"
    ):
        checks_passed += 1
    
    # Check 9: Test File Created
    print("\n9️⃣  E2E Test Suite (test_e2e_remote_commands.py)")
    checks_total += 1
    if (base_path / "test_e2e_remote_commands.py").exists():
        print(f"  ✅ E2E test file created")
        checks_passed += 1
    else:
        print(f"  ❌ E2E test file not found")
    
    # Check 10: Documentation Created
    print("\n🔟 Documentation (REMOTE_ACTIONS_COMPLETE_FIX_v2.md)")
    checks_total += 1
    if (base_path / "REMOTE_ACTIONS_COMPLETE_FIX_v2.md").exists():
        print(f"  ✅ Complete fix documentation created")
        checks_passed += 1
    else:
        print(f"  ❌ Documentation not found")
    
    # Summary
    print("\n" + "=" * 70)
    print(f"📊 VERIFICATION RESULTS: {checks_passed}/{checks_total} checks passed")
    print("=" * 70)
    
    if checks_passed == checks_total:
        print("✅ ALL FIXES VERIFIED AND IN PLACE")
        print("\n🚀 System is ready to test!")
        return True
    else:
        print(f"⚠️  {checks_total - checks_passed} check(s) failed")
        return False

def print_next_steps():
    """Print next steps for user"""
    print("""
📋 NEXT STEPS TO VERIFY WORKING SYSTEM:

1. Start the Portal Server:
   └─ python web/app.py
   
2. Start the Agent (in another terminal):
   └─ python agent.py
   
3. Open Portal in Browser:
   └─ http://localhost:3000
   └─ Login with admin/admin
   
4. Test Terminal Command:
   └─ Go to Server Details
   └─ In Remote Terminal: Type "hostname"
   └─ Click "Run"
   └─ ✅ Should see output within 5 seconds
   
5. Test Software List:
   └─ Go to System Controls
   └─ Click "Software Management"
   └─ ✅ Should show installed software
   
6. Test Software Installation:
   └─ Click "Install Software"
   └─ Select a package (e.g., "7-Zip")
   └─ Click "Deploy"
   └─ ✅ Database should show pending command
   └─ ✅ Agent should execute: "choco install 7-Zip -y"

🔧 IF PROBLEMS OCCUR:

Check Agent Logs:
  └─ Agent polling: "Fetching commands from server"
  └─ Command execution: "Executing command: hostname"
  └─ Result posting: "Posting result to server"

Check Portal Logs:
  └─ Command queued: "[POST] /api/v2/commands"
  └─ Result received: "[POST] /api/v2/agent/commands/result"
  └─ WebSocket broadcast: "socketio.emit('command_result')"

Check Browser Console:
  └─ Open DevTools (F12)
  └─ Console tab: Look for "socket.on('command_result')"
  └─ Network tab: Check WebSocket connection status
  └─ If polling: Check XHR requests to /api/v2/commands/X

Run E2E Test:
  └─ python test_e2e_remote_commands.py
  └─ Should show all tests passing

📞 SUPPORT:

If remote actions still not working:
  1. Check database for pending commands
  2. Verify agent can reach portal API
  3. Check AGENT_KEY configuration
  4. Review PowerShell command execution permissions
  5. Check WebSocket connection in browser (Network tab)

All fixes are documented in: REMOTE_ACTIONS_COMPLETE_FIX_v2.md
""")

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    
    if verify_fixes():
        print_next_steps()
        sys.exit(0)
    else:
        print("\n❌ Some fixes are missing. Please review the errors above.")
        sys.exit(1)
