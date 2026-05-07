"""
Authentication routes (login, logout)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import check_password_hash, generate_password_hash
import time

from admin_portal.models import User, Tenant, AgentKey, db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index_redirect'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('main.index_redirect'))
        flash('Invalid username or password', 'danger')
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
        return redirect(url_for('main.index_redirect'))

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

    if Tenant.query.filter_by(name=tenant_name).first():
        flash('Organization name already exists. Please choose another one.', 'danger')
        return render_template('register.html'), 409

    if User.query.filter_by(username=username).first():
        flash('Username already exists. Please choose another one.', 'danger')
        return render_template('register.html'), 409

    for attempt in range(3):
        try:
            tenant = Tenant(name=tenant_name)
            db.session.add(tenant)
            db.session.flush()

            user = User(
                username=username,
                password=generate_password_hash(password),
                tenant_id=tenant.id,
                is_superadmin=False,
                role='tenant_admin'
            )
            db.session.add(user)

            key = AgentKey(
                tenant_id=tenant.id,
                key_name=f'{tenant_name} Default Key',
                description='Auto-provisioned during onboarding'
            )
            db.session.add(key)
            db.session.commit()
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
        except Exception:
            db.session.rollback()
            flash('Registration failed due to a server error. Please try again.', 'danger')
            return render_template('register.html'), 500

    flash('Registration successful. You can now sign in.', 'success')
    return redirect(url_for('auth.login'))
