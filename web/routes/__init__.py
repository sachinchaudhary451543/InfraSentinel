"""
Admin Portal Routes Package

This module contains all Flask blueprints for the admin portal.
Blueprints are imported and registered in the main app.py.
"""

from web.routes.auth import auth_bp
from web.routes.users import users_bp
from web.routes.tenants import tenants_bp
from web.routes.agents import agents_bp
from web.routes.deployment import deployment_bp
from web.routes.api import api_bp
from web.routes.main import main_bp
from web.routes.sharepoint import sharepoint_bp
# Analytics, license management and status management are imported
# conditionally from the main application module after extensions
# (like caching) are initialized to avoid circular import issues.

__all__ = [
    'auth_bp',
    'users_bp',
    'tenants_bp',
    'agents_bp',
    'deployment_bp',
    'api_bp',
    'main_bp',
    'sharepoint_bp',
    # analytics/license/status blueprints are registered explicitly by the app
]
