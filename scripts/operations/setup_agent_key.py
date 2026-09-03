#!/usr/bin/env python3
"""
Setup script to create the demo_mode_key in AgentKeys table
This is needed for agents to send metrics to the API
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.models import db, AgentKey
from web.app import app

with app.app_context():
    print("=" * 80)
    print("AGENT KEY SETUP")
    print("=" * 80)
    
    # Check if demo_mode_key already exists
    existing_key = AgentKey.query.filter_by(key='demo_mode_key').first()
    
    if existing_key:
        print(f"\n✓ AgentKey 'demo_mode_key' already exists:")
        print(f"  - Key: {existing_key.key}")
        print(f"  - Tenant ID: {existing_key.tenant_id}")
        print(f"  - Active: {existing_key.is_active}")
        print(f"  - Created: {existing_key.created_at}")
    else:
        # Create the key
        print("\n✗ AgentKey 'demo_mode_key' not found. Creating...")
        
        new_key = AgentKey()
        new_key.key = 'demo_mode_key'
        new_key.tenant_id = 1
        new_key.is_active = True
        new_key.key_name = 'Demo Mode'
        new_key.description = 'Demo mode key for testing agent metrics'
        
        db.session.add(new_key)
        db.session.commit()
        
        print(f"\n✓ AgentKey created successfully:")
        print(f"  - Key: {new_key.key}")
        print(f"  - Tenant ID: {new_key.tenant_id}")
        print(f"  - Active: {new_key.is_active}")
        print(f"  - Created: {new_key.created_at}")
    
    print("\n" + "=" * 80)
    print("NEXT STEP: Run test_agent_send_metrics.py again")
    print("=" * 80)
