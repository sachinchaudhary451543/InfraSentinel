"""
Tenant management routes
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
import logging
from flask_login import login_required

from web.models import Tenant, Server, Metric, db
from web.utils import require_superadmin

tenants_bp = Blueprint('tenants', __name__)

@tenants_bp.route('/tenants', methods=['GET'])
@login_required
@require_superadmin
def list_tenants():
    """List all tenants with enriched metadata (superadmin only)"""
    tenants_list = Tenant.query.all()
    
    # Enrich each tenant with live statistics
    enriched = []
    for t in tenants_list:
        servers = Server.query.filter_by(tenant_id=t.id).all()
        total_devices = len(servers)
        agent_installed = sum(1 for s in servers if s.agent_installed)
        online_now = sum(1 for s in servers if s.status == 'online' or s.agent_installed == 1)
        
        # Last activity: most recent last_seen across all servers
        last_activity = None
        for s in servers:
            if s.last_seen and (last_activity is None or s.last_seen > last_activity):
                last_activity = s.last_seen
        
        enriched.append({
            'tenant': t,
            'total_devices': total_devices,
            'agent_installed': agent_installed,
            'online_now': online_now,
            'last_activity': last_activity,
        })
    
    return render_template('tenants.html', tenants_data=enriched)

@tenants_bp.route('/add_tenant', methods=['GET', 'POST'])
@login_required
@require_superadmin
def add_tenant():
    """Add new tenant (superadmin only)"""
    if request.method == 'POST':
        name = request.form['name']
        if name:
            # Check for duplicate
            if Tenant.query.filter_by(name=name).first():
                flash('Tenant name already exists', 'danger')
                return redirect(url_for('tenants.add_tenant'))
            
            t = Tenant(name=name)
            db.session.add(t)
            db.session.commit()
            flash(f'✅ Tenant "{name}" created successfully', 'success')
            return redirect(url_for('main.dashboard'))
    
    return render_template('add_tenant.html')


@tenants_bp.route('/manage_azure/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
@require_superadmin
def manage_tenant_azure(tenant_id):
    """Allow superadmins to register or update Azure credentials for a tenant."""
    t = db.get_or_404(Tenant, tenant_id)
    if request.method == 'POST':
        client_id = request.form.get('azure_client_id')
        client_secret = request.form.get('azure_client_secret')
        tenant_id_field = request.form.get('azure_tenant_id')
        interval = request.form.get('polling_interval_minutes', type=int) or 60
        
        if not (client_id and client_secret and tenant_id_field):
            flash('Please provide Client ID, Client Secret and Tenant ID', 'warning')
            return redirect(url_for('tenants.manage_tenant_azure', tenant_id=t.id))

        try:
            from core.azure_discovery import get_token_result
            import requests

            result = get_token_result(client_id, client_secret, tenant_id_field)
            if 'access_token' not in result:
                flash('MSAL token error: ' + (result.get('error_description') or str(result)), 'danger')
                return redirect(url_for('tenants.manage_tenant_azure', tenant_id=t.id))

            # fetch org display name
            token = result.get('access_token')
            resp = requests.get('https://graph.microsoft.com/v1.0/organization', headers={'Authorization': f'Bearer {token}'}, timeout=10)
            display_name = None
            if resp.status_code == 200:
                org = resp.json()
                value = org.get('value', [])
                if value:
                    display_name = value[0].get('displayName')

            t.azure_client_id = client_id
            t.azure_client_secret = client_secret
            t.azure_tenant_id = tenant_id_field
            t.azure_display_name = display_name or tenant_id_field
            t.azure_registered = True
            t.polling_interval_minutes = interval
            
            # If site_url present in form, save it as SharePoint site to connect
            sp_site = request.form.get('sharepoint_site_url')
            if sp_site:
                t.sharepoint_site_url = sp_site
                t.sharepoint_connected = True  # Mark as connected when URL is provided
            
            # Save SharePoint sync configs
            auto_sync = request.form.get('sharepoint_auto_sync') == 'on'
            t.sharepoint_auto_sync = auto_sync
            t.sharepoint_sync_interval_minutes = request.form.get('sharepoint_sync_interval_minutes', type=int) or 60
            
            db.session.commit()
            flash('Azure credentials saved for tenant: ' + t.name, 'success')
            return redirect(url_for('tenants.add_tenant'))
        except Exception as e:
            logging.error(f'Failed to save azure creds for tenant {t.id}: {e}')
            flash('Error: ' + str(e), 'danger')
            return redirect(url_for('tenants.manage_tenant_azure', tenant_id=t.id))

    return render_template('manage_tenant_azure.html', tenant=t)

