"""
Utility functions for the admin portal
"""

import logging
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

logger = logging.getLogger(__name__)


def require_tenant_access(f):
    """Decorator to ensure user has access to requested tenant"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from admin_portal.models import Tenant
        tenant_id = kwargs.get('tenant_id')
        
        if not tenant_id:
            flash('Tenant ID required', 'error')
            return redirect(url_for('main.dashboard'))
        
        if current_user.tenant_id != int(tenant_id) and not current_user.is_superadmin:
            flash('Access denied to this tenant', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_superadmin(f):
    """Decorator to require superadmin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_superadmin:
            flash('This action requires superadmin privileges', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


class APIResponse:
    """Consistent API response format"""
    
    @staticmethod
    def success(data=None, message='Success', status_code=200):
        """Return successful API response"""
        return {
            'status': 'success',
            'message': message,
            'data': data
        }, status_code
    
    @staticmethod
    def error(message='Error', status_code=400, errors=None):
        """Return error API response"""
        return {
            'status': 'error',
            'message': message,
            'errors': errors or {}
        }, status_code
    
    @staticmethod
    def paginated(items, total, page, per_page):
        """Return paginated API response"""
        return {
            'status': 'success',
            'data': items,
            'pagination': {
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }
        }, 200


def log_action(action, resource_type, resource_id, details=None):
    """Log admin actions for audit trail"""
    try:
        log_entry = f"[{action}] {resource_type} #{resource_id}"
        if details:
            log_entry += f" - {details}"
        logger.info(log_entry)
    except Exception as e:
        logger.error(f"Failed to log action: {e}")


def format_bytes(bytes_value):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def format_uptime(seconds):
    """Format seconds to human readable uptime"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"


def validate_hostname(hostname):
    """Validate hostname format"""
    import re
    pattern = r'^(?!-)(?:[a-zA-Z0-9-]{{1,63}}(?<!-)\.)*[a-zA-Z0-9]{{1,63}}$'
    return bool(re.match(pattern, hostname))


def validate_ip_address(ip):
    """Validate IP address"""
    import re
    # IPv4 validation
    ipv4_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    return bool(re.match(ipv4_pattern, ip))


def sanitize_command(command):
    """Basic command sanitization"""
    # Remove potentially dangerous characters
    dangerous_chars = ['`', '$', '$(', '&', ';', '|', '<', '>', '\n']
    for char in dangerous_chars:
        command = command.replace(char, '')
    return command.strip()


class PaginationHelper:
    """Helper for pagination"""
    
    def __init__(self, items, page, per_page):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = len(items)
    
    def get_items(self):
        """Get items for current page"""
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        return self.items[start:end]
    
    def get_pages(self):
        """Get total number of pages"""
        return (self.total + self.per_page - 1) // self.per_page
    
    def has_previous(self):
        """Check if previous page exists"""
        return self.page > 1
    
    def has_next(self):
        """Check if next page exists"""
        return self.page < self.get_pages()


class AlertHelper:
    """Helper for creating alerts/notifications"""
    
    @staticmethod
    def create_alert(title, message, alert_type='info', dismissible=True):
        """Create alert object"""
        return {
            'title': title,
            'message': message,
            'type': alert_type,
            'dismissible': dismissible
        }
    
    @staticmethod
    def success(title, message):
        """Create success alert"""
        return AlertHelper.create_alert(title, message, 'success')
    
    @staticmethod
    def error(title, message):
        """Create error alert"""
        return AlertHelper.create_alert(title, message, 'error')
    
    @staticmethod
    def warning(title, message):
        """Create warning alert"""
        return AlertHelper.create_alert(title, message, 'warning')


if __name__ == '__main__':
    # Test utilities
    print(format_bytes(1024000))  # Should print ~1000 KB
    print(format_uptime(3661))    # Should print 1h 1m
    print(validate_hostname('test-server.example.com'))  # Should be True
    print(validate_ip_address('192.168.1.1'))  # Should be True
