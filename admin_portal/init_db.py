#!/usr/bin/env python3
"""
Initialize admin portal database with default users and tenants
Run this ONCE to set up the database
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, User, Tenant
from werkzeug.security import generate_password_hash

def init_database():
    """Create tables and add default admin user"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✓ Database tables created")
        
        # Check if admin user already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("✓ Admin user already exists - skipping creation")
            return
        
        # Create default tenant
        default_tenant = Tenant.query.filter_by(name='Default Tenant').first()
        if not default_tenant:
            default_tenant = Tenant(name='Default Tenant')
            db.session.add(default_tenant)
            db.session.commit()
            print(f"✓ Created default tenant (ID: {default_tenant.id})")
        else:
            print(f"✓ Default tenant already exists (ID: {default_tenant.id})")
        
        # Create default admin user
        # Password: admin (you SHOULD change this!)
        admin = User(
            username='admin',
            password=generate_password_hash('admin'),
            tenant_id=default_tenant.id,
            is_superadmin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Created default admin user")
        print(f"\n  Username: admin")
        print(f"  Password: admin")
        print(f"\n  ⚠️  IMPORTANT: Change this password immediately after first login!")
        print(f"\n  Access the portal at: http://127.0.0.1:5001")

if __name__ == '__main__':
    init_database()
    print("\n✓ Database initialized successfully!")
