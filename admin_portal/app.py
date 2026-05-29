"""
Admin Portal: Multi-Tenant Management UI
Modular Flask application with blueprint-based architecture

Structure:
- models: Database layer (SQLAlchemy models)
- routes: URL routing layer (Flask blueprints)  
- utils: Shared utilities and decorators
- services: Business logic (optional, planned for Phase 5)
"""

import logging
import os
import sys
import sqlite3
import re
from typing import Optional
from urllib.parse import unquote

# Addclearent directory to Python path so admin_portal can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, g, request
from flask_login import LoginManager
from sqlalchemy import select, func

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')


class TenantPathPrefixMiddleware:
    """Support path-based tenant routing: /t/<tenant_slug>/..."""
    _tenant_path_re = re.compile(r"^/t/([^/]+)(/.*)?$")

    def __init__(self, wrapped_app):
        self.wrapped_app = wrapped_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or ""
        match = self._tenant_path_re.match(path)
        if match:
            environ["sm.tenant_slug"] = unquote(match.group(1))
            rest = match.group(2) or "/"
            environ["PATH_INFO"] = rest if rest.startswith("/") else f"/{rest}"
        return self.wrapped_app(environ, start_response)


def _slugify_tenant(value):
    """Normalize tenant name/slug for path routing comparisons."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower())
    return slug.strip("-")

# Configure database
db_url = os.environ.get('DATABASE_URL')
if db_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'admin_portal.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Enable /t/<tenant>/... path routing before Flask endpoint matching.
app.wsgi_app = TenantPathPrefixMiddleware(app.wsgi_app)

# Import database
from admin_portal.models import db, User, Tenant

# Initialize database with app
db.init_app(app)


def _resolve_tenant_by_identifier(identifier: Optional[str]) -> Optional[Tenant]:
    """
    Resolve tenant by:
    1) numeric id
    2) exact name (case-insensitive)
    3) slugified name match
    """
    raw = (identifier or "").strip()
    if not raw:
        return None

    if raw.isdigit():
        tenant = db.session.get(Tenant, int(raw))
        if tenant:
            return tenant

    # Use SQLAlchemy 2.0 select() API for better type safety
    stmt = select(Tenant).where(func.lower(Tenant.name) == raw.lower())
    tenant = db.session.execute(stmt).scalar_one_or_none()
    if tenant:
        return tenant

    wanted_slug = _slugify_tenant(raw)
    if not wanted_slug:
        return None

    for tenant_obj in Tenant.query.all():
        if _slugify_tenant(tenant_obj.name) == wanted_slug:
            return tenant_obj
    return None


def _extract_subdomain_tenant_slug():
    """
    Optional subdomain routing support.
    Set TENANT_BASE_DOMAIN to enable (example: yourapp.com).
    """
    base_domain = (os.environ.get("TENANT_BASE_DOMAIN") or "").strip().lower()
    if not base_domain:
        return None

    host = (request.host or "").split(":", 1)[0].lower()
    if host == base_domain or not host.endswith(f".{base_domain}"):
        return None

    subdomain = host[:-(len(base_domain) + 1)].strip(".")
    if not subdomain or subdomain in {"www", "app"}:
        return None
    return subdomain

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # type: ignore


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    return db.session.get(User, int(user_id))


@app.before_request
def _resolve_request_tenant_context():
    """
    Resolve tenant for each request and inject into flask.g.
    Priority:
    1) X-Tenant-ID / X-Tenant-Slug header
    2) /t/<tenant_slug>/... path segment (via WSGI middleware)
    3) subdomain when TENANT_BASE_DOMAIN is configured
    """
    g.request_tenant = None
    g.request_tenant_id = None
    g.request_tenant_slug = None
    g.request_tenant_source = None

    # Skip static assets
    if request.path.startswith("/static/"):
        return None

    header_value = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Slug")
    path_slug = request.environ.get("sm.tenant_slug")
    subdomain_slug = _extract_subdomain_tenant_slug()

    tenant = None
    source = None
    for candidate, candidate_source in (
        (header_value, "header"),
        (path_slug, "path"),
        (subdomain_slug, "subdomain"),
    ):
        if not candidate:
            continue
        tenant = _resolve_tenant_by_identifier(candidate)
        if tenant:
            source = candidate_source
            break

    if tenant:
        g.request_tenant = tenant
        g.request_tenant_id = tenant.id
        g.request_tenant_slug = _slugify_tenant(tenant.name)
        g.request_tenant_source = source


@app.context_processor
def _inject_request_tenant():
    """Expose resolved tenant context and branding to templates."""
    tenant = getattr(g, "request_tenant", None)
    
    # Default branding for unauthenticated/no-tenant contexts (e.g., login page)
    default_branding = {
        "company_name": "ServerMonitor",
        "logo_url": None,
        "primary_color": "#2563eb",
        "secondary_color": "#1e40af",
        "accent_color": "#dc2626",
        "favicon_url": None
    }
    
    branding = default_branding
    if tenant:
        branding = tenant.get_branding()
    
    return {
        "request_tenant": tenant,
        "request_tenant_id": getattr(g, "request_tenant_id", None),
        "request_tenant_slug": getattr(g, "request_tenant_slug", None),
        "branding": branding,
    }


# Register all blueprint routes
from admin_portal.routes import (
    auth_bp, users_bp, tenants_bp, agents_bp, systems_bp,
    discovery_bp, deployment_bp, api_bp, main_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(tenants_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(systems_bp)
app.register_blueprint(discovery_bp)
app.register_blueprint(deployment_bp)
app.register_blueprint(api_bp)
app.register_blueprint(main_bp)


def init_central_db():
    """Initialize central agent database (separate from admin portal)"""
    central_db_path = os.path.join('data', 'central_agents.db')
    os.makedirs(os.path.dirname(central_db_path), exist_ok=True)
    
    try:
        conn = sqlite3.connect(central_db_path)
        cursor = conn.cursor()
        
        # Create central agents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS central_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT UNIQUE NOT NULL,
                tenant_id INTEGER NOT NULL,
                ip TEXT,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'offline'
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✓ Central agents database initialized")
    except Exception as e:
        logging.error(f"Failed to initialize central database: {e}")


def ensure_tenant_columns(db_path: str):
    """Ensure tenant table has azure columns; add them if missing.

    This performs safe ALTER TABLE ADD COLUMN operations for sqlite. It's idempotent
    and helps avoid OperationalError on deployments where models changed.
    """
    try:
        if not os.path.exists(db_path):
            logging.info(f"DB file {db_path} does not exist yet; skipping tenant migration")
            return

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('tenant')")
        existing = [r[1] for r in cur.fetchall()]
        logging.debug(f"Tenant table columns: {existing}")

        to_add = []
        if 'azure_client_id' not in existing:
            to_add.append(("azure_client_id", "TEXT"))
        if 'azure_client_secret' not in existing:
            to_add.append(("azure_client_secret", "TEXT"))
        if 'azure_tenant_id' not in existing:
            to_add.append(("azure_tenant_id", "TEXT"))
        if 'azure_display_name' not in existing:
            to_add.append(("azure_display_name", "TEXT"))
        if 'azure_registered' not in existing:
            to_add.append(("azure_registered", "INTEGER DEFAULT 0"))

        for name, typ in to_add:
            sql = f"ALTER TABLE tenant ADD COLUMN {name} {typ};"
            logging.info(f"Executing migration SQL: {sql}")
            cur.execute(sql)

        if to_add:
            conn.commit()
            logging.info("Tenant migration applied")
        conn.close()
    except Exception as e:
        logging.error(f"Failed to ensure tenant columns: {e}")


def ensure_user_columns(db_path: str):
    """Ensure user table has role column and backfill role values."""
    try:
        if not os.path.exists(db_path):
            logging.info(f"DB file {db_path} does not exist yet; skipping user migration")
            return

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('user')")
        existing = [r[1] for r in cur.fetchall()]

        if 'role' not in existing:
            cur.execute("ALTER TABLE user ADD COLUMN role TEXT DEFAULT 'user';")
            logging.info("Added missing column user.role")

        cur.execute(
            "UPDATE user SET role = 'super_admin' "
            "WHERE is_superadmin = 1 AND (role IS NULL OR role = '' OR role = 'user')"
        )
        cur.execute(
            "UPDATE user SET role = 'tenant_admin' "
            "WHERE is_superadmin = 0 AND (role IS NULL OR role = '')"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to ensure user columns: {e}")


def ensure_initial_setup():
    """Initialize portal database and default records."""
    with app.app_context():
        # Ensure tenant table columns exist for Azure integration before creating tables
        ensure_tenant_columns(DB_PATH)

        # Create all database tables
        db.create_all()
        ensure_user_columns(DB_PATH)
        
        # Auto-create default admin user if no users exist
        if not User.query.first():
            logging.info("Creating default admin user...")
            try:
                from werkzeug.security import generate_password_hash
                from admin_portal.models import Tenant
                
                # Create default tenant
                default_tenant = Tenant(name='Default Tenant')
                db.session.add(default_tenant)
                db.session.commit()
                logging.info(f"✓ Created default tenant (ID: {default_tenant.id})")
                
                # Create admin user
                admin = User(
                    username='admin',
                    password=generate_password_hash('admin'),
                    tenant_id=default_tenant.id,
                    is_superadmin=True,
                    role='super_admin'
                )
                db.session.add(admin)
                db.session.commit()
                logging.info("✓ Created default admin user (username: admin, password: admin)")
                logging.warning("⚠️  IMPORTANT: Change the default password immediately!")
            except Exception as e:
                logging.error(f"Failed to create default admin: {e}")
                db.session.rollback()


# Run setup on import as well (WSGI/waitress entrypoints do not execute __main__)
ensure_initial_setup()


if __name__ == '__main__':
    # Initialize central agent database
    init_central_db()
    
    # Start Flask development server
    app.run(host='0.0.0.0', port=5001)
