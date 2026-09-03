"""
Authentication and authorization utilities
"""

from functools import wraps
from flask import redirect, url_for, flash, g
from flask_login import current_user, logout_user
import re

from web.models import Tenant, db


def validate_password(password, username=None):
    """Return an actionable validation message, or None when the password is acceptable."""
    value = password or ''
    if len(value) < 12:
        return 'Password must be at least 12 characters long.'
    if len(value) > 128:
        return 'Password must not exceed 128 characters.'
    if username and username.lower() in value.lower():
        return 'Password must not contain the username.'
    if not re.search(r'[A-Z]', value):
        return 'Password must contain at least one uppercase letter.'
    if not re.search(r'[a-z]', value):
        return 'Password must contain at least one lowercase letter.'
    if not re.search(r'\d', value):
        return 'Password must contain at least one number.'
    if not re.search(r'[^A-Za-z0-9]', value):
        return 'Password must contain at least one special character.'
    return None


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
            tenant_status = tenant.status or 'active'
            if tenant_status != 'active' and not current_user.is_superadmin:
                return redirect(url_for('main.suspended'))
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


def require_role(*roles):
    """
    Decorator to enforce Role-Based Access Control (RBAC).
    Allowed roles: 'super_admin', 'org_admin', 'hr_admin', 'screen_monitor', 'manager', 'employee'.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user or not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Super admins bypass all role checks
            if current_user.is_superadmin or current_user.role == 'super_admin':
                return f(*args, **kwargs)
                
            if current_user.role not in roles:
                flash("You do not have permission to access this resource.", "danger")
                return 'Forbidden', 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_allowed_employee_ids(user) -> list[int]:
    """
    Returns a list of employee IDs the given user is allowed to view.
    - super_admin / org_admin / hr_admin: Returns None (meaning all employees in tenant).
    - manager: Returns their own employee_id + all subordinates.
    - employee: Returns only their own employee_id.
    """
    if user.is_superadmin or user.role in ['super_admin', 'org_admin', 'hr_admin']:
        return None
        
    if not user.employee_id:
        return [] # No employee mapped, no access
        
    from web.models import Employee
    
    if user.role == 'employee':
        return [user.employee_id]
        
    if user.role == 'manager':
        # Find all subordinates
        subordinates = Employee.query.filter_by(
            tenant_id=user.tenant_id, 
            manager_id=user.employee_id
        ).all()
        
        allowed_ids = [user.employee_id] + [sub.id for sub in subordinates]
        return allowed_ids
        
    return []
