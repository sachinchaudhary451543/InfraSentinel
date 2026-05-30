"""
Active Data Filter Service
Provides methods to filter for only ACTIVE devices, users, and employees
Excludes stale/inactive data from Azure and old employee records
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_
import logging

logger = logging.getLogger("[DATA_FILTER]")


class ActiveDataFilter:
    """Service to filter active systems, users, and employees"""
    
    # Configuration for what constitutes "active"
    CONFIG = {
        'azure_device_inactivity_days': 90,      # Devices inactive for 90+ days marked inactive
        'azure_user_inactivity_days': 120,        # Users inactive for 120+ days marked inactive
        'server_inactivity_days': 60,             # Servers inactive for 60+ days marked inactive
        'show_inactive': False,                    # By default, don't show inactive
    }
    
    @staticmethod
    def mark_inactive_azure_devices(db, tenant_id=None):
        """Mark Azure devices as inactive if no activity in threshold days"""
        from web.models import AzureDevice
        
        threshold_date = datetime.utcnow() - timedelta(
            days=ActiveDataFilter.CONFIG['azure_device_inactivity_days']
        )
        
        # Mark devices with last_activity before threshold as inactive
        if tenant_id:
            query = AzureDevice.query.filter(
                AzureDevice.tenant_id == tenant_id,
                AzureDevice.last_activity < threshold_date,
                AzureDevice.is_active == 1
            )
        else:
            query = AzureDevice.query.filter(
                AzureDevice.last_activity < threshold_date,
                AzureDevice.is_active == 1
            )
        
        count = 0
        for device in query.all():
            device.is_active = 0
            device.device_status = 'inactive'
            device.disabled_at = datetime.utcnow()
            count += 1
        
        if count > 0:
            db.session.commit()
            logger.info(f"Marked {count} Azure devices as inactive (no activity for {ActiveDataFilter.CONFIG['azure_device_inactivity_days']} days)")
        
        return count
    
    @staticmethod
    def mark_inactive_azure_users(db, tenant_id=None):
        """Mark Azure users as inactive if no activity in threshold days"""
        from web.models import AzureUser
        
        threshold_date = datetime.utcnow() - timedelta(
            days=ActiveDataFilter.CONFIG['azure_user_inactivity_days']
        )
        
        # Mark users with last_activity before threshold as inactive
        if tenant_id:
            query = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                AzureUser.last_activity < threshold_date,
                AzureUser.is_active == 1,
                AzureUser.employment_status == 'active'
            )
        else:
            query = AzureUser.query.filter(
                AzureUser.last_activity < threshold_date,
                AzureUser.is_active == 1,
                AzureUser.employment_status == 'active'
            )
        
        count = 0
        for user in query.all():
            user.is_active = 0
            user.employment_status = 'inactive'  # Inactive != terminated (could return)
            count += 1
        
        if count > 0:
            db.session.commit()
            logger.info(f"Marked {count} Azure users as inactive (no activity for {ActiveDataFilter.CONFIG['azure_user_inactivity_days']} days)")
        
        return count
    
    @staticmethod
    def get_active_azure_devices(db, tenant_id=None):
        """Get only ACTIVE Azure devices"""
        from web.models import AzureDevice
        
        query = AzureDevice.query.filter(
            AzureDevice.is_active == 1,
            AzureDevice.device_status == 'active'
        )
        
        if tenant_id:
            query = query.filter(AzureDevice.tenant_id == tenant_id)
        
        return query.all()
    
    @staticmethod
    def get_all_azure_devices_with_status(db, tenant_id=None):
        """Get ALL Azure devices with their status (active, inactive, retired)"""
        from web.models import AzureDevice
        
        query = AzureDevice.query
        if tenant_id:
            query = query.filter(AzureDevice.tenant_id == tenant_id)
        
        return query.order_by(AzureDevice.is_active.desc(), AzureDevice.last_synced.desc()).all()
    
    @staticmethod
    def get_active_azure_users(db, tenant_id=None):
        """Get only ACTIVE Azure users"""
        from web.models import AzureUser
        
        query = AzureUser.query.filter(
            AzureUser.is_active == 1,
            AzureUser.employment_status == 'active'
        )
        
        if tenant_id:
            query = query.filter(AzureUser.tenant_id == tenant_id)
        
        return query.all()
    
    @staticmethod
    def get_all_azure_users_with_status(db, tenant_id=None):
        """Get ALL Azure users with their employment status"""
        from web.models import AzureUser
        
        query = AzureUser.query
        if tenant_id:
            query = query.filter(AzureUser.tenant_id == tenant_id)
        
        return query.order_by(AzureUser.is_active.desc(), AzureUser.last_synced.desc()).all()
    
    @staticmethod
    def get_active_employees(db, tenant_id=None):
        """Get only ACTIVE employees"""
        from web.models import Employee
        
        query = Employee.query.filter(
            Employee.is_active == 1,
            Employee.employment_status == 'active'
        )
        
        if tenant_id:
            query = query.filter(Employee.tenant_id == tenant_id)
        
        return query.all()
    
    @staticmethod
    def get_all_employees_with_status(db, tenant_id=None):
        """Get ALL employees with their employment status"""
        from web.models import Employee
        
        query = Employee.query
        if tenant_id:
            query = query.filter(Employee.tenant_id == tenant_id)
        
        return query.order_by(Employee.is_active.desc()).all()
    
    @staticmethod
    def get_active_servers(db, tenant_id=None):
        """Get only ACTIVE servers"""
        from web.models import Server
        
        query = Server.query.filter(
            Server.device_active_status == 'active'
        )
        
        if tenant_id:
            query = query.filter(Server.tenant_id == tenant_id)
        
        return query.order_by(Server.last_seen.desc().nullslast()).all()
    
    @staticmethod
    def get_device_summary(db, tenant_id=None):
        """Get summary of device statuses: active, inactive, retired"""
        from web.models import AzureDevice
        from sqlalchemy import func
        
        base_query = AzureDevice.query
        if tenant_id:
            base_query = base_query.filter(AzureDevice.tenant_id == tenant_id)
        
        active = base_query.filter(AzureDevice.is_active == 1, AzureDevice.device_status == 'active').count()
        inactive = base_query.filter(AzureDevice.is_active == 0, AzureDevice.device_status == 'inactive').count()
        retired = base_query.filter(AzureDevice.device_status == 'retired').count()
        
        return {
            'active': active,
            'inactive': inactive,
            'retired': retired,
            'total': active + inactive + retired,
        }
    
    @staticmethod
    def get_user_summary(db, tenant_id=None):
        """Get summary of user employment statuses: active, inactive, terminated"""
        from web.models import AzureUser
        
        base_query = AzureUser.query
        if tenant_id:
            base_query = base_query.filter(AzureUser.tenant_id == tenant_id)
        
        active = base_query.filter(AzureUser.is_active == 1, AzureUser.employment_status == 'active').count()
        inactive = base_query.filter(AzureUser.is_active == 0, AzureUser.employment_status == 'inactive').count()
        terminated = base_query.filter(AzureUser.employment_status == 'terminated').count()
        onleave = base_query.filter(AzureUser.employment_status == 'onleave').count()
        
        return {
            'active': active,
            'inactive': inactive,
            'terminated': terminated,
            'onleave': onleave,
            'total': active + inactive + terminated + onleave,
        }
    
    @staticmethod
    def get_inactive_devices_since(db, days=90, tenant_id=None):
        """Get devices that haven't had activity in N days"""
        from web.models import AzureDevice
        
        threshold_date = datetime.utcnow() - timedelta(days=days)
        
        query = AzureDevice.query.filter(
            AzureDevice.last_activity < threshold_date
        )
        
        if tenant_id:
            query = query.filter(AzureDevice.tenant_id == tenant_id)
        
        return query.order_by(AzureDevice.last_activity.desc()).all()
    
    @staticmethod
    def get_inactive_users_since(db, days=120, tenant_id=None):
        """Get users that haven't had activity in N days"""
        from web.models import AzureUser
        
        threshold_date = datetime.utcnow() - timedelta(days=days)
        
        query = AzureUser.query.filter(
            AzureUser.last_activity < threshold_date,
            AzureUser.employment_status == 'active'
        )
        
        if tenant_id:
            query = query.filter(AzureUser.tenant_id == tenant_id)
        
        return query.order_by(AzureUser.last_activity.desc()).all()
    
    @staticmethod
    def mark_device_as_retired(db, device_id):
        """Mark a device as permanently retired"""
        from web.models import AzureDevice
        
        device = db.session.get(AzureDevice, device_id)
        if device:
            device.is_active = 0
            device.device_status = 'retired'
            device.disabled_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Marked device {device.display_name} as retired")
            return True
        return False
    
    @staticmethod
    def mark_user_as_terminated(db, user_id, left_date=None):
        """Mark user employment as terminated"""
        from web.models import AzureUser
        
        user = db.session.get(AzureUser, user_id)
        if user:
            user.is_active = 0
            user.employment_status = 'terminated'
            user.left_date = left_date or datetime.utcnow()
            db.session.commit()
            logger.info(f"Marked user {user.email} as terminated (left: {user.left_date})")
            return True
        return False
