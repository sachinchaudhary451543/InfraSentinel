"""
Deployment job tracking and status routes
"""

from flask import Blueprint, jsonify
from flask_login import login_required, current_user

from admin_portal.models import DeploymentJob, Server, db
from admin_portal.utils import require_tenant_access

deployment_bp = Blueprint('deployment', __name__)


@deployment_bp.route('/api/deployment/status/<int:job_id>', methods=['GET'])
@login_required
@require_tenant_access
def api_deployment_status(job_id):
    """Get deployment job status and logs"""
    job = DeploymentJob.query.get_or_404(job_id)
    server = db.session.get(Server, job.server_id)
    
    if not server or server.tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'job_id': job.id,
        'hostname': server.hostname,
        'status': job.status,
        'job_type': job.job_type,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'log_output': job.log_output
    })
