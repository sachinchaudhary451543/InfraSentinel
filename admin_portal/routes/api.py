"""
REST API endpoints for agent registration and system management
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from admin_portal.models import Server, AgentKey, Tenant, DeploymentJob, db
from admin_portal.utils import require_tenant_access

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/systems/list', methods=['GET'])
@login_required
@require_tenant_access
def api_systems_list():
    """List all systems for current tenant (JSON API)"""
    servers = Server.query.filter_by(tenant_id=current_user.tenant_id).all()
    return jsonify([{
        'id': s.id,
        'hostname': s.hostname,
        'ip': s.ip,
        'status': 'active'
    } for s in servers])


@api_bp.route('/systems/deploy_agent', methods=['POST'])
@login_required
@require_tenant_access
def api_deploy_agent():
    """Create deployment job for agent installation"""
    if current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    server_id = data.get('server_id')
    
    server = Server.query.get_or_404(server_id)
    if server.tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Generate or get agent key
    key = AgentKey.query.filter_by(tenant_id=current_user.tenant_id).first()
    if not key:
        key = AgentKey(
            tenant_id=current_user.tenant_id,
            description='Auto-generated for deployment'
        )
        db.session.add(key)
        db.session.commit()
    
    # Create deployment job
    job = DeploymentJob(
        tenant_id=current_user.tenant_id,
        server_id=server_id,
        agent_key=key.key,
        job_type='deploy',
        status='pending'
    )
    db.session.add(job)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'job_id': job.id,
        'hostname': server.hostname,
        'agent_key': key.key
    })


@api_bp.route('/register_agent', methods=['POST'])
def api_register_agent():
    """Agent self-registration endpoint (unauthenticated)"""
    data = request.get_json()
    agent_key = data.get('agent_key')
    hostname = data.get('hostname')
    ip = data.get('ip')
    
    if not agent_key or not hostname:
        return jsonify({
            'success': False,
            'error': 'Missing agent_key or hostname'
        }), 400
    
    key_obj = AgentKey.query.filter_by(key=agent_key, is_active=True).first()
    if not key_obj:
        return jsonify({
            'success': False,
            'error': 'Invalid or inactive agent key'
        }), 403
    
    # Register or update server
    server = Server.query.filter_by(
        hostname=hostname,
        tenant_id=key_obj.tenant_id
    ).first()
    
    if not server:
        server = Server(
            hostname=hostname,
            tenant_id=key_obj.tenant_id,
            ip=ip
        )
        db.session.add(server)
    else:
        server.ip = ip
    
    db.session.commit()
    
    return jsonify({'success': True, 'server_id': server.id})


@api_bp.route('/branding', methods=['GET'])
def api_get_branding():
    """Get tenant branding (no auth required for public access)"""
    tenant_slug = request.args.get('tenant_slug')
    tenant_id = request.args.get('tenant_id')
    
    if not (tenant_slug or tenant_id):
        return jsonify({
            'company_name': 'ServerMonitor',
            'logo_url': None,
            'primary_color': '#2563eb',
            'secondary_color': '#1e40af',
            'accent_color': '#dc2626',
            'favicon_url': None
        }), 200
    
    tenant = None
    if tenant_id:
        try:
            tenant = Tenant.query.get(int(tenant_id))
        except (ValueError, TypeError):
            pass
    
    if not tenant and tenant_slug:
        # Simple slug matching on tenant name
        from admin_portal.app import _slugify_tenant
        for t in Tenant.query.all():
            if _slugify_tenant(t.name) == tenant_slug:
                tenant = t
                break
    
    if tenant:
        return jsonify(tenant.get_branding()), 200
    
    return jsonify({'error': 'Tenant not found'}), 404


@api_bp.route('/branding/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
def api_manage_branding(tenant_id):
    """Get or update tenant branding (superadmin only)"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    tenant = Tenant.query.get_or_404(tenant_id)
    
    if request.method == 'GET':
        return jsonify(tenant.get_branding()), 200
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            branding_data = {
                'company_name': data.get('company_name'),
                'logo_url': data.get('logo_url'),
                'primary_color': data.get('primary_color'),
                'secondary_color': data.get('secondary_color'),
                'accent_color': data.get('accent_color'),
                'favicon_url': data.get('favicon_url'),
            }
            # Remove None values to preserve existing values
            branding_data = {k: v for k, v in branding_data.items() if v is not None}
            tenant.update_branding(**branding_data)
            db.session.commit()
            return jsonify({
                'success': True,
                'branding': tenant.get_branding()
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400

