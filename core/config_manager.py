"""
Config Manager - Secure configuration storage with encryption
"""

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manage encrypted configuration storage for enterprise deployments"""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize config manager
        
        Args:
            config_dir: Directory to store configs (default: ./data/config)
        """
        self.config_dir = Path(config_dir or os.path.join(os.path.dirname(__file__), '..', 'data', 'config'))
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.key_file = self.config_dir / '.encryption.key'
        self.config_file = self.config_dir / 'enterprise.cfg'
        
        self._cipher = self._init_cipher()
    
    def _init_cipher(self) -> Fernet:
        """Initialize or load encryption cipher"""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            os.chmod(str(self.key_file), 0o600)  # Read-only by owner
        
        return Fernet(key)
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        Encrypt and save configuration
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if successful
        """
        try:
            json_data = json.dumps(config, indent=2)
            encrypted_data = self._cipher.encrypt(json_data.encode())
            
            with open(self.config_file, 'wb') as f:
                f.write(encrypted_data)
            
            os.chmod(str(self.config_file), 0o600)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    def load_config(self) -> Optional[Dict[str, Any]]:
        """
        Decrypt and load configuration
        
        Returns:
            Configuration dictionary or None if not found
        """
        if not self.config_file.exists():
            logger.warning(f"Config file not found: {self.config_file}")
            return None
        
        try:
            with open(self.config_file, 'rb') as f:
                encrypted_data = f.read()
            
            json_data = self._cipher.decrypt(encrypted_data).decode()
            return json.loads(json_data)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return None
    
    def get_credential(self, key: str) -> Optional[Any]:
        """Get a specific credential from config"""
        config = self.load_config()
        if not config:
            return None
        
        keys = key.split('.')
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        
        return value
    
    def set_credential(self, key: str, value: str) -> bool:
        """Set a specific credential in config"""
        config = self.load_config() or {}
        
        keys = key.split('.')
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        return self.save_config(config)


# Default config structure for enterprise deployment
DEFAULT_ENTERPRISE_CONFIG = {
    "tenant": {
        "id": None,
        "name": None,
        "azure_tenant_id": None,
    },
    "authentication": {
        "oauth_enabled": False,
        "oauth_token": None,
        "oauth_refresh_token": None,
        "oauth_expires_at": None,
    },
    "sharepoint": {
        "site_url": None,
        "library": "ServerMonitor",
        "lists": {
            "systems_registry": "SystemsRegistry",
            "metrics": "SystemMetrics",
            "alerts": "Alerts",
            "deployments": "DeploymentJobs",
            "agent_control": "AgentControl",
        }
    },
    "agent": {
        "id": None,
        "name": None,
        "key": None,
        "enabled": True,
        "heartbeat_interval": 300,  # 5 minutes
        "offline_buffer_enabled": True,
    },
    "deployment": {
        "temp_dir": "./data/deployments",
        "check_interval": 300,  # 5 minutes
    },
    "monitoring": {
        "collect_interval": 300,  # 5 minutes
        "high_cpu_threshold": 90,
        "low_disk_threshold": 10,  # GB
        "low_ram_threshold": 20,  # %
    },
}
