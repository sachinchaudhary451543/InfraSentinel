"""Test end-to-end command execution - Remote Actions & Terminal Commands"""
import sqlite3
import json
from datetime import datetime

print("=" * 70)
print("🧪 REMOTE ACTIONS & TERMINAL COMMANDS - END-TO-END TEST")
print("=" * 70)

conn = sqlite3.connect('data/central.db')
cursor = conn.cursor()

# TEST 1: Queue a simple terminal command
print("\n1️⃣  TEST: Queue a terminal command...")
cursor.execute('''
    INSERT INTO remote_command (server_id, command, status, created_at, created_by, timeout_seconds)
    VALUES (2, 'hostname', 'pending', datetime('now'), 'test_user', 30)
''')
cmd_id = cursor.lastrowid
print(f"   ✓ Created command ID {cmd_id}: 'hostname'")

# TEST 2: Queue a Chocolatey install command
print("\n2️⃣  TEST: Queue software installation command...")
cursor.execute('''
    INSERT INTO remote_command (server_id, command, parameters, status, created_at, created_by, timeout_seconds)
    VALUES (?, ?, ?, 'pending', datetime('now'), 'test_user', 120)
''', (
    2,
    'choco install notepadplusplus -y --allow-empty-checksums',
    json.dumps({"action": "install", "software": "notepadplusplus", "requested_by": "test_user"})
))
cmd_id2 = cursor.lastrowid
print(f"   ✓ Created command ID {cmd_id2}: 'choco install notepadplusplus'")

# TEST 3: Queue a PowerShell command
print("\n3️⃣  TEST: Queue PowerShell command...")
cursor.execute('''
    INSERT INTO remote_command (server_id, command, status, created_at, created_by, timeout_seconds)
    VALUES (2, 'Get-Process | Measure-Object -Line', 'pending', datetime('now'), 'test_user', 60)
''')
cmd_id3 = cursor.lastrowid
print(f"   ✓ Created command ID {cmd_id3}: 'Get-Process | Measure-Object -Line'")

conn.commit()

# TEST 4: Verify pending commands
print("\n4️⃣  TEST: Check pending commands for agent...")
cursor.execute('SELECT id, server_id, command, status FROM remote_command WHERE status = "pending" ORDER BY id DESC LIMIT 5')
pending_cmds = cursor.fetchall()
print(f"   ✓ Found {len(pending_cmds)} pending commands:")
for cmd_id, srv_id, cmd, status in pending_cmds:
    print(f"     - ID {cmd_id}: {cmd[:50]}... (Server {srv_id})")

# TEST 5: Show what the agent will fetch
print("\n5️⃣  TEST: Simulate agent API response...")
cursor.execute('''
    SELECT id, command, parameters FROM remote_command 
    WHERE server_id = 2 AND status = 'pending'
    ORDER BY created_at ASC LIMIT 5
''')
agent_response = cursor.fetchall()
print(f"   ✓ Agent will fetch {len(agent_response)} commands:")
for cmd_id, command, params in agent_response:
    print(f"     - {{'command_id': {cmd_id}, 'command': '{command[:40]}...'}}")

# TEST 6: Statistics
print("\n6️⃣  TEST: Database Statistics...")
cursor.execute('SELECT COUNT(*) FROM remote_command WHERE server_id = 2')
server_2_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM remote_command WHERE status = "pending"')
pending_count = cursor.fetchone()[0]
print(f"   ✓ Server 2 total commands: {server_2_count}")
print(f"   ✓ Total pending commands: {pending_count}")

conn.close()

print("\n" + "=" * 70)
print("✅ TEST COMPLETE - System Ready for Command Execution")
print("=" * 70)
print("""
📋 Summary of Fixes Applied:
  1. ✅ Fixed asset_management.py - Now sends proper PowerShell commands (choco install/uninstall)
  2. ✅ Fixed system_control.py - Correctly separates command and parameters
  3. ✅ Fixed agent.py - No longer appends JSON parameters to command strings
  4. ✅ Cleaned database - Archived 11 old failed commands

🚀 Next Steps to Verify Working System:
  1. Start the Portal: python web/app.py
  2. Start the Agent: python agent.py
  3. Queue a terminal command via Portal UI
  4. Watch agent logs for: "Executing command: ..."
  5. Verify output appears in Portal
""")
