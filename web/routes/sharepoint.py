"""
SharePoint OAuth Authorization Code flow routes

Provides a start URL to redirect admins to Microsoft login and a callback to
exchange the code and persist the tenant's SharePoint configuration via the
existing msal_auth encrypt_config shim.
"""
from flask import Blueprint, redirect, request, url_for, render_template, flash
from flask_login import login_required, current_user
from web.utils import require_superadmin
from web.models import Tenant, db

from auth.msal_auth import get_authorization_url, acquire_token_by_auth_code, decrypt_config, encrypt_config, clear_token_cache

sharepoint_bp = Blueprint('sharepoint', __name__, url_prefix='/sharepoint')


@sharepoint_bp.route('/connect', methods=['GET'])
@login_required
@require_superadmin
def sharepoint_connect():
    """Redirect the admin to Microsoft login to authorize delegated access.

    Query params:
      - site_url (required): the tenant SharePoint site URL to use after auth
      - state (optional): opaque state passed through to callback
    """
    site_url = request.args.get('site_url')
    if not site_url:
        return render_template('sharepoint_connect.html'), 400

    redirect_uri = url_for('sharepoint.sharepoint_callback', _external=True)
    # Encode site_url into state so callback can persist it after exchange
    import base64, json
    state_payload = {'site_url': site_url}
    orig_state = request.args.get('state')
    if orig_state:
        state_payload['orig_state'] = str(orig_state)
    state_b64 = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode()
    auth_url = get_authorization_url(redirect_uri=redirect_uri, state=state_b64)
    # Prompt account selection to ensure admin picks correct identity
    return redirect(auth_url + "&prompt=select_account")


@sharepoint_bp.route('/callback')
def sharepoint_callback():
    """Authorization Code callback: exchange code and persist config."""
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        return f"Auth error: {error}", 400
    if not code:
        return "Missing code in callback", 400

    # Decode state to retrieve original site_url
    state = request.args.get('state')
    site_url = None
    if state:
        try:
            import base64, json
            raw = base64.urlsafe_b64decode(state.encode()).decode()
            payload = json.loads(raw)
            site_url = payload.get('site_url')
        except Exception:
            site_url = None

    config = decrypt_config() or {}
    redirect_uri = url_for('sharepoint.sharepoint_callback', _external=True)

    try:
        result = acquire_token_by_auth_code(auth_code=code, redirect_uri=redirect_uri)
    except Exception as e:
        return f"Token exchange failed: {e}", 500

    # Persist minimal information (do NOT store access_token directly; encrypt_config
    # strips ephemeral fields). Store detected tenant_id and the provided site_url.
    tid = None
    if isinstance(result, dict):
        id_claims = result.get('id_token_claims', {})
        tid = id_claims.get('tid') or result.get('tenant_id')

    if tid:
        config['tenant_id'] = tid
    if site_url:
        config['sharepoint_site_url'] = site_url

    try:
        encrypt_config(config)
    except Exception:
        pass

    # If admin completed the flow from the tenant UI, persist to Tenant DB
    try:
        if current_user and hasattr(current_user, 'tenant_id') and current_user.tenant_id:
            t = db.get_or_404(Tenant, current_user.tenant_id)
            if site_url:
                t.sharepoint_site_url = site_url
            t.sharepoint_connected = True
            db.session.commit()
    except Exception:
        pass

    return render_template('sharepoint_callback.html', success=True, tenant_id=tid)


@sharepoint_bp.route('/disconnect', methods=['POST', 'GET'])
@login_required
@require_superadmin
def sharepoint_disconnect():
    """Disconnect tenant SharePoint delegated auth: clear MSAL cache and mark tenant disconnected."""
    tenant_id = request.args.get('tenant_id') or request.form.get('tenant_id')
    try:
        clear_token_cache()
    except Exception:
        pass

    if tenant_id:
        try:
            t = db.get_or_404(Tenant, int(tenant_id))
            t.sharepoint_connected = False
            db.session.commit()
        except Exception:
            pass

    flash('SharePoint disconnected (token cache cleared).', 'info')
    return redirect(url_for('tenants.manage_tenant_azure', tenant_id=tenant_id or (current_user.tenant_id or 0)))
