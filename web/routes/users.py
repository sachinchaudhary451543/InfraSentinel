"""
User management routes (add, edit, delete users)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from werkzeug.security import generate_password_hash

from web.models import User, Tenant, db
from web.utils import require_superadmin

users_bp = Blueprint('users', __name__)


@users_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
@require_superadmin
def add_user():
    """Add new user (superadmin only)."""
    tenants = Tenant.query.all()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        tenant_id = int(request.form['tenant_id'])

        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different username.', 'danger')
            return redirect(url_for('users.add_user'))

        if username and password and tenant_id:
            user = User(
                username=username,
                password=generate_password_hash(password),
                tenant_id=tenant_id,
                is_superadmin=False,
                role='tenant_admin'
            )
            db.session.add(user)
            db.session.commit()
            flash(f'User "{username}" created successfully', 'success')
            return redirect(url_for('main.dashboard'))

    return render_template('add_user.html', tenants=tenants)


@users_bp.route('/users', methods=['GET'])
@login_required
@require_superadmin
def list_users():
    """View/manage all users (superadmin only)."""
    user_list = User.query.all()
    return render_template('users.html', users=user_list)


@users_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@require_superadmin
def edit_user(user_id):
    """Edit user (superadmin only)."""
    user = db.get_or_404(User, user_id)
    tenants = Tenant.query.all()

    if request.method == 'POST':
        username = request.form['username']
        tenant_id = int(request.form['tenant_id'])
        is_superadmin = bool(request.form.get('is_superadmin'))

        if User.query.filter_by(username=username).filter(User.id != user_id).first():
            flash('Username already exists. Please choose a different username.', 'danger')
            return redirect(url_for('users.edit_user', user_id=user_id))

        user.username = username
        user.tenant_id = tenant_id
        user.is_superadmin = is_superadmin
        user.role = 'super_admin' if is_superadmin else 'tenant_admin'
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('users.list_users'))

    return render_template('edit_user.html', user=user, tenants=tenants)


@users_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@require_superadmin
def delete_user(user_id):
    """Delete user (superadmin only)."""
    user = db.get_or_404(User, user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully', 'success')
    return redirect(url_for('users.list_users'))
