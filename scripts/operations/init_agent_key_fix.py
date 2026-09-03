#!/usr/bin/env python3
"""
Quick fix to ensure demo_mode_key exists in AgentKey table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress Flask debug messages
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

from web.app import app
from web.models import db, AgentKey, Tenant

print("\n" + "="*80)
print("AGENT KEY INITIALIZATION")
print("="*80 + "\n")

with app.app_context():
    try:
        # Ensure Tenant exists
        default_tenant = Tenant.query.filter_by(name='Default Tenant').first()
        if not default_tenant:
            print("Creating default tenant...")
            default_tenant = Tenant()
            default_tenant.name = 'Default Tenant'
            db.session.add(default_tenant)
            db.session.commit()
            print(f"✓ Default tenant created (ID: {default_tenant.id})")
        else:
            print(f"✓ Default tenant exists (ID: {default_tenant.id})")
        
        # Check if demo_mode_key exists
        existing_key = AgentKey.query.filter_by(key='demo_mode_key').first()
        
        if existing_key:
            print(f"\n✓ AgentKey 'demo_mode_key' already exists:")
            print(f"  - Tenant ID: {existing_key.tenant_id}")
            print(f"  - Active: {existing_key.is_active}")
        else:
            print("\n✗ Creating 'demo_mode_key'...")
            new_key = AgentKey()
            new_key.key = 'demo_mode_key'
            new_key.tenant_id = default_tenant.id
            new_key.is_active = True
            new_key.key_name = 'Demo Mode'
            new_key.description = 'Demo mode key for testing agent metrics'
            
            db.session.add(new_key)
            db.session.commit()
            
            print(f"✓ AgentKey created successfully!")
            print(f"  - Key: {new_key.key}")
            print(f"  - Tenant ID: {new_key.tenant_id}")
            print(f"  - Active: {new_key.is_active}")
        
        print("\n" + "="*80)
        print("✓ Setup Complete! Agent key is ready.")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
