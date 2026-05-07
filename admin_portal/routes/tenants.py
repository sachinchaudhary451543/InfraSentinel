"""
Tenant management routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
import logging
from flask_login import login_required

from admin_portal.models import Tenant, db
from admin_portal.utils import require_superadmin

tenants_bp = Blueprint('tenants', __name__)


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
            return redirect(url_for('main.index_redirect'))
    
    return render_template('add_tenant.html')


@tenants_bp.route('/manage_azure/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
@require_superadmin
def manage_azure(tenant_id):
    """Allow superadmins to register or update Azure credentials for a tenant."""
    t = Tenant.query.get_or_404(tenant_id)
    if request.method == 'POST':
        client_id = request.form.get('azure_client_id')
        client_secret = request.form.get('azure_client_secret')
        tenant_id_field = request.form.get('azure_tenant_id')
        if not (client_id and client_secret and tenant_id_field):
            flash('Please provide Client ID, Client Secret and Tenant ID', 'warning')
            return redirect(url_for('tenants.manage_azure', tenant_id=t.id))

        try:
            from core.azure_discovery import get_token_result
            import requests

            result = get_token_result(client_id, client_secret, tenant_id_field)
            if 'access_token' not in result:
                flash('MSAL token error: ' + (result.get('error_description') or str(result)), 'danger')
                return redirect(url_for('tenants.manage_azure', tenant_id=t.id))

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
            db.session.commit()
            flash('Azure credentials saved for tenant: ' + t.name, 'success')
            return redirect(url_for('tenants.add_tenant'))
        except Exception as e:
            logging.error(f'Failed to save azure creds for tenant {t.id}: {e}')
            flash('Error: ' + str(e), 'danger')
            return redirect(url_for('tenants.manage_azure', tenant_id=t.id))

    return render_template('manage_tenant_azure.html', tenant=t)


@tenants_bp.route('/manage_branding/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
@require_superadmin
def manage_branding(tenant_id):
    """Manage tenant white-label branding."""
    t = Tenant.query.get_or_404(tenant_id)
    
    if request.method == 'POST':
        try:
            branding_data = {
                'company_name': request.form.get('company_name', '').strip() or t.name,
                'logo_url': request.form.get('logo_url', '').strip() or None,
                'primary_color': request.form.get('primary_color', '').strip() or '#2563eb',
                'secondary_color': request.form.get('secondary_color', '').strip() or '#1e40af',
                'accent_color': request.form.get('accent_color', '').strip() or '#dc2626',
                'favicon_url': request.form.get('favicon_url', '').strip() or None,
            }
            t.update_branding(**branding_data)
            db.session.commit()
            flash(f'✅ Branding for "{t.name}" updated successfully', 'success')
            return redirect(url_for('tenants.manage_branding', tenant_id=t.id))
        except Exception as e:
            logging.error(f'Failed to update branding for tenant {t.id}: {e}')
            flash(f'Error updating branding: {str(e)}', 'danger')
            return redirect(url_for('tenants.manage_branding', tenant_id=t.id))
    
    return render_template('manage_tenant_branding.html', tenant=t)

