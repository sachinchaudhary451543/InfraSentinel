import requests
import json

url = 'http://localhost:5000/api/v2/agent/metrics'
data = {
    'agent_key': 'demo_mode_key',
    'hostname': 'BFS_Sachin',
    'os_info': 'Windows-11-10.0.26200-SP0',
    'ip': '192.168.31.139',
    'logged_in_user': 'SachinKumar',
    'idle_time_seconds': 30,
    'active_app': 'Code',
    'window_title': 'Test Window',
    'activity': {
        'app': 'Code',
        'window_title': 'Test Window',
        'idle_seconds': 30
    },
    'metrics': {
        'cpu_percent': 25.5,
        'ram_percent': 50.2,
        'total_ram_gb': 16.0,
        'used_ram_gb': 8.0,
        'disk_percent': 40.1,
        'total_disk_gb': 512.0,
        'used_disk_gb': 200.0
    },
    'details': {
        'installed_software': []
    }
}

try:
    print(f"Posting to {url}...")
    resp = requests.post(url, json=data, timeout=60)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
