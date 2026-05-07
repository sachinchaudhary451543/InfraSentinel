#!/usr/bin/env python3
"""
Launch admin portal with waitress WSGI server
"""
import os
import sys

# Add admin_portal directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'admin_portal'))

# Import app
from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("Starting ServerMonitor Admin Portal")
    print("=" * 60)
    print()
    print("Access at: http://127.0.0.1:5001")
    print("           http://localhost:5001")
    print()
    print("Login credentials:")
    print("  Username: admin")
    print("  Password: admin")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    from waitress import serve
    serve(app, host='127.0.0.1', port=5001)
