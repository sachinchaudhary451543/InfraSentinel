"""
Dashboard routes (main pages)
Defines /dashboard with proper data passing for all templates.
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from web.models import Tenant, Server, SystemAlert, VM, SystemDiscovery

logger = logging.getLogger("[MAIN]")

main_bp = Blueprint('main', __name__)


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Unified dashboard route - OPTIMIZED for performance.
    Uses batch queries instead of N+1 queries.
    Target: < 200ms vs previous 2500ms
    """
    try:
        from web.dashboard_service import OptimizedDashboardService
        import time
        
        start_time = time.time()
        
        # Fetch all data with optimized batch queries
        dashboard_data = OptimizedDashboardService.get_dashboard_data(current_user)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Log performance for monitoring
        if elapsed_ms > 500:
            logger.warning(f"Dashboard query took {elapsed_ms:.1f}ms (target: <200ms)")
        else:
            logger.debug(f"Dashboard query completed in {elapsed_ms:.1f}ms")
        
        # Debug logging
        logger.info(f"Dashboard loaded for user: {current_user.username}, tenant: {current_user.tenant_id}, servers: {dashboard_data['total_systems']}, online: {dashboard_data['online_count']}")
        
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        template_data = {
            'servers': dashboard_data['servers'],
            'inventory': dashboard_data['inventory'],
            'total_systems': dashboard_data['total_systems'],
            'agent_count': dashboard_data['agent_count'],
            'online_count': dashboard_data['online_count'],
            'alert_count': dashboard_data['alert_count'],
            'vm_count': dashboard_data['vm_count'],
            'discovered_count': dashboard_data['discovered_count'],
            'user': current_user,
            'now': now,
        }

        return render_template('dashboard.html', **template_data)

    except Exception as e:
        logger.exception(f"Dashboard error: {e}")
        # Safe fallback — render with empty data
        try:
            return render_template('dashboard.html',
                                   servers=[], inventory=[], total_systems=0, agent_count=0,
                                   online_count=0, alert_count=0,
                                   vm_count=0, discovered_count=0,
                                   user=current_user, now=datetime.now(timezone.utc).replace(tzinfo=None))
        except Exception as fallback_error:
            logger.exception(f"Dashboard fallback render failed: {fallback_error}")
            return (
                '<h1>Dashboard temporarily unavailable</h1>'
                '<p>Please refresh in a moment while telemetry data is reloading.</p>'
            ), 200


@main_bp.route('/licenses')
@login_required
def licenses_dashboard():
    """Render License Management dashboard template (admins only)."""
    try:
        if not current_user.is_superadmin:
            return redirect(url_for('main.dashboard'))
        return render_template('licenses/dashboard.html')
    except Exception as e:
        logger.error(f"Error rendering licenses dashboard: {e}")
        return redirect(url_for('main.dashboard'))

@main_bp.route('/suspended')
def suspended():
    """Landing page for users of suspended or on-hold tenants."""
    return render_template('suspended.html')
