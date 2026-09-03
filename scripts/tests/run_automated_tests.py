#!/usr/bin/env python3
"""
AUTOMATED TESTING SCRIPT for ServerMonitor
Runs critical tests automatically and reports results
"""

import sys
import os
import requests
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

from web.app import app
from web.models import db, Server, RemoteCommand, AgentKey

# ============================================================================
# TEST CONFIGURATION
# ============================================================================

BACKEND_URL = "http://localhost:3000"
AGENT_KEY = "demo_mode_key"
TEST_RESULTS = []

class TestResult:
    def __init__(self, name, passed, message=""):
        self.name = name
        self.passed = passed
        self.message = message
        self.timestamp = datetime.now()
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} | {self.name} | {self.message}"

def log_test(name, passed, message=""):
    result = TestResult(name, passed, message)
    TEST_RESULTS.append(result)
    print(f"  {result}")
    return result

def print_header(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")

def print_summary():
    print(f"\n{'='*80}")
    print(f"  TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for r in TEST_RESULTS if r.passed)
    total = len(TEST_RESULTS)
    
    for result in TEST_RESULTS:
        print(f"  {result}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"\n  ✅ ALL TESTS PASSED!")
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed")
    
    print(f"{'='*80}\n")
    
    return passed == total

# ============================================================================
# TEST 1: ENVIRONMENT TESTS
# ============================================================================

def test_python_version():
    print_header("TEST 1: ENVIRONMENT CHECKS")
    
    import platform
    version = platform.python_version()
    major, minor = map(int, version.split('.')[:2])
    
    passed = major >= 3 and minor >= 8
    log_test("Python Version", passed, f"Python {version}")

def test_dependencies():
    try:
        import flask
        import psutil
        import requests
        import sqlalchemy
        from flask_socketio import SocketIO
        
        log_test("Flask Import", True, "Flask installed")
        log_test("psutil Import", True, "psutil installed")
        log_test("requests Import", True, "requests installed")
        log_test("SQLAlchemy Import", True, "SQLAlchemy installed")
        log_test("Flask-SocketIO Import", True, "Flask-SocketIO installed")
    except ImportError as e:
        log_test("Dependencies", False, str(e))

def test_database():
    with app.app_context():
        try:
            # Check if we can query the database
            tenant_count = db.session.execute(db.text("SELECT COUNT(*) FROM tenant")).scalar()
            log_test("Database Connection", True, f"Connected, {tenant_count} tenants found")
            
            # Check if agent key exists
            key = AgentKey.query.filter_by(key='demo_mode_key').first()
            log_test("Agent Key 'demo_mode_key'", key is not None, "Required for agent auth")
        except Exception as e:
            log_test("Database Connection", False, str(e))

# ============================================================================
# TEST 2: BACKEND API TESTS
# ============================================================================

def test_backend_health():
    print_header("TEST 2: BACKEND API HEALTH")
    
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=5)
        passed = response.status_code in [200, 302]  # 302 = redirect to login
        log_test("Backend Health Check", passed, f"Status {response.status_code}")
    except requests.exceptions.ConnectionError:
        log_test("Backend Health Check", False, "Connection refused - backend not running")
    except Exception as e:
        log_test("Backend Health Check", False, str(e))

def test_agent_metrics_endpoint():
    print_header("TEST 3: AGENT METRICS ENDPOINT")
    
    try:
        payload = {
            "agent_key": AGENT_KEY,
            "hostname": "TEST-MACHINE",
            "ip": "192.168.1.100",
            "metrics": {
                "cpu_percent": 45.2,
                "ram_percent": 60.5,
                "disk_percent": 70.1
            }
        }
        
        response = requests.post(
            f"{BACKEND_URL}/api/v2/agent/metrics",
            json=payload,
            timeout=5
        )
        
        passed = response.status_code == 200
        log_test("Metrics Endpoint", passed, f"Status {response.status_code}")
    except Exception as e:
        log_test("Metrics Endpoint", False, str(e))

def test_agent_commands_fetch():
    print_header("TEST 4: AGENT COMMAND FETCHING")
    
    try:
        headers = {
            'X-Agent-Key': AGENT_KEY,
            'X-Hostname': 'TEST-SERVER-01'
        }
        
        response = requests.get(
            f"{BACKEND_URL}/api/v2/agent/commands",
            headers=headers,
            timeout=5
        )
        
        passed = response.status_code == 200
        commands = response.json()
        
        log_test("Fetch Commands", passed, f"Status {response.status_code}, {len(commands)} commands")
    except Exception as e:
        log_test("Fetch Commands", False, str(e))

# ============================================================================
# TEST 5: AGENT & COMMAND TESTS
# ============================================================================

def test_server_registration():
    print_header("TEST 5: AGENT REGISTRATION")
    
    with app.app_context():
        try:
            server = Server.query.filter_by(hostname='TEST-SERVER-01').first()
            passed = server is not None
            
            if passed:
                log_test("Server Registration", True, f"Server ID: {server.id}")
            else:
                log_test("Server Registration", False, "TEST-SERVER-01 not found")
        except Exception as e:
            log_test("Server Registration", False, str(e))

def test_metrics_collection():
    print_header("TEST 6: METRICS COLLECTION")
    
    with app.app_context():
        try:
            from web.models import Metric
            
            server = Server.query.filter_by(hostname='TEST-SERVER-01').first()
            if not server:
                log_test("Metrics Collection", False, "Server not found")
                return
            
            metrics = Metric.query.filter_by(server_id=server.id).order_by(
                Metric.timestamp.desc()
            ).first()
            
            if metrics:
                log_test("Metrics Collection", True, 
                    f"CPU: {metrics.cpu_util_percent}%, RAM: {metrics.ram_util_percent}%")
            else:
                log_test("Metrics Collection", False, "No metrics found")
        except Exception as e:
            log_test("Metrics Collection", False, str(e))

def test_command_creation():
    print_header("TEST 7: COMMAND EXECUTION")
    
    with app.app_context():
        try:
            server = Server.query.filter_by(hostname='TEST-SERVER-01').first()
            if not server:
                log_test("Command Creation", False, "Server not found")
                return
            
            # Create a test command
            cmd = RemoteCommand()
            cmd.server_id = server.id
            cmd.command = 'echo'
            cmd.parameters = 'Automated Test'
            cmd.status = 'pending'
            
            db.session.add(cmd)
            db.session.commit()
            
            log_test("Command Creation", True, f"Command ID: {cmd.id}")
            
            # Wait for execution (max 35 seconds)
            for i in range(35):
                db.session.refresh(cmd)
                if cmd.status != 'pending':
                    break
                time.sleep(1)
            
            if cmd.status == 'completed':
                log_test("Command Execution", True, f"Output: {cmd.output[:50]}")
            else:
                log_test("Command Execution", False, f"Status: {cmd.status}")
            
            # Cleanup
            db.session.delete(cmd)
            db.session.commit()
            
        except Exception as e:
            log_test("Command Creation", False, str(e))

def test_command_history():
    print_header("TEST 8: COMMAND HISTORY")
    
    with app.app_context():
        try:
            from web.models import RemoteCommand
            
            server = Server.query.filter_by(hostname='TEST-SERVER-01').first()
            if not server:
                log_test("Command History", False, "Server not found")
                return
            
            commands = RemoteCommand.query.filter_by(
                server_id=server.id
            ).order_by(RemoteCommand.created_at.desc()).limit(5).all()
            
            if commands:
                completed = sum(1 for c in commands if c.status == 'completed')
                log_test("Command History", True, f"{len(commands)} commands, {completed} completed")
            else:
                log_test("Command History", False, "No commands found")
        except Exception as e:
            log_test("Command History", False, str(e))

# ============================================================================
# TEST 9: DATABASE INTEGRITY
# ============================================================================

def test_database_integrity():
    print_header("TEST 9: DATABASE INTEGRITY")
    
    with app.app_context():
        try:
            from web.models import Tenant, User, Metric
            
            # Check tenants
            tenants = Tenant.query.count()
            log_test("Tenant Count", tenants > 0, f"{tenants} tenants")
            
            # Check users
            users = User.query.count()
            log_test("User Count", users > 0, f"{users} users")
            
            # Check servers
            servers = Server.query.count()
            log_test("Server Count", servers > 0, f"{servers} servers")
            
            # Check metrics
            metrics = Metric.query.count()
            log_test("Metric Records", metrics > 0, f"{metrics} records")
            
        except Exception as e:
            log_test("Database Integrity", False, str(e))

# ============================================================================
# TEST 10: PERFORMANCE
# ============================================================================

def test_response_times():
    print_header("TEST 10: PERFORMANCE CHECKS")
    
    try:
        # Test metrics endpoint response time
        start = time.time()
        response = requests.get(f"{BACKEND_URL}/api/v2/metrics?server_id=2", timeout=5)
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        passed = elapsed < 1000  # Should be under 1 second
        log_test("Metrics API Response Time", passed, f"{elapsed:.0f}ms")
        
    except Exception as e:
        log_test("Response Time Test", False, str(e))

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    print("""
    ╔════════════════════════════════════════════════════════════════════════╗
    ║                  SERVERMONITOR AUTOMATED TESTS                         ║
    ║                      April 15, 2026                                    ║
    ╚════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Run test groups
    test_python_version()
    test_dependencies()
    test_database()
    
    test_backend_health()
    test_agent_metrics_endpoint()
    test_agent_commands_fetch()
    
    test_server_registration()
    test_metrics_collection()
    test_command_creation()
    test_command_history()
    
    test_database_integrity()
    test_response_times()
    
    # Print summary
    success = print_summary()
    
    if success:
        print("\n    ✅ All critical tests passed!")
        print("    The system is ready for production use.\n")
        return 0
    else:
        print("\n    ⚠️  Some tests failed. Please review the output above.\n")
        return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
