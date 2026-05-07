"""
Admin Portal Routes Package

This module contains all Flask blueprints for the admin portal.
Blueprints are imported and registered in the main app.py.
"""

from admin_portal.routes.auth import auth_bp
from admin_portal.routes.users import users_bp
from admin_portal.routes.tenants import tenants_bp
from admin_portal.routes.agents import agents_bp
from admin_portal.routes.systems import systems_bp
from admin_portal.routes.discovery import discovery_bp
from admin_portal.routes.deployment import deployment_bp
from admin_portal.routes.api import api_bp
from admin_portal.routes.main import main_bp

__all__ = [
    'auth_bp',
    'users_bp',
    'tenants_bp',
    'agents_bp',
    'systems_bp',
    'discovery_bp',
    'deployment_bp',
    'api_bp',
    'main_bp',
]
