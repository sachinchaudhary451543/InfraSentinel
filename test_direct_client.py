#!/usr/bin/env python3
"""Test agent_metrics endpoint using Flask test client."""

import sys
import json

try:
    from web.app import app
    
    print("Creating test client...")
    client = app.test_client()
    
    print("\nPosting to /api/v2/agent/metrics...")
    data = {
        'agent_key': 'demo_mode_key',
        'hostname': 'TEST-SERVER-01',
        'metrics': {
            'cpu_percent': 25.5,
            'ram_percent': 50.2,
        }
    }
    
    response = client.post(
        '/api/v2/agent/metrics',
        data=json.dumps(data),
        content_type='application/json'
    )
    
    print(f"Status: {response.status_code}")
    
    try:
        resp_json = response.get_json()
        print(f"JSON Response: {json.dumps(resp_json, indent=2)}")
    except:
        print(f"Text Response: {response.get_data(as_text=True)[:1000]}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
