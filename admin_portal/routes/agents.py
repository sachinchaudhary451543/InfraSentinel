"""
Agent key management routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from admin_portal.models import AgentKey
from admin_portal.utils import require_tenant_access

agents_bp = Blueprint('agents', __name__)


@agents_bp.route('/agent_keys', methods=['GET', 'POST'])
@login_required
@require_tenant_access
def agent_keys():
    """Manage agent API keys for current tenant"""
    # Allow superadmins to manage/view agent keys for their tenant
    if request.method == 'POST':
        key_name = request.form.get('key_name')
        desc = request.form.get('description')
        
        if not key_name:
            flash('Key name is required', 'danger')
            return redirect(url_for('agents.agent_keys'))
        
        from admin_portal.models import db
        key = AgentKey(
            tenant_id=current_user.tenant_id,
            key_name=key_name,
            description=desc
        )
        db.session.add(key)
        db.session.commit()
        flash(f'✅ Agent key "{key_name}" generated successfully', 'success')
        
    keys = AgentKey.query.filter_by(tenant_id=current_user.tenant_id).all()
    return render_template('agent_keys.html', keys=keys)


@agents_bp.route('/deactivate_key/<int:key_id>', methods=['GET', 'POST'])
@login_required
@require_tenant_access
def deactivate_key(key_id):
    """Deactivate an agent API key"""
    key = AgentKey.query.get_or_404(key_id)
    
    if key.tenant_id != current_user.tenant_id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('agents.agent_keys')), 403
    
    from admin_portal.models import db
    key.is_active = False
    db.session.commit()
    flash(f'Key "{key.key_name}" deactivated', 'success')
    
    return redirect(url_for('agents.agent_keys'))
