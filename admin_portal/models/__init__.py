"""
Database models for Admin Portal
"""

import secrets
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class Tenant(db.Model):
    """Multi-tenant organization"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # Azure integration credentials (optional). Secrets are stored in DB;
    # for production consider encrypting these values at rest.
    azure_client_id = db.Column(db.String(200))
    azure_client_secret = db.Column(db.String(500))
    azure_tenant_id = db.Column(db.String(200))
    azure_display_name = db.Column(db.String(200))
    azure_registered = db.Column(db.Boolean, default=False)
    
    # White-label branding JSON
    branding = db.Column(
        db.JSON,
        nullable=False,
        default=lambda: {
            "company_name": "ServerMonitor",
            "logo_url": None,
            "primary_color": "#2563eb",
            "secondary_color": "#1e40af",
            "accent_color": "#dc2626",
            "favicon_url": None
        }
    )
    
    def __init__(self, name, branding=None):
        self.name = name
        if branding:
            self.branding = {**self.branding, **branding}
        else:
            self.branding = {
                "company_name": name,
                "logo_url": None,
                "primary_color": "#2563eb",
                "secondary_color": "#1e40af",
                "accent_color": "#dc2626",
                "favicon_url": None
            }
    
    def get_branding(self):
        """Get branding with defaults"""
        defaults = {
            "company_name": "ServerMonitor",
            "logo_url": None,
            "primary_color": "#2563eb",
            "secondary_color": "#1e40af",
            "accent_color": "#dc2626",
            "favicon_url": None
        }
        if self.branding:
            return {**defaults, **self.branding}
        return defaults
    
    def update_branding(self, **kwargs):
        """Update branding with validation"""
        current = self.get_branding()
        for key in ["company_name", "logo_url", "primary_color", "secondary_color", "accent_color", "favicon_url"]:
            if key in kwargs and kwargs[key] is not None:
                current[key] = kwargs[key]
        self.branding = current
        return self.branding


class User(UserMixin, db.Model):
    """Portal user with tenant assignment"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    is_superadmin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), nullable=False, default='user')
    
    def __init__(self, username, password, tenant_id=None, is_superadmin=False, role='user'):
        self.username = username
        self.password = password
        self.tenant_id = tenant_id
        self.is_superadmin = is_superadmin
        self.role = role


class AgentKey(db.Model):
    """API key for agent authentication"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(32))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    key_name = db.Column(db.String(100))  # Human-readable name
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)
    
    def __init__(self, tenant_id, key_name=None, description=None):
        self.tenant_id = tenant_id
        self.key_name = key_name
        self.description = description


class Server(db.Model):
    """Managed server"""
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(100), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    ip = db.Column(db.String(100))
    
    def __init__(self, hostname, tenant_id, ip=None):
        self.hostname = hostname
        self.tenant_id = tenant_id
        self.ip = ip


class VM(db.Model):
    """Virtual machine inventory"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'))


class SystemDiscovery(db.Model):
    """Track discovered systems and their import status"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    hostname = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(100))
    os_info = db.Column(db.String(255))
    discovered_at = db.Column(db.DateTime, server_default=db.func.now())
    imported_at = db.Column(db.DateTime)
    status = db.Column(db.String(50), default="pending")
    source = db.Column(db.String(50), default="ActiveDirectory")
    
    def __init__(self, tenant_id, hostname, ip=None, os_info=None, status="pending", source="ActiveDirectory"):
        self.tenant_id = tenant_id
        self.hostname = hostname
        self.ip = ip
        self.os_info = os_info
        self.status = status
        self.source = source


class DeploymentJob(db.Model):
    """Track agent deployment jobs"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    agent_key = db.Column(db.String(64))
    job_type = db.Column(db.String(50))
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    completed_at = db.Column(db.DateTime)
    log_output = db.Column(db.Text)
    
    def __init__(self, tenant_id, server_id, agent_key=None, job_type="deploy", status="pending"):
        self.tenant_id = tenant_id
        self.server_id = server_id
        self.agent_key = agent_key
        self.job_type = job_type
        self.status = status


class SystemAlert(db.Model):
    """System health alerts"""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    alert_type = db.Column(db.String(100))
    severity = db.Column(db.String(20), default="warning")
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    resolved_at = db.Column(db.DateTime)
    
    def __init__(self, server_id, alert_type, severity="warning", message=None):
        self.server_id = server_id
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
