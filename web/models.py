"""
Unified Database Models for ServerMonitor
"""

import secrets
import os
import uuid
import json
from flask_sqlalchemy import SQLAlchemy
from typing import Any
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# Database-aware column types: prefer native Postgres types when DATABASE_URL indicates Postgres
USE_POSTGRES = str(os.environ.get('DATABASE_URL', '')).startswith('postgres')
try:
    if USE_POSTGRES:
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB as PG_JSONB
        UUID_TYPE = PG_UUID(as_uuid=False)
        JSON_TYPE = PG_JSONB
    else:
        UUID_TYPE = db.String(36)
        JSON_TYPE = db.JSON
except Exception:
    # Fallbacks if dialect modules unavailable at import time
    UUID_TYPE = db.String(36)
    JSON_TYPE = db.JSON

class Tenant(db.Model):
    """Multi-tenant organization"""
    id = db.Column(db.Integer, primary_key=True)
    # Stable UUID for cross-system identification (added alongside integer PK)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(50), default='active', index=True) # active, suspended, hold
    # Azure integration credentials (optional).
    azure_client_id = db.Column(db.String(200))
    azure_client_secret = db.Column(db.String(500))
    azure_tenant_id = db.Column(db.String(200))
    azure_display_name = db.Column(db.String(200))
    azure_registered = db.Column(db.Boolean, default=False)
    # SharePoint delegated connection (Authorization Code flow)
    sharepoint_site_url = db.Column(db.String(500))
    sharepoint_connected = db.Column(db.Boolean, default=False)
    sharepoint_auto_sync = db.Column(db.Boolean, default=False)
    sharepoint_sync_interval_minutes = db.Column(db.Integer, default=60)
    last_sharepoint_sync_timestamp = db.Column(db.DateTime)
    previous_sharepoint_sync_timestamp = db.Column(db.DateTime)
    
    # ISV Polling Config
    polling_interval_minutes = db.Column(db.Integer, default=60)
    last_poll_timestamp = db.Column(db.DateTime)
    
    # White-label branding JSON
    branding = db.Column(
        JSON_TYPE,
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
    
    users = db.relationship('User', backref='tenant', lazy=True)
    servers = db.relationship('Server', backref='tenant', lazy=True)
    agent_keys = db.relationship('AgentKey', backref='tenant', lazy=True)
    
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
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True) # Link to Employee record
    is_superadmin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), nullable=False, default='user')

class AgentKey(db.Model):
    """API key for agent authentication"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(32))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    key_name = db.Column(db.String(100))
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)

class Server(db.Model):
    """Managed server / Endpoint"""
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    hostname = db.Column(db.String(100), nullable=True) # temporary
    type = db.Column(db.String(20), default='agent') # 'azure' | 'agent'
    source = db.Column(db.String(20), default='agent')  # origin of record: agent, azure, AD, etc.
    api_key = db.Column(db.String(64), index=True)
    last_seen = db.Column(db.DateTime)
    device_active_status = db.Column(db.String(50), default='active')
    
    # Additional backwards compatibility fields
    status = db.Column(db.String(20), default="offline")
    ip = db.Column(db.String(100))
    os_info = db.Column(db.String(255))
    is_hyperv_host = db.Column(db.Boolean, default=False)
    server_type = db.Column(db.String(50), default="Endpoint")
    agent_installed = db.Column(db.Boolean, default=False)
    agent_version = db.Column(db.String(50))
    monitoring_mode = db.Column(db.String(20), default='full')
    monitoring_active = db.Column(db.Boolean, default=False)
    monitoring_drives = db.Column(db.String(100), default="C")
    azure_device_id = db.Column(db.String(255))
    serial_number = db.Column(db.String(100))
    address = db.Column(db.String(255))
    
    # Screenshot configuration
    screenshot_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text('true'))  # ENABLED BY DEFAULT for all new servers
    screenshot_interval_minutes = db.Column(db.Integer, nullable=False, default=10, server_default=db.text('10'))
    
    metrics = db.relationship('Metric', backref='server', lazy='dynamic')
    vms = db.relationship('VM', backref='host_server', lazy='dynamic')

    @property
    def status_label(self):
        """ONLINE, IDLE, OFFLINE or NOT INSTALLED based on agent status and last_seen"""
        if not getattr(self, 'agent_installed', True):
            return "NOT INSTALLED"
        if not self.last_seen:
            return "OFFLINE"
        
        now = datetime.utcnow()
        diff = (now - self.last_seen).total_seconds()
        
        if diff > 60:
            return "OFFLINE"
            
        # Check latest activity for idle status
        latest_activity = EmployeeActivity.query.filter_by(server_id=self.id).order_by(EmployeeActivity.timestamp.desc()).first()
        if latest_activity and latest_activity.idle_time > 300:
            return "IDLE"
            
        return "ONLINE"

    @property
    def is_online(self):
        """Boolean convenience for templates: True when ONLINE or IDLE"""
        return self.status_label in ("ONLINE", "IDLE")

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    @property
    def vms_count(self):
        return self.vms.count() if hasattr(self.vms, 'count') else len(self.vms)

class VM(db.Model):
    """Virtual machine inventory"""
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'))
    name = db.Column(db.String(100))
    state = db.Column(db.String(50))
    cpu = db.Column(db.Float)
    ram = db.Column(db.Float)
    
    # Keeping original fields for backward compatibility
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    cpu_usage = db.Column(db.Float)
    memory_assigned = db.Column(db.Float)
    uptime = db.Column(db.String(100))
    path = db.Column(db.String(255))
    host_ip = db.Column(db.String(100))
    host_os = db.Column(db.String(255))

    @property
    def vm_name(self):
        """Alias for backward compatibility with templates"""
        return self.name

    @vm_name.setter
    def vm_name(self, value):
        self.name = value

    def __init__(self, **kwargs: Any):
        # Support vm_name kwarg mapping to name
        if 'vm_name' in kwargs and 'name' not in kwargs:
            kwargs['name'] = kwargs.pop('vm_name')
        elif 'vm_name' in kwargs:
            kwargs.pop('vm_name')
        super().__init__(**kwargs)

class Metric(db.Model):
    """Server Metrics"""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'))
    cpu = db.Column(db.Float)
    ram = db.Column(db.Float)
    disk = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True)
    
    # Original fields
    virtual_cores = db.Column(db.Integer)
    cpu_util_percent = db.Column(db.Float)
    total_ram_gb = db.Column(db.Float)
    available_ram_gb = db.Column(db.Float)
    used_ram_gb = db.Column(db.Float)
    ram_util_percent = db.Column(db.Float)
    total_ssd_gb = db.Column(db.Float)
    available_ssd_gb = db.Column(db.Float)
    used_ssd_gb = db.Column(db.Float)
    ssd_util_percent = db.Column(db.Float)
    drive_letters_checked = db.Column(db.String(100))
    drives_details = db.Column(db.Text)
    details = db.Column(db.Text)  # JSON: activity, installed_software, etc.
    error = db.Column(db.Text)

class EmployeeActivity(db.Model):
    """Tracking employee productivity"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), index=True)  # Linked to employee for productivity tracking
    user = db.Column(db.String(100), index=True)  # Local username from agent
    app = db.Column(db.String(255))
    window_title = db.Column(db.String(512))
    idle_time = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        db.Index('idx_employee_activity_tenant_server_user', 'tenant_id', 'server_id', 'user'),
        db.Index('idx_employee_activity_tenant_timestamp', 'tenant_id', 'timestamp'),
        db.Index('idx_employee_activity_employee_timestamp', 'employee_id', 'timestamp'),
         db.Index('idx_employee_activity_server_timestamp', 'server_id', 'timestamp'),
    )


class Screenshot(db.Model):
    """Screenshot audit trail — tracks captures uploaded to SharePoint"""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    hostname = db.Column(db.String(100))
    captured_at = db.Column(db.DateTime, nullable=False)
    uploaded_at = db.Column(db.DateTime)
    sharepoint_url = db.Column(db.String(500))
    uploaded = db.Column(db.Boolean, default=False)
    file_size_kb = db.Column(db.Integer)
    active_user = db.Column(db.String(200))  # who was logged in
    os_info = db.Column(db.String(255))
    ip_address = db.Column(db.String(100))
    local_file_path = db.Column(db.String(500))  # local fallback when SharePoint is unavailable
    
    # Relationship to Server for easy access
    server = db.relationship('Server', backref=db.backref('screenshots', lazy='dynamic'), foreign_keys=[server_id])

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)


class SharePointMetricQueue(db.Model):
    """Queue of metric rows pending mirror to SharePoint (secondary storage)."""
    __tablename__ = 'sharepoint_metric_queue'

    id = db.Column(db.Integer, primary_key=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('metric.id'), nullable=False, unique=True, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, synced, failed
    attempts = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    synced_at = db.Column(db.DateTime)


class SystemDiscovery(db.Model):
    """Track discovered systems (e.g. via Active Directory)"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    hostname = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(100))
    os_info = db.Column(db.String(255))
    discovered_at = db.Column(db.DateTime, server_default=db.func.now())
    imported_at = db.Column(db.DateTime)
    status = db.Column(db.String(50), default="pending")
    source = db.Column(db.String(50), default="ActiveDirectory")

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

class SystemAlert(db.Model):
    """System health alerts"""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    alert_type = db.Column(db.String(100)) # e.g. "High CPU", "Offline"
    severity = db.Column(db.String(20), default="warning") # info, warning, critical
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    resolved_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

class RemoteCommand(db.Model):
    """Remote execution queuing"""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    server = db.relationship('Server', backref=db.backref('remote_commands', lazy='dynamic'))
    command = db.Column(db.String(255), nullable=False) # e.g. "Restart-Computer", "Stop-Process"
    parameters = db.Column(db.Text) # JSON string of parameters
    status = db.Column(db.String(50), default="pending") # pending, sent, running, completed, failed
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    executed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)  # When command finished execution
    output = db.Column(db.Text)  # Command output/stdout
    error_output = db.Column(db.Text)  # Command error output/stderr
    exit_code = db.Column(db.Integer)  # Command exit code (0 = success)
    timeout_seconds = db.Column(db.Integer, default=120)  # Command timeout in seconds
    created_by = db.Column(db.String(150))  # Username who queued the command

class AuditLog(db.Model):
    """Phase 8: Enterprise Audit Logging - Remote Operations & Asset Management"""
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    user = db.Column(db.String(150), nullable=False)  # Username (string)
    action = db.Column(db.String(100), nullable=False)  # e.g., DEPLOY_SOFTWARE:install, REMOTE_ACCESS:RDP
    resource = db.Column(db.String(255))  # e.g., Server:hostname
    details = db.Column(db.Text)  # Additional context
    status = db.Column(db.String(50), default='pending')  # pending, accessed, success, failed
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Indexes for efficient queries
    __table_args__ = (
        db.Index('idx_audit_tenant_timestamp', 'tenant_id', 'timestamp'),
        db.Index('idx_audit_action', 'action'),
        db.Index('idx_audit_user', 'user'),
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)


class EmployeeAssetLog(db.Model):
    """Track employee device logins for asset management"""
    __tablename__ = 'employee_asset_log'
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # Employee information
    employee_id = db.Column(db.String(100), nullable=False, index=True)
    employee_email = db.Column(db.String(255), nullable=False, index=True)
    
    # Device information
    hostname = db.Column(db.String(100), nullable=False, index=True)
    ip_address = db.Column(db.String(100))
    os_info = db.Column(db.String(255))
    domain = db.Column(db.String(100))
    device_type = db.Column(db.String(50))  # laptop, desktop, server, mobile
    
    # Timing
    login_timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Indexes for efficient queries
    __table_args__ = (
        db.Index('idx_emp_asset_tenant_id', 'tenant_id'),
        db.Index('idx_emp_asset_employee_email', 'employee_email'),
        db.Index('idx_emp_asset_hostname', 'hostname'),
        db.Index('idx_emp_asset_login_time', 'login_timestamp'),
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)


# ---------------------------------------------------------------------------
# Licensing & Productivity Models
# ---------------------------------------------------------------------------
class LicenseSku(db.Model):
    """Represents a tenant subscription SKU (Microsoft Graph subscribedSku)

    Stores dynamic metadata in JSONB when Postgres is used.
    """
    __tablename__ = 'license_sku'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    sku_id = db.Column(db.String(100), nullable=False, index=True)
    sku_part_number = db.Column(db.String(200))
    prepaid_units = db.Column(db.Integer)
    consumed_units = db.Column(db.Integer)
    meta_data = db.Column('metadata', JSON_TYPE)
    fetched_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.Index('idx_license_sku_tenant_sku', 'tenant_id', 'sku_id', unique=False),
    )


class LicenseAssignment(db.Model):
    """Per-user license assignment record derived from Graph licenseDetails.

    Fields:
      - user_id (string) : Graph user id (UUID string)
      - user_principal_name : email/login
      - sku_id : subscribedSku skuId
      - state : enabled/disabled
    """
    __tablename__ = 'license_assignment'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    user_id = db.Column(db.String(100), index=True)
    user_principal_name = db.Column(db.String(200), index=True)
    sku_id = db.Column(db.String(100), index=True)
    state = db.Column(db.String(50))
    assigned_at = db.Column(db.DateTime)
    last_seen = db.Column(db.DateTime)
    meta_data = db.Column('metadata', JSON_TYPE)

    __table_args__ = (
        db.Index('idx_license_assign_tenant_user_sku', 'tenant_id', 'user_id', 'sku_id'),
    )


class LicenseHistory(db.Model):
    """Historical record of license assignments and removals."""
    __tablename__ = 'license_history'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    user_id = db.Column(db.String(100), index=True)
    user_principal_name = db.Column(db.String(200), index=True)
    sku_id = db.Column(db.String(100), index=True)
    event_type = db.Column(db.String(50)) # 'ASSIGNED', 'REMOVED'
    event_date = db.Column(db.DateTime, default=datetime.utcnow)
    assignment_source = db.Column(db.String(50), default='graph_sync')
    
    __table_args__ = (
        db.Index('idx_license_hist_tenant_user', 'tenant_id', 'user_id'),
    )


class TenantLicenseSummary(db.Model):
    """Daily snapshot of total and consumed license counts for analytics."""
    __tablename__ = 'tenant_license_summary'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    sku_id = db.Column(db.String(100), index=True)
    sku_part_number = db.Column(db.String(200))
    snapshot_date = db.Column(db.Date, default=datetime.utcnow)
    total_units = db.Column(db.Integer, default=0)
    consumed_units = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'sku_id', 'snapshot_date', name='uq_tenant_sku_date'),
    )


class ProductivityClassification(db.Model):
    """Classification rules for mapping applications/sites to productivity categories.

    pattern: simple substring or regex used to match application or URL.
    category: 'productive' | 'non_productive' | 'neutral'
    metadata: dynamic JSON for notes or source of rule
    """
    __tablename__ = 'productivity_classification'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    pattern = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    meta_data = db.Column('metadata', JSON_TYPE)


class SyncJob(db.Model):
    """Audit trail for background sync jobs (licenses, discovery, etc.)"""
    __tablename__ = 'sync_job'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    job_type = db.Column(db.String(100), nullable=False, index=True)
    status = db.Column(db.String(50), default='pending', index=True)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    log = db.Column(db.Text)
    meta_data = db.Column('metadata', JSON_TYPE)


class Employee(db.Model):
    """Company employees managed by IT (Source of Truth for Monitoring)"""
    __tablename__ = 'employee'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    display_name = db.Column(db.String(255), index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    department = db.Column(db.String(100))
    designation = db.Column(db.String(100))
    azure_user_id = db.Column(db.String(255), index=True)
    # Local OS username to map agent data (e.g. "sachin" -> "sachin@bafflesol.com")
    local_username = db.Column(db.String(100), index=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True) # Hierarchical RBAC
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)
    employment_status = db.Column(db.String(50), default='active')

    __table_args__ = (
        db.Index('idx_employee_tenant_azure_user', 'tenant_id', 'azure_user_id'),
        db.Index('idx_employee_tenant_local_username', 'tenant_id', 'local_username'),
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

class DeviceActivity(db.Model):
    """Track user activity sessions on monitored devices"""
    __tablename__ = 'device_activity'
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    session_user = db.Column(db.String(150))  # OS-level username logged in
    login_time = db.Column(db.DateTime)
    logout_time = db.Column(db.DateTime)
    idle_minutes = db.Column(db.Float, default=0)
    active_minutes = db.Column(db.Float, default=0)
    session_type = db.Column(db.String(50), default='interactive')  # interactive, rdp, console
    reported_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# MICROSOFT AZURE MODELS (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class AzureUser(db.Model):
    """Users from Azure AD / Entra ID"""
    __tablename__ = 'azure_user'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # Azure AD Object ID
    user_id = db.Column(db.String(255), nullable=False, index=True)
    # Employee identifier (local username portion of userPrincipalName)
    employee_id = db.Column(db.String(255), nullable=True, index=True)
    mail_nickname = db.Column(db.String(255), nullable=True, index=True)
    sam_account_name = db.Column(db.String(255), nullable=True, index=True)
    
    # User profile
    email = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255))
    job_title = db.Column(db.String(255))
    department = db.Column(db.String(255))
    
    # Status tracking
    is_active = db.Column(db.Integer, default=1)  # 1=active, 0=inactive
    employment_status = db.Column(db.String(50), default='active')  # active, inactive, terminated, onleave
    left_date = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, nullable=True)
    
    # Tracking
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'user_id', name='uq_azure_user'),
        db.Index('idx_azure_user_email', 'email'),
        db.Index('idx_azure_user_tenant_employee', 'tenant_id', 'employee_id'),
        db.Index('idx_azure_user_tenant_mail_nickname', 'tenant_id', 'mail_nickname'),
        db.Index('idx_azure_user_tenant_sam', 'tenant_id', 'sam_account_name'),
    )


class AzureDevice(db.Model):
    """Devices from Azure AD / Intune"""
    __tablename__ = 'azure_device'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID_TYPE, unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # Azure AD Object ID
    device_id = db.Column(db.String(255), nullable=False, index=True)
    
    # Device properties
    display_name = db.Column(db.String(255), nullable=False)
    normalized_hostname = db.Column(db.String(255), index=True)
    device_type = db.Column(db.String(100))  # Desktop, Mobile, etc.
    os_version = db.Column(db.String(255))
    os_platform = db.Column(db.String(100))  # Windows, iOS, Android, etc.
    
    # Management
    is_compliant = db.Column(db.Boolean, default=False)
    is_managed_by_intune = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Integer, default=1) # 1 for active, 0 for inactive
    device_status = db.Column(db.String(50), default='active')
    disabled_at = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, nullable=True)
    
    # Tracking
    last_graph_sync = db.Column(db.DateTime, nullable=True)
    last_intune_sync = db.Column(db.DateTime, nullable=True)
    last_heartbeat = db.Column(db.DateTime, nullable=True)
    last_user_activity = db.Column(db.DateTime, nullable=True)
    
    last_synced = db.Column(db.DateTime, default=datetime.utcnow) # legacy back-compat
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'device_id', name='uq_azure_device'),
        db.Index('idx_azure_device_display_name', 'display_name'),
        db.Index('idx_azure_device_tenant_normalized_hostname', 'tenant_id', 'normalized_hostname'),
    )


class AzureDeviceOwner(db.Model):
    """Relationship between Azure devices and users"""
    __tablename__ = 'azure_device_owner'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # References
    # Store DB PKs for device/user to ensure FK integrity across DBs
    device_id = db.Column(db.Integer, db.ForeignKey('azure_device.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('azure_user.id'), nullable=False)
    
    # Type of ownership
    owner_type = db.Column(db.String(50), default="primary")  # primary, registered, etc.
    
    # Tracking
    linked_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'device_id', 'user_id', name='uq_device_owner'),
        db.Index('idx_device_owner_user', 'user_id'),
    )


class EmployeeDeviceAssignment(db.Model):
    """Unified Correlation Engine: Links Employee to an Agent Server and Azure Device"""
    __tablename__ = 'employee_device_assignment'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # Core relationships
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False, index=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=True, index=True)  # Agent server
    azure_device_id = db.Column(db.Integer, db.ForeignKey('azure_device.id'), nullable=True, index=True)
    
    # Assignment details
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    unassigned_at = db.Column(db.DateTime, nullable=True)
    assignment_source = db.Column(db.String(50))  # 'intune_sync', 'agent_heartbeat', 'admin_manual'
    is_active = db.Column(db.Boolean, default=True)
    
    # Tracking
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
    
    __table_args__ = (
        db.Index('idx_emp_dev_active', 'tenant_id', 'is_active'),
    )


class EntraRole(db.Model):
    """User roles in the application (from Entra/Azure AD)"""
    __tablename__ = 'entra_role'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    
    # User reference (email or Entra ID)
    user_email = db.Column(db.String(255), nullable=False, index=True)
    
    # Role assignment
    role = db.Column(db.String(50), nullable=False)  # super_admin, tenant_admin, user
    
    # Tracking
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(255))  # Who assigned this role
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'user_email', name='uq_user_role'),
        db.Index('idx_entra_role_email', 'user_email'),
    )


class AgentControlCommand(db.Model):
    """
    Agent control commands queue (database-backed, not SharePoint).
    Replaces SharePoint AgentControl list for reliability.
    """
    __tablename__ = 'agent_control_command'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    
    # Target agent
    hostname = db.Column(db.String(255), nullable=False, index=True)
    
    # Command details
    action = db.Column(db.String(100), nullable=False)  # RestartAgent, DisableAgent, InstallSoftware
    payload = db.Column(db.Text)  # JSON payload
    
    # Status tracking
    status = db.Column(db.String(50), nullable=False, default="Pending", index=True)  # Pending, InProgress, Done, Failed
    requested_by = db.Column(db.String(255))
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime)
    result_message = db.Column(db.Text)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_agent_cmd_hostname', 'hostname'),
        db.Index('idx_agent_cmd_status', 'status'),
        db.Index('idx_agent_cmd_tenant', 'tenant_id'),
        db.Index('idx_agent_cmd_requested_at', 'requested_at'),
    )


class SyncNotification(db.Model):
    """Stores sync event notifications for the notification bell UI"""
    __tablename__ = 'sync_notification'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    
    # Event info
    category = db.Column(db.String(50), nullable=False, default='sync')  # sync, error, alert
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    
    # Breakdown (JSON) - stores counts per category
    breakdown = db.Column(db.Text)  # JSON string
    
    # Status
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        db.Index('idx_sync_notif_tenant_read', 'tenant_id', 'is_read'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# AZURE LICENSE MANAGEMENT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class AzureLicense(db.Model):
    """Azure subscription licenses (SKUs) - tracks organizational licenses"""
    __tablename__ = 'azure_license'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    
    # License identifiers from Azure
    sku_id = db.Column(db.String(255), nullable=False, index=True)
    sku_name = db.Column(db.String(255))  # e.g., "ENTERPRISEPACK"
    product_name = db.Column(db.String(255))  # e.g., "Office 365 E3"
    
    # License counts (updated on sync)
    total_licenses = db.Column(db.Integer, default=0, index=True)
    assigned_licenses = db.Column(db.Integer, default=0, index=True)
    available_licenses = db.Column(db.Integer, default=0)
    
    # Service plans included (JSON string)
    service_plans_json = db.Column(db.Text)
    
    # Tracking & Performance
    last_synced = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'sku_id', name='uq_azure_license'),
        db.Index('idx_azure_license_tenant', 'tenant_id'),
        db.Index('idx_azure_license_available', 'available_licenses'),  # For dashboard queries
    )


class AzureLicenseAssignment(db.Model):
    """Tracks which users have which licenses assigned"""
    __tablename__ = 'azure_license_assignment'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    
    # Relationships to existing models
    # store DB PK of AzureUser to ensure referential integrity
    user_id = db.Column(db.Integer, db.ForeignKey('azure_user.id'), nullable=False, index=True)
    license_id = db.Column(db.Integer, db.ForeignKey('azure_license.id'), nullable=False, index=True)
    
    # Disable specific service plans within the license
    disabled_plans_json = db.Column(db.Text)  # JSON array of disabled plan IDs
    
    # Timing
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.Index('idx_license_assignment_user', 'user_id'),
        db.Index('idx_license_assignment_license', 'license_id'),
        db.Index('idx_license_assignment_tenant', 'tenant_id'),
        db.UniqueConstraint('user_id', 'license_id', name='uq_user_license'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTERPRISE WORKFORCE PRODUCTIVITY (Phase 6)
# ─────────────────────────────────────────────────────────────────────────────

class ActivitySession(db.Model):
    """Continuous block of activity for a user on a device."""
    __tablename__ = 'activity_session'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False, index=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=True)
    

    # Computed aggregates for the session block (storing seconds for precision)
    active_minutes = db.Column(db.Integer, default=0)
    idle_minutes = db.Column(db.Integer, default=0)
    productive_minutes = db.Column(db.Integer, default=0)
    non_productive_minutes = db.Column(db.Integer, default=0)

    # New canonical fields
    active_seconds = db.Column(db.Integer, default=0)
    idle_seconds = db.Column(db.Integer, default=0)
    productive_seconds = db.Column(db.Integer, default=0)
    non_productive_seconds = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class AppUsage(db.Model):
    """Detailed app usage within a session."""
    __tablename__ = 'app_usage'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('activity_session.id'), nullable=False, index=True)
    
    app_name = db.Column(db.String(255), nullable=False)
    window_title = db.Column(db.Text)
    url = db.Column(db.Text) # If browser
    
    start_time = db.Column(db.DateTime, nullable=False)
    duration_seconds = db.Column(db.Integer, default=0)
    
    classification = db.Column(db.String(50), default='neutral') # productive, non_productive, neutral
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class FocusSession(db.Model):
    """Identified blocks of high productivity / deep work."""
    __tablename__ = 'focus_session'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False, index=True)
    
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, default=0)
    
    primary_app = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class AttendanceRecord(db.Model):
    """Daily summary of attendance."""
    __tablename__ = 'attendance_record'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False, index=True)
    
    date = db.Column(db.Date, nullable=False)
    first_activity = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime)
        # Backward compatibility
    total_active_minutes = db.Column(db.Integer, default=0)
    total_idle_minutes = db.Column(db.Integer, default=0)

        # New canonical fields
    total_active_seconds = db.Column(db.Integer, default=0)
    total_idle_seconds = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(50)) # present, absent, half_day
    
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'employee_id', 'date', name='uq_tenant_employee_date'),
    )
