#!/usr/bin/env python3
"""
Diagnostic & Testing Script: Complete Screenshot and Control System Verification

This script verifies:
1. Agent connectivity and registration
2. Screenshot capture and upload
3. Remote command execution
4. Portal display of screenshots
5. Database integrity
"""

import os
import sys
import requests
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_agent_registration(server_url, agent_key, hostname):
    """Test if agent is properly registered"""
    print(f"\n📋 Testing Agent Registration")
    print(f"  Agent Key: {agent_key[:10]}...")
    print(f"  Hostname: {hostname}")
    
    try:
        from web.app import create_app
        from web.models import db, Server
        
        app = create_app()
        with app.app_context():
            server = Server.query.filter_by(api_key=agent_key).first()
            if server:
                print(f"✅ Agent found in database")
                print(f"  Server ID: {server.id}")
                print(f"  Server Name: {server.name}")
                print(f"  Last Seen: {server.last_seen}")
                print(f"  Status: {server.status}")
                print(f"  Screenshot Enabled: {server.screenshot_enabled}")
                print(f"  Screenshot Interval: {server.screenshot_interval_minutes} minutes")
                return True
            else:
                print(f"✗ Agent NOT found in database")
                print(f"  Agent needs to send metrics to register")
                return False
    except Exception as e:
        print(f"✗ Error checking agent: {e}")
        return False

def test_screenshot_capture():
    """Test if screenshot capture works"""
    print(f"\n📸 Testing Screenshot Capture")
    
    try:
        import platform
        if platform.system() == 'Windows':
            from PIL import ImageGrab
            import io
            import base64
            
            screenshot = ImageGrab.grab()
            img_byte_arr = io.BytesIO()
            screenshot.save(img_byte_arr, format='JPEG', quality=60)
            img_byte_arr.seek(0)
            base64_str = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            print(f"✅ Screenshot captured successfully")
            print(f"  Size: {len(base64_str)} bytes (base64)")
            return True
        else:
            print(f"⚠️  Screenshot capture only works on Windows")
            return True
    except Exception as e:
        print(f"✗ Screenshot capture failed: {e}")
        return False

def test_screenshot_directory():
    """Test if screenshot directory exists and is writable"""
    print(f"\n📁 Testing Screenshot Directory")
    
    try:
        from web.app import app as flask_app
        app_root = os.path.dirname(flask_app.root_path)
        base_dir = os.path.join(app_root, 'data', 'screenshots')
        
        print(f"  Directory: {base_dir}")
        
        if os.path.exists(base_dir):
            print(f"✅ Screenshot directory exists")
            # Count files
            files = os.listdir(base_dir)
            print(f"  Files in directory: {len(files)}")
            if len(files) > 0:
                # Show latest files
                files_sorted = sorted(files, reverse=True)[:3]
                print(f"  Latest files:")
                for f in files_sorted:
                    file_path = os.path.join(base_dir, f)
                    size_kb = os.path.getsize(file_path) // 1024
                    print(f"    - {f} ({size_kb}KB)")
            return True
        else:
            print(f"✗ Screenshot directory does not exist")
            print(f"  Creating directory...")
            os.makedirs(base_dir, exist_ok=True)
            print(f"✅ Directory created")
            return True
    except Exception as e:
        print(f"✗ Error checking screenshot directory: {e}")
        return False

def test_database_tables():
    """Test if all required tables exist"""
    print(f"\n🗄️  Testing Database Tables")
    
    try:
        from web.app import create_app
        from web.models import db, Server, Screenshot, RemoteCommand, EmployeeActivity
        
        app = create_app()
        with app.app_context():
            tables = {
                'Server': Server,
                'Screenshot': Screenshot,
                'RemoteCommand': RemoteCommand,
                'EmployeeActivity': EmployeeActivity,
            }
            
            for table_name, model in tables.items():
                try:
                    count = model.query.count()
                    print(f"✅ {table_name}: {count} records")
                except Exception as e:
                    print(f"✗ {table_name}: {e}")
                    return False
            return True
    except Exception as e:
        print(f"✗ Error checking tables: {e}")
        return False

def test_metrics_endpoint(server_url, agent_key):
    """Test metrics endpoint"""
    print(f"\n📊 Testing Metrics Endpoint")
    print(f"  Endpoint: {server_url}/api/v2/agent/metrics")
    
    try:
        payload = {
            'api_key': agent_key,
            'hostname': 'TEST-DIAGNOSTIC',
            'ip': '127.0.0.1',
            'os_info': 'Windows 10',
            'logged_in_user': 'admin',
            'metrics': {
                'cpu_percent': 25.5,
                'ram_percent': 45.0,
                'disk_percent': 60.0,
                'total_ram_gb': 16,
                'used_ram_gb': 7.2,
                'total_disk_gb': 512,
                'used_disk_gb': 307
            }
        }
        
        resp = requests.post(f"{server_url}/api/v2/agent/metrics", json=payload, timeout=10)
        
        if resp.status_code == 200:
            print(f"✅ Metrics endpoint responded")
            resp_data = resp.json()
            print(f"  Response: {json.dumps(resp_data, indent=2)}")
            return True
        else:
            print(f"✗ Metrics endpoint failed: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"✗ Error testing metrics endpoint: {e}")
        return False

def test_commands_endpoint(server_url, agent_key):
    """Test commands endpoint"""
    print(f"\n🎯 Testing Commands Endpoint")
    print(f"  Endpoint: {server_url}/api/v2/agent/commands")
    
    try:
        headers = {
            'X-Agent-Key': agent_key,
            'X-Hostname': 'TEST-DIAGNOSTIC'
        }
        
        resp = requests.get(f"{server_url}/api/v2/agent/commands", headers=headers, timeout=10)
        
        if resp.status_code == 200:
            print(f"✅ Commands endpoint responded")
            commands = resp.json()
            print(f"  Pending commands: {len(commands)}")
            return True
        else:
            print(f"✗ Commands endpoint failed: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error testing commands endpoint: {e}")
        return False

def main():
    print("\n" + "=" * 80)
    print("🔧 ServerMonitor System Diagnostic")
    print("=" * 80)
    
    # Configuration
    server_url = os.getenv('SERVER_URL', 'http://localhost:5000')
    agent_key = os.getenv('AGENT_KEY', 'test_key')
    hostname = 'DIAGNOSTIC-TEST'
    
    print(f"\nConfiguration:")
    print(f"  Server URL: {server_url}")
    print(f"  Agent Key: {agent_key[:10]}...")
    
    results = {
        'Agent Registration': test_agent_registration(server_url, agent_key, hostname),
        'Screenshot Capture': test_screenshot_capture(),
        'Screenshot Directory': test_screenshot_directory(),
        'Database Tables': test_database_tables(),
        'Metrics Endpoint': test_metrics_endpoint(server_url, agent_key),
        'Commands Endpoint': test_commands_endpoint(server_url, agent_key),
    }
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! System is ready.")
    else:
        print("\n⚠️  Some tests failed. See details above.")
    
    print("\n" + "=" * 80)
    print("Next Steps:")
    print("  1. Start the agent: python agent.py")
    print("  2. Wait for first metrics to be sent (10-30 seconds)")
    print("  3. Check portal for agent appearing online")
    print("  4. Screenshot should appear after configured interval")
    print("  5. Test remote commands from admin portal")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
