"""
INTEGRATION INSTRUCTIONS - License Management System
Complete step-by-step guide to integrate all new components
"""

# ════════════════════════════════════════════════════════════════════════════

# PHASE 1: DATABASE SETUP

# ════════════════════════════════════════════════════════════════════════════

## Step 1.1: Add License Models to web/models.py

## Location: End of web/models.py

## Action: Append the following imports and models from LICENSE_MODELS.py

```python
# At the top of web/models.py, ensure these imports exist:
from datetime import datetime

# Append these models at the end of web/models.py:

class AzureLicense(db.Model):
    """Azure subscription licenses (SKUs)"""
    __tablename__ = 'azure_license'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # License identifiers
    sku_id = db.Column(db.String(255), nullable=False, index=True)
    sku_name = db.Column(db.String(255))  # e.g., "ENTERPRISEPACK"
    product_name = db.Column(db.String(255))  # e.g., "Office 365 E3"

    # License counts
    total_licenses = db.Column(db.Integer, default=0)
    assigned_licenses = db.Column(db.Integer, default=0)
    available_licenses = db.Column(db.Integer, default=0)

    # Service plans included (JSON string)
    service_plans_json = db.Column(db.Text)

    # Tracking
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'sku_id', name='uq_azure_license'),
        db.Index('idx_azure_license_tenant', 'tenant_id'),
    )


class AzureLicenseAssignment(db.Model):
    """License assignments to individual users"""
    __tablename__ = 'azure_license_assignment'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # Relationships
    user_id = db.Column(db.Integer, db.ForeignKey('azure_user.id'), nullable=False)
    license_id = db.Column(db.Integer, db.ForeignKey('azure_license.id'), nullable=False)

    # Disable specific service plans within license
    disabled_plans_json = db.Column(db.Text)  # JSON array of disabled plan IDs

    # Timing
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relationships for easy access
    user = db.relationship('AzureUser', backref=db.backref('licenses', lazy='dynamic'))
    license = db.relationship('AzureLicense', backref=db.backref('assignments', lazy='dynamic'))

    __table_args__ = (
        db.Index('idx_license_assignment_user', 'user_id'),
        db.Index('idx_license_assignment_license', 'license_id'),
        db.Index('idx_license_assignment_tenant', 'tenant_id'),
    )


class AzureDeviceOwner(db.Model):
    """Relationship between devices and their assigned users"""
    __tablename__ = 'azure_device_owner'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # Relationships
    device_id = db.Column(db.Integer, db.ForeignKey('azure_device.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('azure_user.id'), nullable=False)

    # Timing
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relationships for easy access
    device = db.relationship('AzureDevice', backref=db.backref('owners', lazy='dynamic'))
    user = db.relationship('AzureUser', backref=db.backref('owned_devices', lazy='dynamic'))

    __table_args__ = (
        db.Index('idx_device_owner_device', 'device_id'),
        db.Index('idx_device_owner_user', 'user_id'),
        db.Index('idx_device_owner_tenant', 'tenant_id'),
    )
```

## Step 1.2: Run Migration Scripts

## Terminal Commands:

```powershell
# First ensure you're in the correct directory
cd "<path-to>\ServerMonitor"

# Run the license migration
python -m scripts.database.migrate_add_licenses

# Verify database has new tables
python -c "from web.app import db; from web.models import AzureLicense; print('✓ Models loaded successfully')"
```

# ════════════════════════════════════════════════════════════════════════════

# PHASE 2: BLUEPRINT REGISTRATION

# ════════════════════════════════════════════════════════════════════════════

## Step 2.1: Register New API Blueprints in web/app.py

## Location: Around line 570-580 (where other blueprints are registered)

## Add these imports at the top:

```python
# Add these to the imports section at top of web/app.py:
from web.routes.status_management import status_mgmt_bp
from web.routes.admin_status import admin_status_bp
from web.routes.analytics import analytics_bp
from web.routes.license_management import license_bp
```

## Add these registrations after the existing blueprint registrations (look for app.register_blueprint):

```python
# Register new blueprints
app.register_blueprint(status_mgmt_bp)
app.register_blueprint(admin_status_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(license_bp)
```

# ════════════════════════════════════════════════════════════════════════════

# PHASE 3: SCHEDULER SETUP

# ════════════════════════════════════════════════════════════════════════════

## Step 3.1: Update web/app.py to Initialize Scheduler

## Find the **name** == '**main**' section at bottom of web/app.py

## Update it to:

```python
if __name__ == '__main__':
    # Initialize database and scheduler
    with app.app_context():
        db.create_all()
        from web.scheduler import init_scheduler, shutdown_scheduler

        scheduler = init_scheduler(app)

        try:
            # Start Flask app (blocks until interrupted)
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        finally:
            # Gracefully shutdown scheduler
            shutdown_scheduler()
```

## Step 3.2: Add Scheduler to requirements.txt

```
APScheduler==3.10.1
```

## Install dependencies:

```powershell
pip install APScheduler==3.10.1
```

# ════════════════════════════════════════════════════════════════════════════

# PHASE 4: TESTING API ENDPOINTS

# ════════════════════════════════════════════════════════════════════════════

## Test Analytics API:

```bash
curl -X GET "http://localhost:5000/api/v2/analytics/overview" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/analytics/devices/activity-timeline" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/analytics/employees/device-mapping" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/analytics/inactivity-report" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Test License API:

```bash
curl -X GET "http://localhost:5000/api/v2/licenses/overview" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/licenses/1/breakdown" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/licenses/user/1/assignments" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/licenses/report/utilization" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5000/api/v2/licenses/sync-status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Test Status Management API:

```bash
curl -X POST "http://localhost:5000/api/v2/status/azure/device/1/retire" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"

curl -X GET "http://localhost:5000/api/v2/status/devices/inactive-summary" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

# ════════════════════════════════════════════════════════════════════════════

# PHASE 5: FRONTEND TEMPLATES (Optional - for UI)

# ════════════════════════════════════════════════════════════════════════════

## Step 5.1: Create License Dashboard Template

## File: web/templates/licenses/dashboard.html

(See LICENSE_DASHBOARD_TEMPLATE.html for full template)

## Step 5.2: Add Navigation Link

## In web/templates/base.html, find the navigation bar and add:

```html
<li class="nav-item">
  <a class="nav-link" href="{{ url_for('licenses.dashboard') }}">
    Licenses
    <span class="badge badge-danger" id="unused-license-count">0</span>
  </a>
</li>
```

## Step 5.3: Update dashboard.html

## Add status columns and activity indicators to device/user tables

# ════════════════════════════════════════════════════════════════════════════

# VERIFICATION CHECKLIST

# ════════════════════════════════════════════════════════════════════════════

✓ Step 1.1: Added license models to web/models.py
✓ Step 1.2: Ran migration scripts
✓ Step 2.1: Registered all blueprints in web/app.py
✓ Step 3.1: Initialized scheduler in web/app.py
✓ Step 3.2: Added APScheduler to requirements.txt and installed
✓ Step 4: Tested all API endpoints
✓ Step 5: Created frontend templates (optional)

Once all steps are complete, restart the application:

```powershell
# Stop current instance (Ctrl+C)
# Restart with:
python main.py
```

# ════════════════════════════════════════════════════════════════════════════

# WHAT'S HAPPENING AUTOMATICALLY

# ════════════════════════════════════════════════════════════════════════════

1. WEEKLY AZURE SYNC (Monday 2:00 AM)
   - Fetches all devices from Azure Graph API
   - Detects activity status (last sign-in > 90 days = inactive)
   - Fetches all users from Azure
   - Detects employment status (inactive > 120 days OR accountEnabled=false)
   - Syncs all license SKUs and assignments
   - Maps devices to device owners

2. DAILY INACTIVE DETECTION (Daily 3:00 AM)
   - Automatically marks stale devices as inactive
   - Automatically marks stale users as inactive/terminated
   - Creates audit trail of changes

3. MANUAL ACTIONS (Available anytime)
   - Mark device as retired
   - Reactivate device
   - Mark user as terminated with exit date
   - Reactivate user from leave
   - View complete inactivity reports

4. ANALYTICS DASHBOARDS (Real-time)
   - Device activity timeline
   - Employee-to-device mapping
   - License utilization breakdown
   - Inactivity reports with filtering

# ════════════════════════════════════════════════════════════════════════════

# TROUBLESHOOTING

# ════════════════════════════════════════════════════════════════════════════

## Issue: "No module named 'APScheduler'"

## Solution:

```powershell
pip install APScheduler==3.10.1
```

## Issue: "Blueprint not found"

## Solution: Verify blueprint imports and registrations in web/app.py

## Issue: "Database locked error"

## Solution: Restart the application

## Issue: "Missing azure_sync_service module"

## Solution: Ensure web/azure_sync_service.py exists (should be from previous implementation)

## Issue: "Scheduler not running"

## Check logs: Look for "[SCHEDULER]" prefixed log messages

"""
