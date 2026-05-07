"""
Active Agents API Blueprint
============================
Provides real-time active agent information instead of dummy data.
"""

from flask import Blueprint, jsonify
from flask_login import login_required, current_user

from web.active_agents_monitor import ActiveAgentsMonitor

active_agents_bp = Blueprint('active_agents', __name__, url_prefix='/api/v2/agents')


@active_agents_bp.route('/active', methods=['GET'])
@login_required
def get_active_agents():
    """Get list of active agents for current tenant (or all for superadmin)"""
    try:
        if current_user.is_superadmin:
            active_agents = ActiveAgentsMonitor.get_active_agents_for_tenant(tenant_id=None)
        else:
            active_agents = ActiveAgentsMonitor.get_active_agents_for_tenant(
                tenant_id=current_user.tenant_id
            )
        
        return jsonify({
            'success': True,
            'count': len(active_agents),
            'agents': active_agents
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_agents_bp.route('/inactive', methods=['GET'])
@login_required
def get_inactive_agents():
    """Get list of inactive agents for current tenant (or all for superadmin)"""
    try:
        if current_user.is_superadmin:
            inactive_agents = ActiveAgentsMonitor.get_inactive_agents_for_tenant(tenant_id=None)
        else:
            inactive_agents = ActiveAgentsMonitor.get_inactive_agents_for_tenant(
                tenant_id=current_user.tenant_id
            )
        
        return jsonify({
            'success': True,
            'count': len(inactive_agents),
            'agents': inactive_agents
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_agents_bp.route('/status', methods=['GET'])
@login_required
def get_agents_status():
    """Get agent status summary by tenant"""
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Unauthorized'}), 403
        
        agents_by_tenant = ActiveAgentsMonitor.get_agents_by_tenant()
        
        return jsonify({
            'success': True,
            'summary': agents_by_tenant
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_agents_bp.route('/cache/clear', methods=['POST'])
@login_required
def clear_cache():
    """Clear active agents cache (admin only)"""
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Unauthorized'}), 403
        
        ActiveAgentsMonitor.clear_cache()
        
        return jsonify({
            'success': True,
            'message': 'Cache cleared'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
