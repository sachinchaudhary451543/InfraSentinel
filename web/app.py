"""
Unified ServerMonitor App
Combines Intune-like Administration and Performance Metrics Monitoring.
"""

import logging
import os
import sys
import re
import shutil
import threading
import atexit
import socket
import signal
import platform
from datetime import datetime
from urllib.parse import unquote

# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key.strip(), value.strip())
            logging.info(f"Loaded environment variables from {env_path}")
        except Exception as e:
            logging.warning(f"Could not load .env file: {e}")

load_env_file()

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, redirect, url_for, session, g, request
from flask_login import LoginManager
from flask_socketio import SocketIO
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ─────────────────────────────────────────────────────────────────────────────
# BUFFERED LOGGING (Ported from main.py)
# ─────────────────────────────────────────────────────────────────────────────
_log_buffer = []
_log_buffer_size = 10
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(ROOT_DIR, "logs", "ServerMonitor.log")

def log(msg):
    global _log_buffer
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        safe_line = line.encode("ascii", errors="replace").decode("ascii")
        print(safe_line)
    _log_buffer.append(line + "\n")
    if len(_log_buffer) >= _log_buffer_size:
        _flush_log_buffer()

def _flush_log_buffer():
    global _log_buffer
    if not _log_buffer:
        return
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.writelines(_log_buffer)
        _log_buffer = []
    except Exception as e:
        print(f"Log flush error: {e}")

atexit.register(_flush_log_buffer)

def backup_config():
    config_path = os.path.join(ROOT_DIR, "config.json")
    if os.path.exists(config_path):
        backup_path = config_path + ".bak"
        shutil.copy2(config_path, backup_path)
        log(f"Config backed up to {backup_path}")

def run_platform_startup():
    """Merged startup sequence from main.py"""
    backup_config()
    log("=" * 62)
    log("  ServerMonitor v3.0 – Integrated Platform")
    log("=" * 62)

    # 1. Load secure config & OAuth
    log("Step 1/4 – Authenticating...")
    try:
        from auth.msal_auth import decrypt_config, encrypt_config, get_valid_token
        config = decrypt_config() or {}
        
        client_secret = config.get("sharepoint_credentials", {}).get("client_secret")
        tenant_id = config.get("sharepoint_credentials", {}).get("tenant_id") or config.get("tenant_id")
        
        token_data = get_valid_token(client_secret=client_secret, tenant_id=tenant_id)
        config["access_token"] = token_data["access_token"]
        if token_data["tenant_id"] != "unknown":
            config["tenant_id"] = token_data["tenant_id"]
        
        encrypt_config(config)
        log(f"✅ Authenticated. Tenant: {config.get('tenant_id')}")
    except Exception as e:
        log(f"⚠️ Authentication warning: {e}")

    # 2. Server Registration logs
    log("Step 2/4 – Server registration...")
    try:
        hostname = socket.gethostname()
        try: ip = socket.gethostbyname(hostname)
        except: ip = "Unknown"
        log(f"  Host: {hostname} | IP: {ip} | OS: {platform.platform()}")
    except Exception as e:
        log(f"Registration info failed: {e}")

    # 3. Domain Discovery (background)
    log("Step 3/4 – Domain Discovery sync...")
    try:
        from core.domain_discovery import DomainDiscoveryEngine
        discovery = DomainDiscoveryEngine()
        def _run_discovery():
            try:
                discovery.run_discovery()
                log("✅ Domain Discovery completed (synced to database)")
            except Exception as e:
                log(f"⚠️ Domain Discovery error: {e}")
        threading.Thread(target=_run_discovery, daemon=True, name="DomainDiscovery").start()
        log("✅ Domain Discovery running in background.")
    except Exception as e:
        log(f"⚠️ Domain Discovery failed: {e}")

    # 4. Initialize Scheduler
    log("Step 4/4 – Starting background jobs...")
    try:
        from web.jobs import init_scheduler
        init_scheduler(app)
        log("✅ Background job scheduler started.")
    except Exception as e:
        log(f"⚠️ Scheduler init warning: {e}")

# Initialize Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
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

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Enable /t/<tenant>/... path routing before Flask endpoint matching.
app.wsgi_app = TenantPathPrefixMiddleware(app.wsgi_app)

# Enable HTTP response compression to reduce payload sizes (gzip/brotli)
try:
    from flask_compress import Compress
    Compress(app)
    logging.info('Flask-Compress enabled')
except Exception:
    logging.info('Flask-Compress not installed; skipping compression')

# Basic request timing middleware to help identify slow endpoints
SLOW_REQUEST_THRESHOLD_MS = int(os.environ.get('SLOW_REQUEST_THRESHOLD_MS', '500'))


@app.before_request
def _start_timer():
    g._start_time = getattr(g, '_start_time', None) or __import__('time').time()


@app.after_request
def _log_request_time(response):
    try:
        start = getattr(g, '_start_time', None)
        if start:
            duration = (__import__('time').time() - start) * 1000.0
            msg = f"{request.method} {request.path} completed in {duration:.1f}ms"
            if duration >= SLOW_REQUEST_THRESHOLD_MS:
                app.logger.warning("SLOW_REQUEST: %s", msg)
                try:
                    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs'), exist_ok=True)
                    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'slow_requests.log'), 'a', encoding='utf-8') as f:
                        f.write(f"{__import__('time').ctime()} - {msg}\n")
                except Exception:
                    pass
            else:
                app.logger.debug(msg)
    except Exception:
        pass
    # Set long cache headers for static assets to improve client performance
    try:
        if request.path.startswith('/static/'):
            # If the response already has Cache-Control, don't override
            if not response.headers.get('Cache-Control'):
                # For versioned assets, encourage long caching
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    except Exception:
        pass
    return response

# Central Database path
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'central.db')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Import database and models
from web.models import db, User, Tenant

# Initialize database with app
db.init_app(app)


def _resolve_tenant_by_identifier(identifier):
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

    tenant = Tenant.query.filter(db.func.lower(Tenant.name) == raw.lower()).first()
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


def _get_default_branding():
    """Get default branding when no tenant is resolved"""
    return {
        "company_name": "ServerMonitor",
        "logo_url": None,
        "primary_color": "#2563eb",
        "secondary_color": "#1e40af",
        "accent_color": "#dc2626",
        "favicon_url": None
    }

@app.context_processor
def _inject_request_tenant():
    """Expose resolved tenant context and branding to templates."""
    branding = _get_default_branding()
    if getattr(g, "request_tenant", None):
        branding = g.request_tenant.get_branding()
    
    return {
        "request_tenant": getattr(g, "request_tenant", None),
        "request_tenant_id": getattr(g, "request_tenant_id", None),
        "request_tenant_slug": getattr(g, "request_tenant_slug", None),
        "branding": branding,
    }

from flask_socketio import join_room
from flask_login import current_user

@socketio.on('join')
def on_join(data):
    """Authenticated user joins their tenant room"""
    if current_user.is_authenticated:
        room = str(current_user.tenant_id)
        join_room(room)
        logging.info(f"User {current_user.username} joined room {room}")

# Register blueprints
from web.routes import (
    auth_bp, users_bp, tenants_bp, agents_bp,
    discovery_bp, deployment_bp, api_bp, main_bp
)
from web.routes.admin import admin_bp
from web.smart_analyzer import smart_analyzer
from web.routes.sharepoint import sharepoint_bp
from web.routes.auth_entra import auth_entra_bp
from web.routes.asset_management import asset_mgmt_bp
from web.routes.active_agents_api import active_agents_bp
from web.routes.api_improvements import api_imp_bp
from web.routes.system_control import sys_control_bp

app.register_blueprint(auth_bp)
app.register_blueprint(auth_entra_bp)  # registers at /auth/entra/*
app.register_blueprint(users_bp)
app.register_blueprint(tenants_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(asset_mgmt_bp)  # registers at /assets/* (employee assets & remote control)
app.register_blueprint(discovery_bp)
app.register_blueprint(deployment_bp, url_prefix='/deployment')
app.register_blueprint(api_bp)
app.register_blueprint(api_imp_bp)  # Enhanced APIs for productivity, domain discovery, and app tracking
app.register_blueprint(sys_control_bp)  # System control - command execution, software management, agent deployment
app.register_blueprint(active_agents_bp)  # Active agents monitoring API
app.register_blueprint(main_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(smart_analyzer, url_prefix='/smart-analyzer')
app.register_blueprint(sharepoint_bp)

from web.routes.agent_portal import agent_portal_bp
app.register_blueprint(agent_portal_bp)


from flask import send_from_directory

@app.route("/")
def index():
    if "_user_id" in session or "user_id" in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon_io'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


def ensure_initial_setup():
    with app.app_context():
        db.create_all()
        # Ensure new Tenant columns exist for migrations on older databases
        conn = None
        try:
            conn = db.engine.connect()
            res = conn.execute(text("PRAGMA table_info('tenant')"))
            existing_cols = {r[1] for r in res.fetchall()}
            # Add sharepoint_site_url if missing
            if 'sharepoint_site_url' not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE tenant ADD COLUMN sharepoint_site_url VARCHAR(500)"))
                    logging.info('Added missing column tenant.sharepoint_site_url')
                except Exception:
                    logging.exception('Failed to add tenant.sharepoint_site_url')
            # Add sharepoint_connected if missing
            if 'sharepoint_connected' not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE tenant ADD COLUMN sharepoint_connected INTEGER DEFAULT 0"))
                    logging.info('Added missing column tenant.sharepoint_connected')
                except Exception:
                    logging.exception('Failed to add tenant.sharepoint_connected')
            
            if 'sharepoint_auto_sync' not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE tenant ADD COLUMN sharepoint_auto_sync INTEGER DEFAULT 0"))
                except Exception:
                    pass
                    
            if 'sharepoint_sync_interval_minutes' not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE tenant ADD COLUMN sharepoint_sync_interval_minutes INTEGER DEFAULT 60"))
                except Exception:
                    pass
            
            if 'last_sharepoint_sync_timestamp' not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE tenant ADD COLUMN last_sharepoint_sync_timestamp DATETIME"))
                except Exception:
                    pass
                    
            # Ensure azure_user.employee_id exists if table present
            try:
                res2 = conn.execute(text("PRAGMA table_info('azure_user')"))
                cols2 = {r[1] for r in res2.fetchall()}
                if 'employee_id' not in cols2:
                    try:
                        conn.execute(text("ALTER TABLE azure_user ADD COLUMN employee_id VARCHAR(255)"))
                        logging.info('Added missing column azure_user.employee_id')
                    except Exception:
                        logging.exception('Failed to add azure_user.employee_id')
            except Exception:
                # table may not exist yet; ignore
                pass

            # Ensure server table columns for Hyper-V classification
            try:
                res3 = conn.execute(text("PRAGMA table_info('server')"))
                cols3 = {r[1] for r in res3.fetchall()}
                if 'is_hyperv_host' not in cols3:
                    try:
                        conn.execute(text("ALTER TABLE server ADD COLUMN is_hyperv_host INTEGER DEFAULT 0"))
                        logging.info('Added missing column server.is_hyperv_host')
                    except Exception:
                        logging.exception('Failed to add server.is_hyperv_host')
                if 'server_type' not in cols3:
                    try:
                        conn.execute(text("ALTER TABLE server ADD COLUMN server_type VARCHAR(50) DEFAULT 'Endpoint'"))
                        logging.info('Added missing column server.server_type')
                    except Exception:
                        logging.exception('Failed to add server.server_type')
            except Exception:
                pass

            # Ensure user.role exists for role-based onboarding
            try:
                res4 = conn.execute(text("PRAGMA table_info('user')"))
                cols4 = {r[1] for r in res4.fetchall()}
                if 'role' not in cols4:
                    try:
                        conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(50) DEFAULT 'user'"))
                        logging.info('Added missing column user.role')
                    except Exception:
                        logging.exception('Failed to add user.role')
                try:
                    conn.execute(
                        text("UPDATE user SET role = 'super_admin' WHERE is_superadmin = 1 AND (role IS NULL OR role = '' OR role = 'user')")
                    )
                    conn.execute(
                        text("UPDATE user SET role = 'tenant_admin' WHERE is_superadmin = 0 AND (role IS NULL OR role = '')")
                    )
                except Exception:
                    logging.exception('Failed backfilling user.role values')
            except Exception:
                pass

            # ── Agent-Based Monitoring Architecture columns ──
            try:
                res5 = conn.execute(text("PRAGMA table_info('server')"))
                cols5 = {r[1] for r in res5.fetchall()}
                agent_cols = {
                    'name': "VARCHAR(100) DEFAULT 'Unknown'",
                    'type': "VARCHAR(20) DEFAULT 'agent'",
                    'api_key': "VARCHAR(64)",
                    'last_seen': "DATETIME",
                    'source': "VARCHAR(20) DEFAULT 'agent'",
                    'agent_installed': "INTEGER DEFAULT 0",
                    'agent_version': "VARCHAR(50)",
                    'monitoring_mode': "VARCHAR(20) DEFAULT 'full'",
                    'azure_device_id': "VARCHAR(255)",
                    'status': "VARCHAR(20) DEFAULT 'offline'",
                }
                for col_name, col_def in agent_cols.items():
                    if col_name not in cols5:
                        try:
                            conn.execute(text(f"ALTER TABLE server ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column server.{col_name}')
                        except Exception:
                            logging.exception(f'Failed to add server.{col_name}')
                
                # Metric table updates
                res_m = conn.execute(text("PRAGMA table_info('metric')"))
                cols_m = {r[1] for r in res_m.fetchall()}
                metric_cols = {
                    'cpu': 'FLOAT', 'ram': 'FLOAT', 'disk': 'FLOAT',
                    'cpu_util_percent': 'FLOAT', 'ram_util_percent': 'FLOAT',
                    'ssd_util_percent': 'FLOAT'
                }
                for col_name, col_def in metric_cols.items():
                    if col_name not in cols_m:
                        try:
                            conn.execute(text(f"ALTER TABLE metric ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column metric.{col_name}')
                        except Exception:
                            pass
                
                # VM table updates
                res_v = conn.execute(text("PRAGMA table_info('vm')"))
                cols_v = {r[1] for r in res_v.fetchall()}
                vm_cols = {'cpu': 'FLOAT', 'ram': 'FLOAT', 'name': 'VARCHAR(100)', 'state': 'VARCHAR(50)'}
                for col_name, col_def in vm_cols.items():
                    if col_name not in cols_v:
                        conn.execute(text(f"ALTER TABLE vm ADD COLUMN {col_name} {col_def}"))
                        logging.info(f'Added missing column vm.{col_name}')
                
                # Backfill vm.name from vm_name if it existed
                try:
                    if 'vm_name' in cols_v and 'name' in cols_v:
                        conn.execute(text("UPDATE vm SET name = vm_name WHERE name IS NULL AND vm_name IS NOT NULL"))
                except Exception:
                    pass
                        
                # Backfill: synchronize old columns with new columns
                try:
                    conn.execute(text(
                        "UPDATE server SET "
                        "name = coalesce(hostname, 'Unknown') WHERE name = 'Unknown' OR name IS NULL"
                    ))
                    conn.execute(text(
                        "UPDATE server SET "
                        "type = coalesce(source, 'agent') WHERE type = 'agent'"
                    ))
                    conn.execute(text(
                        "UPDATE server SET "
                        "last_seen = last_heartbeat WHERE last_seen IS NULL AND last_heartbeat IS NOT NULL"
                    ))
                    conn.execute(text(
                        "UPDATE server SET agent_installed = 1, type = 'agent' "
                        "WHERE last_seen IS NOT NULL AND (agent_installed IS NULL OR agent_installed = 0)"
                    ))
                    logging.info('Backfilled legacy data to new columns')
                except Exception:
                    logging.exception('Failed backfilling server legacy columns')
            except Exception:
                pass

            # ── Screenshot configuration columns ──
            try:
                res6 = conn.execute(text("PRAGMA table_info('server')"))
                cols6 = {r[1] for r in res6.fetchall()}
                screenshot_cols = {
                    'screenshot_enabled': "INTEGER DEFAULT 0",
                    'screenshot_interval_minutes': "INTEGER DEFAULT 10",
                }
                for col_name, col_def in screenshot_cols.items():
                    if col_name not in cols6:
                        try:
                            conn.execute(text(f"ALTER TABLE server ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column server.{col_name}')
                        except Exception:
                            logging.exception(f'Failed to add server.{col_name}')
            except Exception:
                pass

            # ── Screenshot table columns ──
            try:
                res_ss = conn.execute(text("PRAGMA table_info('screenshot')"))
                cols_ss = {r[1] for r in res_ss.fetchall()}
                ss_extra_cols = {
                    'local_file_path': "VARCHAR(500)",
                }
                for col_name, col_def in ss_extra_cols.items():
                    if col_name not in cols_ss:
                        try:
                            conn.execute(text(f"ALTER TABLE screenshot ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column screenshot.{col_name}')
                        except Exception:
                            logging.exception(f'Failed to add screenshot.{col_name}')
            except Exception:
                pass  # table may not exist yet

            # ── Custom Identification columns (Serial & Address) ──
            try:
                res7 = conn.execute(text("PRAGMA table_info('server')"))
                cols7 = {r[1] for r in res7.fetchall()}
                id_cols = {
                    'serial_number': "VARCHAR(100)",
                    'address': "VARCHAR(255)",
                }
                for col_name, col_def in id_cols.items():
                    if col_name not in cols7:
                        try:
                            conn.execute(text(f"ALTER TABLE server ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column server.{col_name}')
                        except Exception:
                            logging.exception(f'Failed to add server.{col_name}')
            except Exception:
                pass

            # ── Remote Command table columns ──
            try:
                res_rc = conn.execute(text("PRAGMA table_info('remote_command')"))
                cols_rc = {r[1] for r in res_rc.fetchall()}
                rc_cols = {
                    'completed_at': "DATETIME",
                    'output': "TEXT",
                    'error_output': "TEXT",
                    'exit_code': "INTEGER",
                    'timeout_seconds': "INTEGER DEFAULT 120",
                    'created_by': "VARCHAR(150)",
                }
                for col_name, col_def in rc_cols.items():
                    if col_name not in cols_rc:
                        try:
                            conn.execute(text(f"ALTER TABLE remote_command ADD COLUMN {col_name} {col_def}"))
                            logging.info(f'Added missing column remote_command.{col_name}')
                        except Exception:
                            logging.exception(f'Failed to add remote_command.{col_name}')
            except Exception:
                pass  # table may not exist yet

            # Commit all DDL changes (required in SQLAlchemy 2.0+)
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_metric_server_timestamp ON metric(server_id, timestamp DESC)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_employee_asset_tenant_email_host ON employee_asset_log(tenant_id, employee_email, hostname)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_azure_device_owner_tenant_user ON azure_device_owner(tenant_id, user_id)"))
                logging.info('Ensured performance indexes for metrics/assets queries')
            except Exception:
                logging.exception('Failed creating performance indexes')

            # Commit all DDL changes (required in SQLAlchemy 2.0+)
            conn.commit()
            
        except Exception:
            logging.exception('Error ensuring database columns')
        finally:
            if conn is not None:
                conn.close()
        # Initialize default tenant if it doesn't exist
        default_tenant = Tenant.query.filter_by(name='Default Tenant').first()
        if not default_tenant:
            default_tenant = Tenant()
            default_tenant.name = 'Default Tenant'
            db.session.add(default_tenant)
            db.session.commit()

        # Initialize default admin if no users exist
        if not User.query.filter_by(username='admin').first():
            from werkzeug.security import generate_password_hash
            admin_user = User()
            admin_user.username = 'admin'
            admin_user.password = generate_password_hash('admin')
            admin_user.tenant_id = default_tenant.id
            admin_user.is_superadmin = True
            admin_user.role = 'super_admin'
            db.session.add(admin_user)
            db.session.commit()
            logging.info("Created default admin user (admin/admin)")


# Run setup on import as well (WSGI/waitress entrypoints do not execute __main__)
ensure_initial_setup()

# Apply database optimizations (indexes, analysis)
try:
    from web.db_optimizations import create_critical_indexes, analyze_database
    with app.app_context():
        create_critical_indexes(db)
        analyze_database(db)
except Exception as e:
    logging.warning(f"Database optimization warning: {e}")

# Configure socket reuse to prevent "address already in use" errors on restart
def configure_socket_reuse():
    """Configure gevent socket server to allow address reuse."""
    try:
        from gevent.server import StreamServer
        # Set the class-level attribute to True so gevent uses it during bind()
        StreamServer.reuse_addr = True
        log("✅ Socket reuse (SO_REUSEADDR) enabled on StreamServer class")
    except Exception as e:
        log(f"Warning: Could not configure socket reuse: {e}")

# Global flag for graceful shutdown
_shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    log(f"Shutdown signal ({signum}) received. Stopping server...")
    sys.exit(0)

if __name__ == '__main__':
    # Full platform startup sequence
    run_platform_startup()
    
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    # Configure socket reuse before starting server
    configure_socket_reuse()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log(f"Starting server on port {port} (debug={debug})")

    # Allow overriding bind host via environment variable (helpful on Windows where
    # binding to 0.0.0.0 can be blocked by security policies). Default remains 0.0.0.0
    bind_host = os.environ.get('BIND_HOST') or os.environ.get('HOST') or '0.0.0.0'

    try:
        from web.jobs import shutdown_scheduler
        socketio.run(
            app,
            host=bind_host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True
        )
    finally:
        shutdown_scheduler()
