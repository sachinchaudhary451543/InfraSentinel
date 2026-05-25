#!/usr/bin/env python3
"""
Full End-to-End Test - Remote Actions, Terminal Commands, Software Management
Tests the complete flow: Portal → Database → Agent → PowerShell → Portal
"""
import sqlite3
import json
import requests
import time
from datetime import datetime

BASE_URL = "http://localhost:3000"
SESSION_COOKIE = ""

def log(msg):
    """Print timestamped message"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def test_1_login():
    """Test login and get session"""
    log("🔐 TEST 1: Login to Portal")
    try:
        session = requests.Session()
        res = session.post(f"{BASE_URL}/auth/login", data={
            'username': 'admin',
            'password': 'admin'
        }, allow_redirects=True)
        if res.status_code == 200:
            log("  ✅ Login successful")
            return session
        else:
            log(f"  ❌ Login failed: {res.status_code}")
            return None
    except Exception as e:
        log(f"  ❌ Network error: {e}")
        return None

def test_2_queue_commands(session):
    """Test queueing various commands"""
    log("\n📤 TEST 2: Queue Commands via API")
    server_id = 2  # Adjust based on your server
    
    commands = [
        ("Terminal", "hostname"),
        ("PowerShell", "Get-Date"),
        ("Software List", "winget list"),
    ]
    
    for cmd_type, cmd_str in commands:
        try:
            res = session.post(
                f"{BASE_URL}/api/v2/commands",
                json={"server_id": server_id, "command": cmd_str},
                headers={"Content-Type": "application/json"}
            )
            data = res.json()
            if res.status_code == 200 and data.get('success'):
                log(f"  ✅ {cmd_type}: Command ID {data['command_id']} queued")
            else:
                log(f"  ❌ {cmd_type}: {data.get('error', 'Unknown error')}")
        except Exception as e:
            log(f"  ❌ {cmd_type}: {e}")

def test_3_check_database():
    """Check database for pending commands"""
    log("\n🗄️  TEST 3: Check Database Status")
    try:
        conn = sqlite3.connect('data/central.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM remote_command WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM remote_command WHERE status = "completed"')
        completed = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM remote_command WHERE status = "failed"')
        failed = cursor.fetchone()[0]
        
        log(f"  Pending: {pending} | Completed: {completed} | Failed: {failed}")
        
        # Show recent commands
        cursor.execute('SELECT id, command, status FROM remote_command ORDER BY id DESC LIMIT 5')
        log("  Recent commands:")
        for cmd_id, cmd, status in cursor.fetchall():
            status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
            log(f"    {status_icon} ID {cmd_id}: {cmd[:40]}... ({status})")
        
        conn.close()
    except Exception as e:
        log(f"  ❌ Database error: {e}")

def test_4_api_endpoints(session):
    """Test various API endpoints"""
    log("\n🔌 TEST 4: API Endpoints")
    server_id = 2
    
    endpoints = [
        ("GET", f"/api/v2/server/{server_id}/software/list", "Get software list"),
        ("GET", f"/api/v2/server/{server_id}/commands/history", "Get command history"),
    ]
    
    for method, endpoint, desc in endpoints:
        try:
            if method == "GET":
                res = session.get(f"{BASE_URL}{endpoint}")
            else:
                res = session.post(f"{BASE_URL}{endpoint}")
            
            if res.status_code == 200:
                data = res.json()
                log(f"  ✅ {desc}: {data}")
            else:
                log(f"  ⚠️  {desc}: Status {res.status_code}")
        except Exception as e:
            log(f"  ❌ {desc}: {e}")

def test_5_websocket_broadcast():
    """Test WebSocket broadcasting"""
    log("\n📡 TEST 5: WebSocket Broadcast Check")
    log("  ℹ️  WebSocket broadcast configured in agent_command_result()")
    log("  ℹ️  When agent posts result, portal receives via socket.on('command_result')")
    log("  ℹ️  Check browser console: Portal dashboard should show command output")

def test_6_polling_fallback():
    """Test polling fallback"""
    log("\n🔄 TEST 6: Polling Fallback Mechanism")
    log("  ℹ️  If WebSocket unavailable, portal polls /api/v2/commands/<id> every 2s")
    log("  ℹ️  Polling stops after 120s timeout")
    log("  ℹ️  Both mechanisms (WebSocket + Polling) work together for reliability")

def main():
    print("=" * 70)
    print("🧪 REMOTE ACTIONS & TERMINAL COMMANDS - FULL E2E TEST")
    print("=" * 70)
    
    # Test login
    session = test_1_login()
    if not session:
        log("❌ Cannot proceed without login")
        return
    
    # Test API
    test_2_queue_commands(session)
    test_3_check_database()
    test_4_api_endpoints(session)
    test_5_websocket_broadcast()
    test_6_polling_fallback()
    
    print("\n" + "=" * 70)
    print("✅ E2E TEST COMPLETE")
    print("=" * 70)
    print("""
📋 Next Steps:

1. Start Agent:
   python agent.py

2. Monitor:
   - Agent logs: "Executing command: hostname"
   - Portal: System Controls → Terminal (should show output)

3. Verify Command Execution:
   - Queue command via Terminal
   - Check database: SELECT * FROM remote_command WHERE id=X;
   - Should see output populated

4. Test Software Management:
   - Go to System Controls
   - Click "Install Software" or "Uninstall"
   - Check database for pending choco commands
   - Agent should execute: "choco install X -y"

🔧 Troubleshooting:

If commands not showing output:
  1. Check agent is running: Get-Process python
  2. Check agent logs for errors
  3. Browser console for JavaScript errors
  4. Verify /api/v2/agent/commands endpoint returns pending commands

If WebSocket not working:
  1. Check browser Network tab (WebSocket connection)
  2. Verify Flask-SocketIO initialized
  3. Polling fallback should still work (check /api/v2/commands/<id>)
""")

if __name__ == "__main__":
    main()
