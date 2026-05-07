"""
Admin Portal Configuration
Centralized configuration management
"""

import os
from datetime import timedelta

# Flask Configuration
class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Security
    CORS_HEADERS = 'Content-Type'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development
    SQLALCHEMY_ECHO = True
    
    # Database
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(os.path.dirname(__file__), "instance", "admin_portal.db")}'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Database - Use environment variable
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///admin_portal.db')
    
    # Security settings
    PREFERRED_URL_SCHEME = 'https'
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    
    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Portal-specific settings
class PortalSettings:
    """Portal-specific settings and constants"""
    
    # UI Settings
    ITEMS_PER_PAGE = 20
    SYSTEM_STATUS_TIMEOUT = 120  # seconds
    COMMAND_EXECUTION_TIMEOUT = 300  # seconds
    
    # Metrics
    METRICS_RETENTION_DAYS = 30
    METRICS_CLEANUP_INTERVAL = 7  # days
    METRICS_UPDATE_INTERVAL = 30  # seconds
    
    # Commands
    COMMAND_RETENTION_DAYS = 60
    COMMAND_CLEANUP_INTERVAL = 7  # days
    MAX_COMMAND_OUTPUT_SIZE = 100000  # characters
    
    # Agent
    AGENT_KEY_LENGTH = 32
    AGENT_HEARTBEAT_INTERVAL = 30  # seconds
    AGENT_OFFLINE_THRESHOLD = 120  # seconds
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Features (can be toggled)
    FEATURES = {
        'real_time_metrics': True,
        'command_execution': True,
        'domain_discovery': True,
        'agent_management': True,
        'multi_tenant': True,
        'audit_logging': True,
        'performance_monitoring': True,
        'alert_system': False,  # Coming soon
    }
    
    # Color scheme
    COLORS = {
        'primary': '#3B82F6',
        'secondary': '#8B5CF6',
        'success': '#10B981',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'info': '#06B6D4',
    }
    
    # API settings
    API_VERSION = 'v2'
    API_TIMEOUT = 30  # seconds
    API_RATE_LIMIT = '100/hour'


def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    
    return configs.get(env, DevelopmentConfig)
