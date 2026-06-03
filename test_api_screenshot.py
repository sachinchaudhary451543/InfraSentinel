#!/usr/bin/env python3
"""Test API endpoint directly"""
import sys
import os
import json
import base64
import io
sys.path.insert(0, os.path.dirname(__file__))

from web.app import app
from web.models import db, Server, Screenshot
from datetime import datetime
from PIL import ImageGrab
import requests

# Start the Flask app in a test client
client = app.test_client()

with app.app_context():
    # Get server and API key
    server = Server.query.first()
    if not server:
        print("ERROR: No server in database")
        sys.exit(1)
    
    # Get the agent API key
    if not server.api_key:
        print("ERROR: Server has no api_key. Setting a test key...")
        server.api_key = 'test-agent-key-12345'
        db.session.commit()
    api_key = server.api_key
    
    print(f"Server: {server.hostname} (ID: {server.id})")
    print(f"API Key: {api_key}")
    print(f"Screenshot enabled: {server.screenshot_enabled}")
    
    # Create a test screenshot
    screenshot = ImageGrab.grab()
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='JPEG', quality=60)
    img_byte_arr.seek(0)
    base64_str = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    
    # Create a test payload similar to what the agent sends
    payload = {
        'api_key': api_key,
        'hostname': server.hostname,
        'ip': '192.168.1.1',
        'os_info': 'Windows 10',
        'logged_in_user': 'testuser',
        'idle_time_seconds': 0,
        'metrics': {
            'cpu_percent': 25.5,
            'ram_percent': 50.0,
            'disk_percent': 30.0,
            'ram_gb': 8.0,
            'ram_total': 16.0,
            'disk_gb': 500.0,
            'disk_total': 1000.0,
            'virtual_cores': 4
        },
        'screenshot': {
            'success': True,
            'image': base64_str,
            'format': 'jpeg',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    }
    
    # Count screenshots before
    count_before = Screenshot.query.count()
    print(f"Screenshots in DB before: {count_before}")
    
    # Send to the API
    print("\nSending metrics to /api/v2/agent/metrics...")
    response = client.post('/api/v2/agent/metrics', json=payload)
    print(f"Response status: {response.status_code}")
    print(f"Response: {response.get_json()}")
    
    # Count screenshots after
    count_after = Screenshot.query.count()
    print(f"\nScreenshots in DB after: {count_after}")
    
    if count_after > count_before:
        print(f"✓ SUCCESS: {count_after - count_before} screenshot(s) saved!")
        # Show the latest screenshot
        latest = Screenshot.query.order_by(Screenshot.id.desc()).first()
        print(f"  Latest screenshot ID: {latest.id}")
        print(f"  Filename: {latest.filename}")
        print(f"  Local path: {latest.local_file_path}")
        print(f"  File exists: {os.path.isfile(latest.local_file_path) if latest.local_file_path else False}")
    else:
        print("✗ FAILED: No screenshots saved!")
