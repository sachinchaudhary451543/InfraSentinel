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

try:
    from gevent import monkey
    monkey.patch_all()
except Exception:
    pass

from flask import Flask, redirect, url_for, session, g, request
from flask_login import LoginManager
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

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
app.config['DEBUG'] = False

# Load root config.json into app.config (optional server settings)
try:
    cfg_path = os.path.join(ROOT_DIR, 'config.json')
    if os.path.exists(cfg_path):
        import json as _json
        with open(cfg_path, 'r', encoding='utf-8') as _cf:
            _cfg = _json.load(_cf)
            # Normalize keys to upper-case environment-style names
            for _k, _v in _cfg.items():
                app.config.setdefault(_k.upper(), _v)
        logging.info('Loaded configuration from config.json into app.config')
except Exception as e:
    logging.warning(f'Could not load config.json into app.config: {e}')


def format_seconds(value):
    """Format seconds as HH:MM:SS for productivity labels."""
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_minutes(value):
    """Format minutes as HH:MM:SS for productivity labels (DeviceActivity model)."""
    try:
        minutes = float(value or 0)
    except (TypeError, ValueError):
        minutes = 0
    total_seconds = int(minutes * 60)
    hours = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


app.add_template_filter(format_seconds, name='format_seconds')
app.add_template_filter(format_minutes, name='format_minutes')


def safe_url_for(endpoint, **kwargs):
    """Safely build a URL for a possibly-missing endpoint.

    Returns '#' when the endpoint cannot be built to avoid Jinja BuildError
    when optional blueprints are not registered.
    """
    try:
        return url_for(endpoint, **kwargs)
    except Exception:
        return '#'


# Expose safe_url_for to Jinja templates so templates can use it when
# optional blueprints/endpoints may not be present in all deployments.
app.jinja_env.globals['safe_url_for'] = safe_url_for


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
# Production uses Gunicorn + Gevent (with Redis message queue if available), development uses Waitress.
# async_mode MUST be 'gevent' to match the GeventWebSocketWorker used in the Dockerfile.
# Gevent monkey patching is required for compatibility with RedisManager and websocket upgrades.
# Without it, Redis-backed Socket.IO will fail with runtime errors and connections may return 400/401.
redis_url = os.environ.get('REDIS_URL')
socketio_kwargs = {
    "cors_allowed_origins": "*",
    "async_mode": "gevent",       # CRITICAL: must match gunicorn+gevent worker type
    "logger": False,
    "engineio_logger": False,
    "allow_upgrades": True,
    "async_handlers": True,
    "ping_timeout": 60,
    "ping_interval": 25,
}
if redis_url:
    socketio_kwargs["message_queue"] = redis_url
    logging.info("Socket.IO initialized with Redis Message Queue adapter (gevent async_mode)")
else:
    logging.warning("Socket.IO running without Redis – WebSocket sessions are NOT shared across workers.")

socketio = SocketIO(
    app,
    **socketio_kwargs
)

# Enable /t/<tenant>/... path routing before Flask endpoint matching.
app.wsgi_app = TenantPathPrefixMiddleware(app.wsgi_app)

# Security hardening: Fix proxy headers for proper X-Forwarded-* handling
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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

# Support switching to Postgres in production via DATABASE_URL env var.
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# If using Postgres, tune engine options for production workloads
if DATABASE_URL.startswith('postgres') or DATABASE_URL.startswith('postgresql'):
    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    # sensible defaults; can be tuned via env vars
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
        'pool_size': int(os.environ.get('SQL_POOL_SIZE', '10')),
        'max_overflow': int(os.environ.get('SQL_MAX_OVERFLOW', '20')),
        'pool_pre_ping': True,
        'pool_recycle': int(os.environ.get('SQL_POOL_RECYCLE', '1800'))
    })
    logging.info('Configured SQLAlchemy for Postgres with engine options')
else:
    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    from sqlalchemy.pool import NullPool
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
        'connect_args': {
            'timeout': int(os.environ.get('SQLITE_BUSY_TIMEOUT_SECONDS', '120')),
            'check_same_thread': False,
        },
        'poolclass': NullPool,  # Prevent connection pooling issues with SQLite
        'pool_pre_ping': True,
    })
    logging.info('Using SQLite for development (DATABASE_URL not set to Postgres) - NullPool enabled for concurrent access')

# Import database and models
from web.models import db, User, Tenant

# Initialize database with app
db.init_app(app)

# Enable SQLite WAL mode for concurrent read/write access
if not (DATABASE_URL.startswith('postgres') or DATABASE_URL.startswith('postgresql')):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, 'connect')
    def _enable_sqlite_wal(dbapi_conn, connection_record):
        """Enable Write-Ahead Logging (WAL) mode for SQLite to allow concurrent reads during writes.

        Registered on the Engine class to avoid requiring an application context
        when importing db.engine during module import.
        """
        try:
            # Only apply PRAGMA to sqlite3 connections
            # dbapi_conn is a sqlite3.Connection for SQLite
            mod = getattr(dbapi_conn, '__class__', None)
            if mod is not None and 'sqlite' in str(mod).lower():
                # Some sqlite DB-API objects expose execute, others require cursor
                try:
                    dbapi_conn.execute('PRAGMA journal_mode=WAL')
                except Exception:
                    cur = dbapi_conn.cursor()
                    cur.execute('PRAGMA journal_mode=WAL')
                    cur.close()
                try:
                    dbapi_conn.execute('PRAGMA cache_size=-64000')
                except Exception:
                    cur = dbapi_conn.cursor()
                    cur.execute('PRAGMA cache_size=-64000')
                    cur.close()
                try:
                    dbapi_conn.execute('PRAGMA synchronous=NORMAL')
                except Exception:
                    cur = dbapi_conn.cursor()
                    cur.execute('PRAGMA synchronous=NORMAL')
                    cur.close()
                logging.info('SQLite WAL mode enabled for concurrent access')
        except Exception as e:
            logging.warning(f'Could not enable SQLite WAL mode: {e}')

from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith('sqlite'):
        cursor = dbapi_connection.cursor()
        # WAL mode allows readers and writers to coexist
        cursor.execute("PRAGMA journal_mode=WAL")
        # NORMAL is faster than FULL, still safe for our use case
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Match the connection timeout (120 seconds = 120000 ms)
        cursor.execute(f"PRAGMA busy_timeout={int(os.environ.get('SQLITE_BUSY_TIMEOUT_SECONDS', '120')) * 1000}")
        # Allow temp storage to overflow to disk for large operations
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

# Initialize Flask-Caching (Redis if configured, otherwise SimpleCache)
try:
    from flask_caching import Cache
    cache_config = {}
    if os.environ.get('REDIS_URL'):
        cache_config['CACHE_TYPE'] = 'RedisCache'
        cache_config['CACHE_REDIS_URL'] = os.environ.get('REDIS_URL')
    else:
        cache_config['CACHE_TYPE'] = os.environ.get('CACHE_TYPE', 'SimpleCache')
        cache_config['CACHE_DEFAULT_TIMEOUT'] = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', '60'))

    app.config.update(cache_config)
    cache = Cache(app)
    logging.info('Flask-Caching initialized')
except Exception:
    cache = None
    logging.info('Flask-Caching not available or failed to initialize; continuing without Redis cache')


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
    
    # Skip agent endpoints that don't require tenant resolution
    if request.path.startswith("/api/v2/agent/"):
        return None
    
    if request.path.startswith("/api/v2/agents/"):
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


@app.before_request
def _enforce_tenant_onboarding():
    """Redirect users to tenant settings onboarding until Azure/SharePoint are registered.

    Allows static assets, auth routes, logout and the tenant settings/manage_azure pages.
    """
    from flask_login import current_user

    # Skip static and agent API endpoints
    if request.path.startswith('/static/') or request.path.startswith('/api/v2/agent/') or request.path.startswith('/api/v2/agents/'):
        return None

    # If not logged in, nothing to enforce here
    if not getattr(current_user, 'is_authenticated', False):
        return None

    try:
        tenant = None
        if getattr(current_user, 'tenant_id', None):
            tenant = db.session.get(Tenant, int(current_user.tenant_id))

        # If tenant cannot be determined, allow access (other checks will handle it)
        if not tenant:
            return None

        # If tenant is active but Azure not registered yet, require setup before showing dashboards
        if not getattr(tenant, 'azure_registered', False):
            # Allowed endpoints while onboarding
            allowed = {
                'tenants.tenant_settings',
                'tenants.manage_tenant_azure',
                'auth.logout',
                'auth.login',
                'auth.register',
            }

            if request.endpoint not in allowed:
                return redirect(url_for('tenants.tenant_settings'))

    except Exception:
        # On unexpected errors, do not block the request flow
        return None


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
    discovery_bp, deployment_bp, api_bp, main_bp,
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

# Optional blueprints: import/register only if present to support trimmed deployments
try:
    from web.routes.analytics import analytics_bp
    app.register_blueprint(analytics_bp)
except Exception as e:
    logging.info(f"Optional blueprint 'analytics' not loaded: {e}")

try:
    from web.routes.analytics_api import analytics_api_bp
    app.register_blueprint(analytics_api_bp)
except Exception as e:
    logging.info(f"Optional blueprint 'analytics_api' not loaded: {e}")

try:
    from web.routes.license_management import license_bp
    app.register_blueprint(license_bp)
except Exception as e:
    logging.info(f"Optional blueprint 'license_management' not loaded: {e}")

try:
    from web.routes.status_management import status_mgmt_bp
    app.register_blueprint(status_mgmt_bp)
except Exception as e:
    logging.info(f"Optional blueprint 'status_management' not loaded: {e}")

from web.routes.agent_portal import agent_portal_bp
app.register_blueprint(agent_portal_bp)


from flask import send_from_directory
from flask import url_for

@app.route("/")
def index():
    if "_user_id" in session or "user_id" in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon_io'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/favicon.png')
def favicon_png():
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon_io'),
                               'favicon-32x32.png', mimetype='image/png')

@app.route('/health')
def health():
    """Health check endpoint for monitoring uptime."""
    return {"status": "ok"}, 200


def ensure_initial_setup():
    with app.app_context():
        db.create_all()

        # ── Safe dynamic database schema synchronization ───────────────
        try:
            from sqlalchemy import inspect
            engine = db.engine
            inspector = inspect(engine)
            is_postgres = engine.dialect.name == 'postgresql'
            logging.info(f"[DB-SYNC] Checking database schema (dialect={engine.dialect.name})...")
            
            for table_name, table in db.metadata.tables.items():
                if not inspector.has_table(table_name):
                    continue
                    
                existing_columns = {col['name'].lower() for col in inspector.get_columns(table_name)}
                for col in table.columns:
                    col_name = col.name
                    if col_name.lower() not in existing_columns:
                        sql_type = str(col.type.compile(dialect=engine.dialect))
                        if is_postgres:
                            if 'DATETIME' in sql_type.upper():
                                sql_type = 'TIMESTAMP'
                                
                        alter_query = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}"
                        logging.info(f"[DB-SYNC] Column '{col_name}' is missing in table '{table_name}'. Running: {alter_query}")
                        try:
                            db.session.execute(db.text(alter_query))
                            db.session.commit()
                            logging.info(f"[DB-SYNC] Successfully added column {table_name}.{col_name}")
                        except Exception as inner_e:
                            db.session.rollback()
                            logging.error(f"[DB-SYNC] Failed to add column {table_name}.{col_name}: {inner_e}")
        except Exception as e:
            logging.error(f"[DB-SYNC] Schema synchronization failed: {e}")

        # Migration validation disabled: using db.create_all() directly
        # Alembic migrations can be re-enabled later if needed
        logging.info('Database initialized via db.create_all() - schema is current')

        # Initialize default tenant if it doesn't exist
        default_tenant = Tenant.query.filter_by(name='Default Tenant').first()
        if not default_tenant:
            default_tenant = Tenant()
            default_tenant.name = 'Default Tenant'
            db.session.add(default_tenant)
            db.session.commit()

        # Initialize default admin if no users exist
        admin_exists = User.query.filter_by(username='admin').first()
        if not admin_exists:
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


def _run_smoke_tests():
    """Run lightweight smoke checks validating blueprints are registered and
    basic public endpoints respond. This avoids calling auth-protected APIs.
    """
    try:
        client = app.test_client()
        ok = True
        # Root should redirect to login when not authenticated
        r = client.get('/')
        if r.status_code not in (302, 301, 200):
            app.logger.warning('Smoke test: GET / returned %s', r.status_code)
            ok = False
        # Favicon should be reachable (static file handler)
        r = client.get('/favicon.ico')
        if r.status_code not in (200, 404):
            app.logger.warning('Smoke test: GET /favicon.ico returned %s', r.status_code)
            ok = False

        # Verify expected blueprints are registered
        expected = ['auth', 'main', 'api', 'agents', 'users', 'tenants']
        missing = [b for b in expected if b not in app.blueprints]
        if missing:
            app.logger.warning('Smoke test: missing blueprints: %s', missing)
            ok = False

        if ok:
            app.logger.info('Smoke tests passed')
        else:
            app.logger.warning('Smoke tests had warnings; inspect logs')
    except Exception:
        app.logger.exception('Exception while running smoke tests')


# Run smoke tests after startup validation
_run_smoke_tests()

# Apply database optimizations (indexes, analysis)
try:
    from web.db_optimizations import create_critical_indexes, analyze_database
    with app.app_context():
        create_critical_indexes(db)
        analyze_database(db)
except Exception as e:
    logging.warning(f"Database optimization warning: {e}")

# ── Weekly License Auto-Sync Scheduler ──────────────────────────────────────
def _start_license_sync_scheduler():
    """Start a daemon thread that syncs Azure licenses weekly."""
    import threading, time
    if os.environ.get('LICENSE_SYNC_DISABLED', '').lower() in ('1', 'true', 'yes'):
        logging.info('[LICENSE_SCHEDULER] Disabled by LICENSE_SYNC_DISABLED')
        return
    SYNC_INTERVAL = int(os.environ.get('LICENSE_SYNC_INTERVAL_SECONDS', 604800))  # 7 days
    default_initial_delay = 300 if DATABASE_URL.startswith('sqlite') else 60
    INITIAL_DELAY = int(os.environ.get('LICENSE_SYNC_INITIAL_DELAY_SECONDS', str(default_initial_delay)))

    def _sync_loop():
        time.sleep(INITIAL_DELAY)
        while True:
            try:
                with app.app_context():
                    from web.tasks.sync_licenses import run_license_sync
                    logging.info('[LICENSE_SCHEDULER] Starting weekly license sync...')
                    result = run_license_sync()
                    logging.info('[LICENSE_SCHEDULER] Sync completed: %s', result)
            except Exception:
                logging.exception('[LICENSE_SCHEDULER] Weekly license sync failed')
            time.sleep(SYNC_INTERVAL)

    t = threading.Thread(target=_sync_loop, daemon=True, name='LicenseWeeklySync')
    t.start()
    logging.info('[LICENSE_SCHEDULER] Weekly license sync scheduled (interval=%ds)', SYNC_INTERVAL)

try:
    _start_license_sync_scheduler()
except Exception as e:
    logging.warning(f"License scheduler warning: {e}")

# ── Azure AD Sync Service (Devices + Users auto-sync every 30 min) ──────────
def _start_azure_sync_service():
    """Start background Azure AD sync for devices and users."""
    if os.environ.get('AZURE_SYNC_DISABLED', '').lower() in ('1', 'true', 'yes'):
        logging.info('[AZURE_SYNC] Disabled by AZURE_SYNC_DISABLED')
        return
    try:
        from core.azure_sync_service import init_sync_service
        sync_minutes = int(os.environ.get('AZURE_SYNC_INTERVAL_MINUTES', '30'))
        init_sync_service(app, sync_interval_minutes=sync_minutes)
        logging.info('[AZURE_SYNC] Background device/user sync started (interval=%dm)', sync_minutes)
    except Exception as e:
        logging.warning(f'[AZURE_SYNC] Could not start sync service: {e}')

try:
    _start_azure_sync_service()
except Exception as e:
    logging.warning(f"Azure sync service warning: {e}")

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
    
    port = int(os.environ.get("PORT", 5000))
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

    # Import scheduler shutdown function if available; fall back to no-op
    try:
        from web.jobs import shutdown_scheduler
    except Exception:
        def shutdown_scheduler():
            try:
                logging.info('shutdown_scheduler unavailable; skipping')
            except Exception:
                pass

    try:
        socketio.run(
            app,
            host=bind_host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
    finally:
        try:
            shutdown_scheduler()
        except Exception:
            logging.exception('Error while shutting down scheduler')
