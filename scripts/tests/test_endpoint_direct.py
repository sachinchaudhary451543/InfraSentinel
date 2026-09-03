#!/usr/bin/env python3
"""Test agent_metrics endpoint directly without going through HTTP."""

import sys
import traceback
from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response
import json

# Create a test client
from web.app import app

print("Creating Flask test client...")
client = app.test_client()

print("\nTesting /api/v2/agent/metrics endpoint...")
data = {
    'agent_key': 'demo_mode_key',
    'hostname': 'TEST-SERVER-01',
    'os_info': 'Windows-11-10.0.26200-SP0',
    'ip': '192.168.31.139',
    'logged_in_user': 'test.user',
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
    response = client.post(
        '/api/v2/agent/metrics',
        json=data,
        content_type='application/json'
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.get_json() or response.get_data(as_text=True)}")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
