#!/usr/bin/env python3
"""Test direct POST to metrics endpoint."""

import requests
import json

url = 'http://localhost:5000/api/v2/agent/metrics'
data = {
    'agent_key': 'demo_mode_key',
    'hostname': 'TEST-SERVER-01',
}

print(f"Posting to {url}...")
try:
    resp = requests.post(url, json=data, timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    
    try:
        print(f"JSON Response: {resp.json()}")
    except:
        print(f"Text Response: {resp.text[:1000]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
