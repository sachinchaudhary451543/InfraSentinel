"""Test the system_controls route to see the actual error."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import app
from web.models import db

with app.test_client() as client:
    # Login first
    client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=True)
    
    # Now hit system-controls
    resp = client.get('/assets/system-controls')
    print(f"Status: {resp.status_code}")
    if resp.status_code >= 400:
        print(f"Response body (first 5000 chars):")
        print(resp.data.decode('utf-8', errors='replace')[:5000])
