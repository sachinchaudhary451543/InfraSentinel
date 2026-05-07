"""
Employee Asset Detection System
Tracks which devices an employee logs into and registers them automatically
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EmployeeAsset:
    """Represents a device accessed by an employee"""
    def __init__(
        self,
        employee_id: str,
        employee_email: str,
        hostname: str,
        ip_address: Optional[str],
        os_info: Optional[str],
        domain: Optional[str],
        login_timestamp: datetime,
        device_type: str = 'unknown'  # laptop, desktop, server, mobile
    ):
        self.employee_id = employee_id
        self.employee_email = employee_email
        self.hostname = hostname
        self.ip_address = ip_address
        self.os_info = os_info
        self.domain = domain
        self.login_timestamp = login_timestamp
        self.device_type = device_type
        self.last_seen = login_timestamp
        self.login_count = 1


class EmployeeAssetDetector:
    """Detects and registers devices when employees log in"""
    
    def __init__(self, db_session=None):
        """Initialize the detector"""
        self.db_session = db_session
    
    def detect_login_from_agent(self, agent_data: Dict[str, Any]) -> Optional[EmployeeAsset]:
        """
        Detect employee login from agent metrics payload
        
        Expected agent_data structure:
        {
            'agent_key': '...',
            'hostname': '...',
            'ip': '...',
            'os_info': '...',
            'logged_in_user': 'domain\\username' or 'employee@domain.com',
            'metrics': {...}
        }
        """
        try:
            logged_in_user = agent_data.get('logged_in_user')
            if not logged_in_user:
                return None
            
            # Extract employee info
            if '\\' in logged_in_user:
                # Format: DOMAIN\username
                domain, username = logged_in_user.split('\\', 1)
                employee_email = f"{username}@{domain or 'unknown.local'}"
                employee_id = username
            elif '@' in logged_in_user:
                # Format: user@domain.com
                employee_email = logged_in_user
                employee_id = logged_in_user.split('@')[0]
                domain = logged_in_user.split('@')[1]
            else:
                # Fallback: just username
                employee_id = logged_in_user
                employee_email = f"{logged_in_user}@unknown.local"
                domain = 'unknown.local'
            
            # Classify device type based on OS
            device_type = self._classify_device_type(agent_data.get('os_info', ''))
            
            asset = EmployeeAsset(
                employee_id=employee_id,
                employee_email=employee_email,
                hostname=agent_data.get('hostname', 'unknown'),
                ip_address=agent_data.get('ip'),
                os_info=agent_data.get('os_info'),
                domain=domain,
                login_timestamp=datetime.utcnow(),
                device_type=device_type
            )
            
            logger.info(
                f"Detected employee login: {employee_email} on {asset.hostname} "
                f"({device_type}) from {agent_data.get('ip')}"
            )
            
            return asset
        
        except Exception as e:
            logger.error(f"Error detecting employee login: {e}")
            return None
    
    def register_employee_asset(self, asset: EmployeeAsset, tenant_id: int) -> bool:
        """Register or update an employee asset in the database"""
        if not self.db_session:
            logger.warning("No database session available for registering asset")
            return False
        
        try:
            from web.models import Server, EmployeeAssetLog
            
            # 1. Find or create the server
            server = Server.query.filter_by(
                hostname=asset.hostname,
                tenant_id=tenant_id
            ).first()
            
            if not server:
                server = Server(
                    hostname=asset.hostname,
                    tenant_id=tenant_id,
                    ip=asset.ip_address,
                    os_info=asset.os_info,
                    status='online'
                )
                self.db_session.add(server)
                self.db_session.flush()
                logger.info(f"Created server record for {asset.hostname}")
            
            server.ip = asset.ip_address or server.ip
            server.os_info = asset.os_info or server.os_info
            server.status = 'online'
            server.last_heartbeat = asset.login_timestamp
            
            # 2. Log the employee asset login
            asset_log = EmployeeAssetLog(
                server_id=server.id,
                tenant_id=tenant_id,
                employee_id=asset.employee_id,
                employee_email=asset.employee_email,
                hostname=asset.hostname,
                ip_address=asset.ip_address,
                os_info=asset.os_info,
                domain=asset.domain,
                device_type=asset.device_type,
                login_timestamp=asset.login_timestamp
            )
            self.db_session.add(asset_log)
            
            self.db_session.commit()
            
            logger.info(
                f"Registered asset: {asset.employee_email} -> {asset.hostname} "
                f"(Server ID: {server.id}, Asset Log ID: {asset_log.id})"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error registering employee asset: {e}")
            self.db_session.rollback() if self.db_session else None
            return False
    
    @staticmethod
    def _classify_device_type(os_info: str) -> str:
        """Classify device type based on OS information"""
        if not os_info:
            return 'unknown'
        
        os_lower = os_info.lower()
        
        if 'server' in os_lower or 'windows server' in os_lower:
            return 'server'
        elif 'windows 10' in os_lower or 'windows 11' in os_lower:
            return 'desktop'
        elif 'ubuntu' in os_lower or 'debian' in os_lower or 'centos' in os_lower:
            return 'server'
        elif 'macos' in os_lower or 'darwin' in os_lower:
            return 'laptop'
        elif 'mobile' in os_lower or 'android' in os_lower or 'ios' in os_lower:
            return 'mobile'
        elif 'windows' in os_lower:
            return 'laptop'
        elif 'linux' in os_lower:
            return 'server'
        else:
            return 'unknown'
    
    def get_employee_assets(self, tenant_id: int, employee_email: Optional[str] = None):
        """Get all assets (devices) used by an employee"""
        if not self.db_session:
            return []
        
        try:
            from web.models import EmployeeAssetLog
            
            query = EmployeeAssetLog.query.filter_by(tenant_id=tenant_id)
            
            if employee_email:
                query = query.filter_by(employee_email=employee_email)
            
            assets = query.order_by(EmployeeAssetLog.login_timestamp.desc()).all()
            
            return assets
        
        except Exception as e:
            logger.error(f"Error querying employee assets: {e}")
            return []
    
    def get_employees_logged_in_device(self, tenant_id: int, hostname: str):
        """Get all employees who have logged into a specific device"""
        if not self.db_session:
            return []
        
        try:
            from web.models import EmployeeAssetLog
            
            assets = EmployeeAssetLog.query.filter_by(
                tenant_id=tenant_id,
                hostname=hostname
            ).order_by(EmployeeAssetLog.login_timestamp.desc()).all()
            
            return assets
        
        except Exception as e:
            logger.error(f"Error querying device logins: {e}")
            return []
