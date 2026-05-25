"""
License Models - Add to web/models.py
Copy and append to end of models.py file
"""

# ─────────────────────────────────────────────────────────────────────────────
# LICENSE MANAGEMENT MODELS
# ─────────────────────────────────────────────────────────────────────────────

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
