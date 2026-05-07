"""
Dashboard routes (main pages)
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from admin_portal.models import Tenant, Server

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index_redirect():
    """Root route - redirect to login or dashboard based on auth status"""
    if current_user.is_authenticated:
        # User is logged in, show appropriate dashboard
        if current_user.is_superadmin:
            tenants = Tenant.query.all()
            return render_template('superadmin_dashboard.html', tenants=tenants)
        else:
            servers = Server.query.filter_by(tenant_id=current_user.tenant_id).all()
            return render_template('tenant_dashboard.html', servers=servers)
    else:
        # User not authenticated, redirect to login
        return redirect(url_for('auth.login'))
