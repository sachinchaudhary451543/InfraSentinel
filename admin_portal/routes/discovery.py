"""
Domain discovery and system import routes
"""

import logging
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from admin_portal.models import SystemDiscovery, Server, db
from admin_portal.utils import require_tenant_access
from admin_portal.models import Tenant

discovery_bp = Blueprint('discovery', __name__)


@discovery_bp.route('/discover_domain', methods=['GET', 'POST'])
@login_required
@require_tenant_access
def discover_domain():
    """Scan domain for systems using core.domain_discovery module"""
    # Allow superadmins to run discovery for their assigned tenant as well
    if request.method == 'POST':
        # Accept optional connection parameters from form: domain, tenant/company and secret
        domain_name = request.form.get('domain') or None
        company_tenant = request.form.get('company') or request.form.get('tenant') or None
        secret = request.form.get('secret') or None
        use_azure = request.form.get('use_azure') == '1'

        try:
            from core.domain_discovery import DomainDiscoveryEngine

            # If user asked to use Azure (or tenant already has creds and no domain provided),
            # attempt Azure discovery using stored tenant credentials
            tenant = db.session.get(Tenant, current_user.tenant_id)
            systems = []
            if use_azure or (not domain_name and tenant and tenant.azure_registered):
                try:
                    # Try Azure discovery with stored creds
                    azure_devices = __import__('core.azure_discovery', fromlist=['discover_devices']).discover_devices(
                        client_id=tenant.azure_client_id if tenant else None,
                        client_secret=tenant.azure_client_secret if tenant else None,
                        tenant_id=tenant.azure_tenant_id if tenant else None
                    )
                    # Convert to DiscoveredSystem-like objects
                    from core.domain_discovery import DiscoveredSystem
                    for item in azure_devices:
                        domain_value = item.get('domain') or (getattr(tenant, 'azure_display_name', None) or (tenant.name if tenant else 'azure'))
                        ds = DiscoveredSystem(
                            hostname=item.get('hostname') or 'Unknown',
                            ip_address=item.get('ip_address'),
                            os_name=item.get('os_name') or 'Unknown',
                            os_version=item.get('os_version'),
                            system_type=DomainDiscoveryEngine()._classify_system(item.get('os_name') or ''),
                            domain=domain_value,
                            ou_path=item.get('ou_path') or '',
                            mac_address=item.get('mac_address'),
                            serial_number=item.get('serial_number'),
                            discovered_at=item.get('discovered_at') or datetime.utcnow().isoformat(),
                            last_seen=item.get('last_seen') or datetime.utcnow().isoformat(),
                            enabled=item.get('enabled', True),
                            description=item.get('description')
                        )
                        systems.append(ds)
                except Exception as e:
                    logging.error(f"Azure discovery error: {e}")

            if not systems:
                # Create engine instance and attempt to pass parameters to discover_servers
                engine = DomainDiscoveryEngine()
                # Prepare kwargs dynamically to avoid static signature checks
                discover_kwargs = {}
                if domain_name:
                    discover_kwargs['domain'] = domain_name
                if company_tenant:
                    discover_kwargs['tenant'] = company_tenant
                if secret:
                    discover_kwargs['secret'] = secret

                try:
                    systems = engine.discover_servers(**discover_kwargs) if discover_kwargs else engine.discover_servers()
                except TypeError:
                    # discover_servers doesn't accept parameters - call without args
                    systems = engine.discover_servers()
            
            if systems:
                # Store discovered systems in database
                for sys_data in systems:
                    discovery = SystemDiscovery(
                        tenant_id=current_user.tenant_id,
                        hostname=sys_data.hostname,
                        ip=sys_data.ip_address,
                        os_info=sys_data.os_name,
                        source='ActiveDirectory',
                        status='pending'
                    )
                    db.session.add(discovery)
                
                db.session.commit()
                flash(f'✅ Domain scan completed. Found {len(systems)} systems.', 'success')
            else:
                flash('❌ Domain scan found no systems.', 'warning')
        except Exception as e:
            logging.error(f"Domain discovery error: {e}")
            flash(f'Error: {str(e)}', 'danger')
        
        return redirect(url_for('discovery.discover_domain'))
    
    # GET: Show discovered systems
    discoveries = SystemDiscovery.query.filter_by(
        tenant_id=current_user.tenant_id
    ).order_by(SystemDiscovery.discovered_at.desc()).all()
    tenant = db.session.get(Tenant, current_user.tenant_id)
    return render_template('discover_domain.html', discoveries=discoveries, tenant=tenant)



@discovery_bp.route('/register_azure_tenant', methods=['POST'])
@login_required
@require_tenant_access
def register_azure_tenant():
    """Register Azure credentials for the current tenant (client id, secret, tenant id)"""
    client_id = request.form.get('azure_client_id')
    client_secret = request.form.get('azure_client_secret')
    tenant_id = request.form.get('azure_tenant_id')

    if not (client_id and client_secret and tenant_id):
        flash('Please provide Client ID, Client Secret and Tenant ID', 'warning')
        return redirect(url_for('discovery.discover_domain'))

    # Validate credentials by requesting a token and fetching organization info
    try:
        from core.azure_discovery import _get_token
        token = _get_token(client_id, client_secret, tenant_id)
        if not token:
            flash('Failed to validate Azure credentials. Check permissions and try again.', 'danger')
            return redirect(url_for('discovery.discover_domain'))

        # Fetch organization info
        import requests
        resp = requests.get('https://graph.microsoft.com/v1.0/organization', headers={'Authorization': f'Bearer {token}'}, timeout=10)
        display_name = None
        if resp.status_code == 200:
            org = resp.json()
            # take displayName from first org
            value = org.get('value', [])
            if value:
                display_name = value[0].get('displayName')

        # Store credentials on tenant record
        tenant = db.session.get(Tenant, current_user.tenant_id)
        if not tenant:
            flash('Tenant record not found', 'danger')
            return redirect(url_for('discovery.discover_domain'))

        tenant.azure_client_id = client_id
        tenant.azure_client_secret = client_secret
        tenant.azure_tenant_id = tenant_id
        tenant.azure_display_name = display_name or tenant_id
        tenant.azure_registered = True
        db.session.commit()

        flash('Azure tenant registered successfully.', 'success')
    except Exception as e:
        logging.error(f"Failed to register azure tenant: {e}")
        flash('Error registering Azure tenant: ' + str(e), 'danger')

    return redirect(url_for('discovery.discover_domain'))


@discovery_bp.route('/azure_diagnostics', methods=['POST'])
@login_required
@require_tenant_access
def azure_diagnostics():
    """Run a quick token + Graph /devices check and surface actionable messages (admin consent URL).

    This endpoint is intended for admins to diagnose permission/token issues when
    registering an Azure tenant. It uses stored tenant credentials for the current
    tenant and flashes diagnostic messages back to the discover page.
    """
    tenant = db.session.get(Tenant, current_user.tenant_id)
    if not tenant or not (tenant.azure_client_id and tenant.azure_client_secret and tenant.azure_tenant_id):
        flash('Azure credentials not configured for this tenant.', 'warning')
        return redirect(url_for('discovery.discover_domain'))

    try:
        from core.azure_discovery import get_token_result
        import requests

        result = get_token_result(tenant.azure_client_id, tenant.azure_client_secret, tenant.azure_tenant_id)
        if 'access_token' not in result:
            # Show detailed AAD error and provide an admin-consent URL to simplify resolution
            err = result.get('error') or 'unknown_error'
            desc = result.get('error_description') or str(result)
            flash(f'MSAL token error: {err} - {desc}', 'danger')

            # Construct an admin consent URL (note: redirect URI must match one registered on the app)
            redirect_uri = url_for('discovery.discover_domain', _external=True)
            admin_consent_url = (
                f'https://login.microsoftonline.com/{tenant.azure_tenant_id}/adminconsent?client_id={tenant.azure_client_id}'
                f'&redirect_uri={redirect_uri}'
            )
            flash('If you are an Azure admin you can attempt to grant admin consent: ' + admin_consent_url, 'info')
            return redirect(url_for('discovery.discover_domain'))

        # If we have a token, try a Graph /devices call to check permissions
        token = result.get('access_token')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        resp = requests.get('https://graph.microsoft.com/v1.0/devices', headers=headers, timeout=10)
        if resp.status_code != 200:
            # Permission issue or other problem
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            flash(f'Graph /devices returned {resp.status_code}: {body}', 'danger')
            # Suggest admin consent URL as above
            redirect_uri = url_for('discovery.discover_domain', _external=True)
            admin_consent_url = (
                f'https://login.microsoftonline.com/{tenant.azure_tenant_id}/adminconsent?client_id={tenant.azure_client_id}'
                f'&redirect_uri={redirect_uri}'
            )
            flash('To resolve insufficient privileges, an Azure admin must grant Application permissions (Directory.Read.All, Device.Read.All, DeviceManagementManagedDevices.Read.All) and then grant admin consent in the Portal. Use this URL to start the admin consent flow: ' + admin_consent_url, 'info')
            return redirect(url_for('discovery.discover_domain'))

        flash('Azure diagnostics: token and /devices call succeeded.', 'success')
    except Exception as e:
        logging.error(f'Azure diagnostics failed: {e}')
        flash(f'Azure diagnostics error: {e}', 'danger')

    return redirect(url_for('discovery.discover_domain'))


@discovery_bp.route('/import_discovered/<int:discovery_id>', methods=['POST'])
@login_required
@require_tenant_access
def import_discovered(discovery_id):
    """Import a single discovered system to managed servers"""
    # Allow superadmins to import discovered systems for their tenant
    discovery = SystemDiscovery.query.get_or_404(discovery_id)
    if discovery.tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if already imported
    existing = Server.query.filter_by(
        hostname=discovery.hostname,
        tenant_id=current_user.tenant_id
    ).first()
    if existing:
        return jsonify({'error': 'System already imported'}), 400
    
    # Create server record
    server = Server(
        hostname=discovery.hostname,
        tenant_id=current_user.tenant_id,
        ip=discovery.ip
    )
    db.session.add(server)
    discovery.status = 'imported'
    discovery.imported_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'status': 'success', 'server_id': server.id})


@discovery_bp.route('/bulk_import_discovered', methods=['POST'])
@login_required
@require_tenant_access
def bulk_import_discovered():
    """Bulk import all pending discovered systems"""
    # Allow superadmins to bulk import for their assigned tenant
    pending = SystemDiscovery.query.filter_by(
        tenant_id=current_user.tenant_id,
        status='pending'
    ).all()
    
    imported = 0
    for discovery in pending:
        existing = Server.query.filter_by(
            hostname=discovery.hostname,
            tenant_id=current_user.tenant_id
        ).first()
        if not existing:
            server = Server(
                hostname=discovery.hostname,
                tenant_id=current_user.tenant_id,
                ip=discovery.ip
            )
            db.session.add(server)
            discovery.status = 'imported'
            discovery.imported_at = datetime.utcnow()
            imported += 1
    
    db.session.commit()
    return jsonify({'status': 'success', 'imported': imported})
