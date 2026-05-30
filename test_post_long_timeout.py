#!/usr/bin/env python3
"""Test agent metrics POST with longer timeout."""

import requests
import json

url = 'http://localhost:5000/api/v2/agent/metrics'
data = {
    'agent_key': 'demo_mode_key',
    'hostname': 'BFS_Sachin',
}

print(f"Posting to {url}...")
try:
    resp = requests.post(url, json=data, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
except requests.exceptions.Timeout:
    print("Request timed out after 30 seconds!")
except Exception as e:
    print(f"Error: {e}")
