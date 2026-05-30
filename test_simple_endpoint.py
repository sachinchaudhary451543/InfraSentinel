"""Test if basic HTTP response works"""
import requests

# Test 1: Simple GET endpoint (should work instantly)
try:
    print("Test 1: GET / (root)...")
    resp = requests.get('http://localhost:5000/', timeout=5)
    print(f"Status: {resp.status_code}, Time: instant ✅")
except requests.exceptions.Timeout:
    print(f"Status: TIMEOUT ❌")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Simple GET endpoint
try:
    print("\nTest 2: GET /api/v2/agent/commands...")
    resp = requests.get('http://localhost:5000/api/v2/agent/commands', 
                       headers={'X-Hostname': 'BFS_Sachin'}, 
                       timeout=5)
    print(f"Status: {resp.status_code}, Time: instant ✅")
except requests.exceptions.Timeout:
    print(f"Status: TIMEOUT ❌")
except Exception as e:
    print(f"Error: {e}")

# Test 3: POST with minimal payload
try:
    print("\nTest 3: POST /api/v2/agent/metrics (minimal payload)...")
    resp = requests.post('http://localhost:5000/api/v2/agent/metrics',
                        json={'agent_key': 'demo_mode_key', 'hostname': 'BFS_Sachin'},
                        timeout=5)
    print(f"Status: {resp.status_code}, Time: instant ✅")
except requests.exceptions.Timeout:
    print(f"Status: TIMEOUT ❌")
except Exception as e:
    print(f"Error: {e}")
