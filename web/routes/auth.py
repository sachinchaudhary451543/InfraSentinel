"""
Authentication routes (login, logout, register)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import check_password_hash, generate_password_hash
import time
import logging

from web.models import User, Tenant, AgentKey, db

logger = logging.getLogger("[AUTH]")

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        org_id = (request.form.get('org_id') or '').strip()
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not org_id:
            flash('Organization ID is required to sign in.', 'danger')
            return render_template('login.html'), 400

        # Resolve tenant by UUID or name
        tenant = Tenant.query.filter((Tenant.uuid == org_id) | (Tenant.name == org_id)).first()
        if not tenant:
            flash('Organization not found. Check your Organization ID.', 'danger')
            return render_template('login.html'), 404

        user = User.query.filter_by(username=username, tenant_id=tenant.id).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('main.dashboard'))

        flash('Invalid username or password for the specified organization.', 'danger')
        return render_template('login.html'), 401
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Public self-service onboarding for new tenant organizations."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'GET':
        return render_template('register.html')

    tenant_name = request.form.get('tenant_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not tenant_name or not username or not password or not confirm_password:
        flash('All fields are required.', 'danger')
        return render_template('register.html'), 400

    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return render_template('register.html'), 400

    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return render_template('register.html'), 400

    if len(username) < 3:
        flash('Username must be at least 3 characters.', 'danger')
        return render_template('register.html'), 400

    if Tenant.query.filter_by(name=tenant_name).first():
        flash('Organization name already exists. Please choose another one.', 'danger')
        return render_template('register.html'), 409

    if User.query.filter_by(username=username).first():
        flash('Username already exists. Please choose another one.', 'danger')
        return render_template('register.html'), 409

    # Attempt registration with retry for DB locks
    registered = False
    for attempt in range(3):
        try:
            # Create tenant
            tenant = Tenant(name=tenant_name)
            db.session.add(tenant)
            db.session.flush()  # Get tenant.id without committing

            # Create admin user for this tenant
            user = User(
                username=username,
                password=generate_password_hash(password),
                tenant_id=tenant.id,
                is_superadmin=False,
                role='tenant_admin'
            )
            db.session.add(user)

            # Auto-provision an agent key
            key = AgentKey(
                tenant_id=tenant.id,
                key_name=f'{tenant_name} Default Key',
                description='Auto-provisioned during onboarding'
            )
            db.session.add(key)

            # Commit everything atomically
            db.session.commit()
            registered = True
            logger.info(f"New organization registered: '{tenant_name}' (tenant_id={tenant.id}) by user '{username}'")
            break

        except IntegrityError:
            db.session.rollback()
            flash('Registration failed due to duplicate data. Please try different values.', 'danger')
            return render_template('register.html'), 409

        except OperationalError as exc:
            db.session.rollback()
            if 'database is locked' in str(exc).lower() and attempt < 2:
                time.sleep(0.2 * (attempt + 1))
                continue
            flash('Registration failed due to temporary database lock. Please retry.', 'danger')
            return render_template('register.html'), 503

        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {e}")
            flash('Registration failed due to a server error. Please try again.', 'danger')
            return render_template('register.html'), 500

    if not registered:
        flash('Registration failed after multiple attempts. Please try again.', 'danger')
        return render_template('register.html'), 503

    # Auto-login the new user and redirect to their dashboard
    new_user = User.query.filter_by(username=username).first()
    if new_user:
        # Show the organization identifier (UUID) to the admin so they can distribute it to team members
        org_id = tenant.uuid if getattr(tenant, 'uuid', None) else str(tenant.id)
        login_user(new_user)
        flash(f'Welcome! Your organization "{tenant_name}" has been created successfully. Organization ID: {org_id} — please save this and share with your users.', 'success')
        return redirect(url_for('tenants.tenant_settings'))

    # Fallback: redirect to login if auto-login fails
    flash('Registration successful. You can now sign in.', 'success')
    return redirect(url_for('auth.login'))
