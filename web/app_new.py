"""
Restructured ServerMonitor Application
=======================================

Unified dashboard with Microsoft Entra ID authentication.

Features:
  ✓ Microsoft Entra ID (Azure AD) OAuth2 authentication
  ✓ Role-based access control (RBAC)
  ✓ Microsoft Graph API integration for device discovery
  ✓ Unified dashboard with role-based views
  ✓ Real-time WebSocket connections
  ✓ Multi-tenant support

Architecture:
  • Removed old local authentication
  • Removed duplicate dashboards
  • Single unified dashboard (content changes by role)
  • All data from Microsoft ecosystem
  • Local database caches Azure AD data
"""

import logging
import os
import sys
from datetime import timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from gevent import monkey
    monkey.patch_all()
except Exception:
    pass

from flask import Flask, render_template, redirect, url_for, session
from flask_socketio import SocketIO
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("[APP]")

# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

# Security & Session Configuration
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    'dev-key-change-in-production'
)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('ENVIRONMENT', 'dev') == 'prod'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Database Configuration
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'servermonitor.db')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    f'sqlite:///{DB_PATH}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ─────────────────────────────────────────────────────────────────────────────
# EXTENSIONS
# ─────────────────────────────────────────────────────────────────────────────

# Database
from web.models import db
db.init_app(app)

# CORS
CORS(app, supports_credentials=True)

# WebSockets
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25
)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

# Authentication routes (Microsoft Entra ID)
from web.routes.auth_entra import auth_entra_bp
app.register_blueprint(auth_entra_bp)

# Dashboard routes (unified, role-based)
from web.routes.dashboard import dashboard_bp
app.register_blueprint(dashboard_bp)

# API routes (deprecated - for agent metrics only)
from web.routes.api import api_bp
app.register_blueprint(api_bp)

# ─────────────────────────────────────────────────────────────────────────────
# ROOT ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def root():
    """Root route - redirect to dashboard or login."""
    if 'user' in session:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('auth.login'))


@app.route('/health')
def health():
    """Health check endpoint."""
    return {'status': 'ok'}, 200


@app.route('/error')
def error_page():
    """Generic error page."""
    return render_template('error.html'), 500


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('error.html', message="Page not found"), 404


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors."""
    return render_template(
        'error.html',
        message="You don't have permission to access this resource"
    ), 403


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    db.session.rollback()
    return render_template('error.html', message="Internal server error"), 500


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def create_app(config=None):
    """Application factory function."""
    
    # Create tables
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")
    
    # Initialize Azure sync service (optional - for background sync)
    # from core.azure_sync_service import init_sync_service
    # init_sync_service(app, sync_interval_minutes=30)
    
    logger.info("Application initialized successfully")
    return app


# ─────────────────────────────────────────────────────────────────────────────
# DEVELOPMENT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Initialize app
    create_app()
    
    # Run development server
    socketio.run(
        app,
        host='0.0.0.0',
        port=3000,
        debug=os.environ.get('ENVIRONMENT') == 'dev'
    )
