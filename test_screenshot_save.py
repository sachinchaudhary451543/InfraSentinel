#!/usr/bin/env python3
"""Test script to debug screenshot saving"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from web.app import app
from web.models import db, Screenshot, Server
from datetime import datetime
import base64
import io
from PIL import ImageGrab

with app.app_context():
    # Get a server
    server = Server.query.first()
    if not server:
        print("ERROR: No server found in database!")
        sys.exit(1)
    
    print(f"Testing with server: {server.hostname} (ID: {server.id})")
    
    # Create a test screenshot
    try:
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='JPEG', quality=60)
        img_byte_arr.seek(0)
        img_bytes = img_byte_arr.getvalue()
        
        print(f"Screenshot captured: {len(img_bytes)} bytes")
        
        # Now try to save it the way the API does
        ext = 'jpg'
        ts_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        fname = f"screenshot_{server.id}_{server.hostname}_{ts_str}.{ext}"
        
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'screenshots'
        )
        os.makedirs(base_dir, exist_ok=True)
        file_path = os.path.join(base_dir, fname)
        
        with open(file_path, 'wb') as f:
            f.write(img_bytes)
        
        print(f"Screenshot saved to: {file_path}")
        print(f"File exists: {os.path.isfile(file_path)}")
        
        # Now try to save to database
        shot = Screenshot()
        shot.server_id = server.id
        shot.tenant_id = server.tenant_id
        shot.filename = fname
        shot.hostname = server.hostname
        shot.captured_at = datetime.utcnow()
        shot.uploaded_at = datetime.utcnow()
        shot.uploaded = False
        shot.file_size_kb = len(img_bytes) // 1024
        shot.active_user = 'testuser'
        shot.os_info = 'Windows 10'
        shot.ip_address = '127.0.0.1'
        shot.local_file_path = os.path.abspath(file_path)
        
        db.session.add(shot)
        print(f"Screenshot object created and added to session")
        print(f"  Local file path: {shot.local_file_path}")
        
        db.session.commit()
        print(f"Screenshot saved to database with ID: {shot.id}")
        
        # Verify it's in the database
        check = Screenshot.query.get(shot.id)
        if check:
            print(f"✓ Verified: Screenshot {check.id} in database")
            print(f"  Filename: {check.filename}")
            print(f"  Local path: {check.local_file_path}")
        else:
            print("✗ ERROR: Screenshot not found in database after commit!")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
