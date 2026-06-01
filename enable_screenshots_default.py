#!/usr/bin/env python3
"""Enable screenshots by default for all agent-installed servers"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from web.app import app
from web.models import db, Server

with app.app_context():
    # Find all servers with agent installed
    servers = Server.query.filter_by(agent_installed=True).all()
    
    print(f"Found {len(servers)} agent-installed servers")
    
    updated = 0
    for server in servers:
        if not server.screenshot_enabled:
            server.screenshot_enabled = True
            db.session.add(server)
            print(f"  ✓ Enabled screenshots for {server.hostname or server.name} (ID: {server.id})")
            updated += 1
    
    if updated > 0:
        try:
            db.session.commit()
            print(f"\n✓ Successfully enabled screenshots for {updated} server(s)")
        except Exception as e:
            print(f"\n✗ Failed to commit: {e}")
            db.session.rollback()
            sys.exit(1)
    else:
        print("\nNo servers needed updates")
        sys.exit(0)
