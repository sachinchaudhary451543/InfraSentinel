"""
Admin Panel Routes - Super Admin Dashboard & Management
Provides /admin/dashboard, /admin/tenants, /admin/users, /admin/usage
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import re
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from web.models import db, Tenant, User, Server, AgentKey, Metric, SystemAlert, AuditLog
from web.utils import require_superadmin, validate_password

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/configuration', methods=['GET', 'POST'])
@login_required
def configuration_center():
    """Unified tenant administration, onboarding guidance, and live Entra verification."""
    is_platform_admin = current_user.is_superadmin or current_user.role == 'super_admin'
    if not is_platform_admin and current_user.role not in {'org_admin', 'tenant_admin'}:
        flash('You do not have permission to manage organization configuration.', 'danger')
        return redirect(url_for('main.dashboard'))

    available_tenants = Tenant.query.order_by(Tenant.name).all() if is_platform_admin else [current_user.tenant]
    available_tenants = [tenant for tenant in available_tenants if tenant]
    selected_id = request.values.get('tenant_id', type=int)
    selected = next((tenant for tenant in available_tenants if tenant.id == selected_id), None)
    selected = selected or (current_user.tenant if not is_platform_admin else (available_tenants[0] if available_tenants else None))
    verification = None

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_tenant' and is_platform_admin:
            name = request.form.get('tenant_name', '').strip()
            if not name:
                flash('Tenant name is required.', 'danger')
            elif Tenant.query.filter_by(name=name).first():
                flash('A tenant with this name already exists.', 'danger')
            else:
                selected = Tenant(name=name)
                db.session.add(selected)
                db.session.flush()
                db.session.add(AgentKey(tenant_id=selected.id, key_name=f'{name} Default Key', description='Created with tenant'))
                db.session.commit()
                flash(f'Tenant "{name}" created. Configure its Entra connection below.', 'success')
                return redirect(url_for('admin.configuration_center', tenant_id=selected.id))
        elif action == 'verify_entra' and selected:
            client_id = request.form.get('azure_client_id', '').strip()
            client_secret = request.form.get('azure_client_secret', '').strip() or (selected.azure_client_secret or '')
            directory_id = request.form.get('azure_tenant_id', '').strip()
            from core.azure_discovery import verify_graph_configuration
            verification = verify_graph_configuration(client_id, client_secret, directory_id)
            if verification['can_save']:
                selected.azure_client_id = client_id
                selected.azure_client_secret = client_secret
                selected.azure_tenant_id = directory_id
                selected.azure_display_name = verification['organization_name'] or directory_id
                selected.azure_registered = verification['ok']
                db.session.commit()
                flash('Entra configuration saved.' if verification['ok'] else 'Credentials saved, but integration remains unverified until all required Graph checks pass.', 'success' if verification['ok'] else 'warning')
            else:
                flash('Configuration was not saved because Microsoft Entra credentials could not be verified.', 'danger')
        elif action == 'save_operations' and selected:
            selected.polling_interval_minutes = request.form.get('polling_interval_minutes', type=int) or 60
            selected.sharepoint_site_url = request.form.get('sharepoint_site_url', '').strip() or None
            selected.sharepoint_auto_sync = request.form.get('sharepoint_auto_sync') == 'on'
            selected.sharepoint_sync_interval_minutes = request.form.get('sharepoint_sync_interval_minutes', type=int) or 60
            selected.sharepoint_connected = bool(selected.sharepoint_site_url)
            db.session.commit()
            flash('Operational settings saved.', 'success')
        return render_template('admin/configuration_center.html', tenant=selected, tenants=available_tenants,
                               is_platform_admin=is_platform_admin, verification=verification,
                               total_users=User.query.count() if is_platform_admin else User.query.filter_by(tenant_id=selected.id).count(),
                               total_servers=Server.query.count() if is_platform_admin else Server.query.filter_by(tenant_id=selected.id).count(),
                               active_alerts=SystemAlert.query.filter_by(is_active=True).count())

    return render_template('admin/configuration_center.html', tenant=selected, tenants=available_tenants,
                           is_platform_admin=is_platform_admin, verification=None,
                           total_users=User.query.count() if is_platform_admin else User.query.filter_by(tenant_id=selected.id).count(),
                           total_servers=Server.query.count() if is_platform_admin else Server.query.filter_by(tenant_id=selected.id).count(),
                           active_alerts=SystemAlert.query.filter_by(is_active=True).count())


@admin_bp.route('/dashboard')
@login_required
@require_superadmin
def admin_dashboard():
    """Super Admin overview dashboard"""
    return redirect(url_for('admin.configuration_center'))
    tenants = Tenant.query.all()
    total_users = User.query.count()
    total_servers = Server.query.count()
    total_keys = AgentKey.query.filter_by(is_active=True).count()
    active_alerts = SystemAlert.query.filter_by(is_active=True).count()

    online_servers = sum(1 for s in Server.query.all() if s.is_online)

    # Recent audit logs
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(20).all()

    # Per-tenant stats
    tenant_stats = []
    for t in tenants:
        server_count = Server.query.filter_by(tenant_id=t.id).count()
        user_count = User.query.filter_by(tenant_id=t.id).count()
        key_count = AgentKey.query.filter_by(tenant_id=t.id, is_active=True).count()
        tenant_stats.append({
            'tenant': t,
            'servers': server_count,
            'users': user_count,
            'keys': key_count
        })

    return render_template('admin/dashboard.html',
                           tenants=tenants, tenant_stats=tenant_stats,
                           total_users=total_users, total_servers=total_servers,
                           total_keys=total_keys, active_alerts=active_alerts,
                           online_servers=online_servers, recent_logs=recent_logs)


@admin_bp.route('/tenants')
@login_required
@require_superadmin
def admin_tenants():
    """Manage all tenants"""
    return redirect(url_for('admin.configuration_center'))
    tenants = Tenant.query.all()
    tenant_data = []
    
    for t in tenants:
        tenant_data.append({
            'tenant': t,
            'servers': Server.query.filter_by(tenant_id=t.id).count(),
            'users': User.query.filter_by(tenant_id=t.id).count(),
            'keys': AgentKey.query.filter_by(tenant_id=t.id, is_active=True).count(),
            'azure': t.azure_registered or False,
            'azure_org': None
        })
    return render_template('admin/tenants.html', tenant_data=tenant_data)


@admin_bp.route('/tenants/create', methods=['POST'])
@login_required
@require_superadmin
def admin_create_tenant():
    """Create a new tenant"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('Tenant name is required', 'danger')
        return redirect(url_for('admin.admin_tenants'))

    if Tenant.query.filter_by(name=name).first():
        flash('Tenant name already exists', 'danger')
        return redirect(url_for('admin.admin_tenants'))

    t = Tenant(name=name)
    db.session.add(t)
    db.session.commit()

    # Auto-generate an agent key for the new tenant
    key = AgentKey(tenant_id=t.id, key_name=f'{name} Default Key', description='Auto-generated on tenant creation')
    db.session.add(key)
    db.session.commit()

    flash(f'Tenant "{name}" created with agent key: {key.key[:16]}...', 'success')
    return redirect(url_for('admin.admin_tenants'))


@admin_bp.route('/tenants/<int:tenant_id>/delete', methods=['POST'])
@login_required
@require_superadmin
def admin_delete_tenant(tenant_id):
    """Delete a tenant and all related data"""
    t = db.session.get(Tenant, tenant_id)
    if not t:
        flash('Tenant not found', 'danger')
        return redirect(url_for('admin.admin_tenants'))

    # Delete related data
    AgentKey.query.filter_by(tenant_id=t.id).delete()
    User.query.filter_by(tenant_id=t.id).delete()
    servers = Server.query.filter_by(tenant_id=t.id).all()
    for s in servers:
        Metric.query.filter_by(server_id=s.id).delete()
    Server.query.filter_by(tenant_id=t.id).delete()
    db.session.delete(t)
    db.session.commit()

    flash(f'Tenant "{t.name}" and all related data deleted', 'success')
    return redirect(url_for('admin.admin_tenants'))


@admin_bp.route('/tenants/<int:tenant_id>/generate_key', methods=['POST'])
@login_required
@require_superadmin
def admin_generate_key(tenant_id):
    """Generate a new agent key for a tenant"""
    t = db.session.get(Tenant, tenant_id)
    if not t:
        flash('Tenant not found', 'danger')
        return redirect(url_for('admin.admin_tenants'))

    key_name = request.form.get('key_name', f'{t.name} Key')
    key = AgentKey(tenant_id=t.id, key_name=key_name, description='Generated by admin')
    db.session.add(key)
    db.session.commit()

    flash(f'New key generated: {key.key}', 'success')
    return redirect(url_for('admin.admin_tenants'))


@admin_bp.route('/users')
@login_required
@require_superadmin
def admin_users():
    """Manage all users across tenants"""
    users = User.query.order_by(User.username.asc()).all()
    tenants = Tenant.query.all()
    from web.models import Employee
    employees = Employee.query.all()
    return render_template('admin/users.html', users=users, tenants=tenants, employees=employees,
                           total_users=len(users), admin_count=sum(1 for user in users if user.is_superadmin or user.role in {'super_admin', 'tenant_admin'}),
                           mapped_count=sum(1 for user in users if user.employee_id))


@admin_bp.route('/users/create', methods=['POST'])
@login_required
@require_superadmin
def admin_create_user():
    """Create a new user"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    tenant_id = request.form.get('tenant_id', type=int)
    role = request.form.get('role', 'tenant_admin').strip()
    allowed_roles = {'tenant_admin', 'hr_admin', 'screen_monitor', 'manager', 'employee'}
    employee_id_raw = request.form.get('employee_id')
    employee_id = int(employee_id_raw) if employee_id_raw and employee_id_raw.isdigit() else None

    if not username or not password or not confirm_password:
        flash('Username, password, and password confirmation are required.', 'danger')
        return redirect(url_for('admin.admin_users'))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._@-]{2,99}', username):
        flash('Username must be 3–100 characters and may contain only letters, numbers, dot, underscore, @, or hyphen.', 'danger')
        return redirect(url_for('admin.admin_users'))
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        flash('Username already exists (usernames are case-insensitive).', 'danger')
        return redirect(url_for('admin.admin_users'))
    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('admin.admin_users'))
    password_error = validate_password(password, username)
    if password_error:
        flash(password_error, 'danger')
        return redirect(url_for('admin.admin_users'))
    if role not in allowed_roles:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('admin.admin_users'))
    tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
    if not tenant:
        flash('A valid tenant must be selected.', 'danger')
        return redirect(url_for('admin.admin_users'))
    if employee_id:
        from web.models import Employee
        employee = db.session.get(Employee, employee_id)
        if not employee or employee.tenant_id != tenant.id or not employee.is_active:
            flash('Selected employee is invalid, inactive, or belongs to a different tenant.', 'danger')
            return redirect(url_for('admin.admin_users'))

    user = User(
        username=username,
        password=generate_password_hash(password),
        tenant_id=tenant.id,
        is_superadmin=False,
        role=role,
        employee_id=employee_id
    )
    db.session.add(user)
    db.session.commit()
    flash(f'User "{username}" created with {role.replace("_", " ")} access.', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/users/<int:user_id>/password', methods=['POST'])
@login_required
@require_superadmin
def admin_reset_password(user_id):
    """Set a new password for a managed user; never generate or expose a password."""
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.admin_users'))
    if user.id == current_user.id:
        flash('Use Change Password to update your own password.', 'warning')
        return redirect(url_for('admin.admin_users'))
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    if new_password != confirm_password:
        flash('Reset passwords do not match.', 'danger')
    else:
        password_error = validate_password(new_password, user.username)
        if password_error:
            flash(password_error, 'danger')
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash(f'Password reset successfully for "{user.username}".', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@require_superadmin
def admin_delete_user(user_id):
    """Delete a user"""
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('admin.admin_users'))
    if user.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('admin.admin_users'))

    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" deleted', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/usage')
@login_required
@require_superadmin
def admin_usage():
    """View tenant usage statistics as JSON"""
    tenants = Tenant.query.all()
    data = []
    for t in tenants:
        server_count = Server.query.filter_by(tenant_id=t.id).count()
        metric_count = Metric.query.join(Server).filter(Server.tenant_id == t.id).count()
        data.append({
            'tenant_id': t.id,
            'tenant_name': t.name,
            'servers': server_count,
            'total_metrics': metric_count
        })
    return jsonify(data)
