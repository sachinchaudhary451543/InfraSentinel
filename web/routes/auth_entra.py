"""
web/routes/auth_entra.py – Microsoft Entra ID Authentication Routes
===================================================================

Routes for OAuth2 login/logout using Entra ID.
Blueprint name: 'auth_entra' (avoids conflict with Flask-Login 'auth')

Endpoints:
  GET /auth/entra/login    - Redirect to Entra ID login
  GET /auth/entra/callback - Handle OAuth callback
  GET /auth/entra/logout   - Logout user
"""

import logging
from flask import Blueprint, redirect, url_for, session, request
from flask_login import login_user

from auth.entra_auth import (
    validate_configuration,
    get_authorization_url,
    handle_auth_callback,
    extract_user_info,
    get_user_role,
    CLIENT_ID
)

logger = logging.getLogger("[AUTH-ENTRA]")

# IMPORTANT: blueprint name is 'auth_entra' to avoid conflict with auth_bp ('auth')
auth_entra_bp = Blueprint('auth_entra', __name__, url_prefix='/auth/entra')


@auth_entra_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Initiate Microsoft Entra ID login."""
    # TEMPORARY: Disabled until redirect URI is registered in Azure Portal
    from flask import flash
    flash("Microsoft login is temporarily disabled. Please register 'http://localhost:8080/auth/entra/callback' in Azure Portal Authentication settings.", "warning")
    return redirect(url_for('auth.login'))
    
    if not CLIENT_ID:
        logger.error("Entra ID not configured — CLIENT_ID missing")
        from flask import flash
        flash("Microsoft login is not configured. Use username/password.", "warning")
        return redirect(url_for('auth.login'))

    try:
        validate_configuration()
    except EnvironmentError as e:
        logger.error(f"Configuration error: {e}")
        from flask import flash
        flash("Microsoft login is not configured properly.", "warning")
        return redirect(url_for('auth.login'))

    auth_url, state = get_authorization_url()
    return redirect(auth_url)


@auth_entra_bp.route('/callback')
def callback():
    """Handle OAuth callback from Entra ID."""
    code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description')

    if error:
        logger.error(f"Auth error: {error} - {error_description}")
        from flask import flash
        flash(f"Authentication failed: {error_description}", "danger")
        return redirect(url_for('auth.login'))

    if not code:
        logger.error("No authorization code in callback")
        from flask import flash
        flash("No authorization code received.", "danger")
        return redirect(url_for('auth.login'))

    # Exchange code for tokens
    token_result = handle_auth_callback(code)

    if not token_result or "access_token" not in token_result:
        logger.error("Failed to acquire token")
        from flask import flash
        flash("Failed to authenticate with Azure AD.", "danger")
        return redirect(url_for('auth.login'))

    # Extract tokens
    id_token = token_result.get("id_token", "")
    access_token = token_result.get("access_token")

    # Store access_token in session for Graph API calls
    session['access_token'] = access_token
    session['id_token'] = id_token

    # Extract user info from token claims
    user_info = extract_user_info(id_token) if id_token else {}

    # Also fetch from /me endpoint as fallback
    if not user_info.get("email"):
        try:
            import requests as req
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = req.get("https://graph.microsoft.com/v1.0/me", headers=headers, timeout=10)
            if resp.status_code == 200:
                me = resp.json()
                user_info = {
                    "email": me.get("userPrincipalName") or me.get("mail", ""),
                    "name": me.get("displayName", ""),
                    "oid": me.get("id"),
                    "tenant_id": None
                }
        except Exception as e:
            logger.error(f"Failed to fetch /me: {e}")

    email = user_info.get("email", "")
    if not email:
        from flask import flash
        flash("Could not determine your email from Azure AD.", "danger")
        return redirect(url_for('auth.login'))

    # Find or create user in Flask-Login User table
    from web.models import db, User, Tenant
    user = User.query.filter_by(username=email).first()

    if not user:
        # Create new user — assign to default tenant
        default_tenant = Tenant.query.first()
        from werkzeug.security import generate_password_hash
        import secrets
        user = User()
        user.username = email
        user.password = generate_password_hash(secrets.token_urlsafe(32))
        user.tenant_id = default_tenant.id if default_tenant else None
        user.is_superadmin = False
        user.role = 'tenant_admin'
        db.session.add(user)
        db.session.commit()
        logger.info(f"Created new user from Entra: {email}")

    # Login via Flask-Login
    login_user(user)

    # Also store Entra session data
    session['user'] = {
        'email': email,
        'name': user_info.get("name", ""),
        'oid': user_info.get("oid"),
        'tenant_id': user_info.get("tenant_id"),
        'role': get_user_role(id_token, access_token or "") if id_token else "user",
        'access_token': access_token,
        'id_token': id_token
    }
    session.permanent = True

    logger.info(f"User {email} logged in via Entra ID")
    return redirect(url_for('main.dashboard'))


@auth_entra_bp.route('/logout')
def logout():
    """Logout user and redirect to Microsoft logout endpoint."""
    from flask_login import logout_user as flask_logout
    email = session.get('user', {}).get('email', 'unknown')
    flask_logout()
    session.clear()
    logger.info(f"User {email} logged out")
    return redirect(
        "https://login.microsoftonline.com/common/oauth2/v2.0/logout"
        "?post_logout_redirect_uri=http://localhost:8080/"
    )


@auth_entra_bp.route('/user', methods=['GET'])
def get_user():
    """Get current user info from session."""
    user = session.get('user')
    if not user:
        return {'error': 'Not logged in'}, 401
    return {
        'email': user.get('email'),
        'name': user.get('name'),
        'role': user.get('role'),
        'tenant_id': user.get('tenant_id')
    }, 200
