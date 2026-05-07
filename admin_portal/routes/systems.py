"""
System/Server management routes
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from admin_portal.models import Server
from admin_portal.utils import require_tenant_access

systems_bp = Blueprint('systems', __name__)


@systems_bp.route('/registered_agents')
@login_required
@require_tenant_access
def registered_agents():
    """List all registered servers/agents for current tenant"""
    # Allow superadmins to view tenant servers as well (they may have tenant_id assigned)
    servers = Server.query.filter_by(tenant_id=current_user.tenant_id).all()
    return render_template('registered_agents.html', servers=servers)
