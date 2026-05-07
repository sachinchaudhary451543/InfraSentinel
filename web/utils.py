"""
Authentication and authorization utilities
"""

from functools import wraps
from flask import redirect, url_for, flash, g
from flask_login import current_user, logout_user

from web.models import Tenant, db


def require_superadmin(f):
    """Decorator to require superadmin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_superadmin:
            return 'Unauthorized', 403
        return f(*args, **kwargs)
    return decorated_function


def require_tenant_access(f):
    """Decorator to validate current user has valid tenant access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user or not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.tenant_id:
            tenant = db.session.get(Tenant, current_user.tenant_id)
            if not tenant:
                logout_user()
                flash("Your tenant has been deleted", "danger")
                return redirect(url_for('auth.login'))
        if not current_user.is_superadmin and not current_user.tenant_id:
            logout_user()
            flash("Account misconfiguration: No tenant assigned", "danger")
            return redirect(url_for('auth.login'))
        requested_tenant_id = getattr(g, 'request_tenant_id', None)
        if (
            requested_tenant_id
            and not current_user.is_superadmin
            and current_user.tenant_id != requested_tenant_id
        ):
            return 'Unauthorized', 403
        return f(*args, **kwargs)
    return decorated_function
