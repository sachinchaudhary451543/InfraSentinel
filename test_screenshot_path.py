#!/usr/bin/env python3
"""Test screenshot path calculation in agent_metrics endpoint"""
import sys
import os
import json
import base64
sys.path.insert(0, os.path.dirname(__file__))

from web.app import app
from web.models import db, Server, Screenshot
from io import BytesIO
from PIL import Image
from datetime import datetime

# Create a test image
img = Image.new('RGB', (100, 100), color='red')
img_byte_arr = BytesIO()
img.save(img_byte_arr, format='JPEG', quality=60)
img_byte_arr.seek(0)
base64_str = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

client = app.test_client()

with app.app_context():
    server = Server.query.first()
    if not server:
        print("ERROR: No server in database")
        sys.exit(1)
    
    if not server.api_key:
        server.api_key = 'testkey123'
        db.session.commit()
    
    # Create a metrics payload with screenshot
    payload = {
        'api_key': server.api_key,
        'hostname': server.hostname or 'test-server',
        'ip': '192.168.1.100',
        'os_info': 'Windows 10',
        'logged_in_user': 'testuser',
        'metrics': {
            'cpu_percent': 45.2,
            'ram_percent': 62.1,
            'total_ram_gb': 16,
            'used_ram_gb': 10,
            'disk_percent': 55,
            'total_disk_gb': 512,
            'used_disk_gb': 280,
        },
        'screenshot': {
            'success': True,
            'image': base64_str,
            'format': 'jpeg'
        }
    }
    
    # Send to the metrics endpoint
    resp = client.post('/api/v2/agent/metrics', json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.get_json()}")
    
    # Check if screenshot was created
    latest_shot = Screenshot.query.order_by(Screenshot.id.desc()).first()
    if latest_shot:
        print(f"\nLatest screenshot:")
        print(f"  ID: {latest_shot.id}")
        print(f"  Filename: {latest_shot.filename}")
        print(f"  Local path: {latest_shot.local_file_path}")
        print(f"  File exists: {os.path.isfile(latest_shot.local_file_path) if latest_shot.local_file_path else False}")
        
        # Check path consistency
        if latest_shot.local_file_path:
            abs_path = os.path.abspath(latest_shot.local_file_path)
            print(f"  Normalized path: {abs_path}")
            print(f"  Path contains ServerMonitor: {'ServerMonitor' in abs_path}")
            data_screenshots_path = os.path.join('data', 'screenshots')
            print(f"  Path contains {data_screenshots_path}: {data_screenshots_path in abs_path}")
