"""
PHASE 14 & 17: Security Middleware and Rate Limiting
- Input validation and sanitization
- Rate limiting per IP/user
- CORS configuration
- Security headers
"""

import os
import logging
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis

logger = logging.getLogger("ServerMonitor-Security")

# ============================================================================
# REDIS & RATE LIMITING
# ============================================================================

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1")
REDIS_CONN = Redis.from_url(REDIS_URL)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["200 per day", "50 per hour"]
)


# ============================================================================
# PHASE 14: INPUT VALIDATION & SANITIZATION
# ============================================================================

class InputValidator:
    """Validates and sanitizes user input"""
    
    # SQL Injection patterns
    SQL_PATTERNS = [
        r"'.*OR.*'",
        r".*--.*",
        r".*;.*DROP.*",
        r".*UNION.*SELECT.*",
        r".*xp_.*",
        r".*sp_.*"
    ]
    
    # XSS patterns
    XSS_PATTERNS = [
        r"<script.*>.*</script>",
        r"javascript:",
        r"onerror=",
        r"onclick=",
        r"<iframe",
        r"<object",
        r"<embed"
    ]
    
    # Path traversal
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.",
        r"\.\.\\",
        r"%2e%2e"
    ]
    
    @staticmethod
    def validate_string(value: str, field_name: str, max_length: int = 1000) -> tuple[bool, str]:
        """Validate string input"""
        import re
        
        if not isinstance(value, str):
            return False, f"{field_name} must be string"
        
        if len(value) > max_length:
            return False, f"{field_name} exceeds max length {max_length}"
        
        # Check SQL injection
        for pattern in InputValidator.SQL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"SQL injection attempt in {field_name}: {value[:50]}")
                return False, f"{field_name} contains invalid characters"
        
        # Check XSS
        for pattern in InputValidator.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"XSS attempt in {field_name}: {value[:50]}")
                return False, f"{field_name} contains invalid HTML"
        
        # Check path traversal
        for pattern in InputValidator.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"Path traversal attempt in {field_name}: {value}")
                return False, f"{field_name} contains invalid path"
        
        return True, ""
    
    @staticmethod
    def validate_hostname(hostname: str) -> tuple[bool, str]:
        """Validate hostname"""
        import re
        
        # RFC 1123 hostname validation
        if len(hostname) > 255:
            return False, "Hostname too long"
        
        pattern = r'^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.[a-zA-Z0-9-]{1,63})*\.?$'
        if not re.match(pattern, hostname):
            return False, "Invalid hostname format"
        
        return True, ""
    
    @staticmethod
    def validate_ip(ip: str) -> tuple[bool, str]:
        """Validate IP address"""
        import re
        
        ipv4_pattern = r'^((25[0-5]|(2[0-4]|1\d)?[0-9]?)\.?\b){4}$'
        ipv6_pattern = r'^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4})$'
        
        if not (re.match(ipv4_pattern, ip) or re.match(ipv6_pattern, ip)):
            return False, "Invalid IP address"
        
        return True, ""


# ============================================================================
# PHASE 14: DECORATORS FOR API PROTECTION
# ============================================================================

def validate_json() -> callable:
    """Validate request JSON"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Request must be JSON"}), 400
            
            try:
                request.get_json()
            except Exception as e:
                logger.warning(f"Invalid JSON in request: {e}")
                return jsonify({"error": "Invalid JSON"}), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_auth_header() -> callable:
    """Require API key authentication"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = request.headers.get('X-Agent-Key')
            if not key:
                logger.warning(f"Missing auth key from {request.remote_addr}")
                return jsonify({"error": "Unauthorized"}), 401
            
            # Validate key exists and is active
            from web.models import AgentKey
            agent_key = AgentKey.query.filter_by(key=key, is_active=True).first()
            
            if not agent_key:
                logger.warning(f"Invalid auth key attempt from {request.remote_addr}")
                return jsonify({"error": "Unauthorized"}), 401
            
            # Store in request context
            g.agent_key = agent_key
            g.tenant_id = agent_key.tenant_id
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_request_fields(required_fields: list) -> callable:
    """Validate request has required fields"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.get_json() or {}
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                return jsonify({"error": f"Missing fields: {missing}"}), 400
            
            # Validate fields
            for field in required_fields:
                is_valid, error = InputValidator.validate_string(
                    str(data[field]), 
                    field
                )
                if not is_valid:
                    return jsonify({"error": error}), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# PHASE 17: SECURITY HEADERS MIDDLEWARE
# ============================================================================

def add_security_headers(app):
    """Add security headers to all responses"""
    
    @app.after_request
    def set_security_headers(response):
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Enable XSS filter
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # CSP
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "font-src 'self' fonts.googleapis.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        
        # HSTS (if HTTPS is enforced)
        if os.environ.get("REQUIRE_HTTPS") == "true":
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains; preload'
            )
        
        return response


# ============================================================================
# PHASE 17: CORS CONFIGURATION
# ============================================================================

def setup_cors(app):
    """Configure CORS for API"""
    from flask_cors import CORS
    
    CORS(app, resources={
        r"/api/*": {
            "origins": os.environ.get("CORS_ORIGINS", "*").split(","),
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": ["Content-Type", "X-Agent-Key"],
            "max_age": 3600
        }
    })


# ============================================================================
# PHASE 14: RATE LIMITING RULES
# ============================================================================

def setup_rate_limits(app):
    """Configure rate limits for endpoints"""
    
    # Agent metrics endpoint - allow more frequent
    app.add_url_rule(
        "/api/v2/agent/metrics",
        "agent_metrics",
        view_func=limiter.limit("600 per hour")(lambda: None)
    )
    
    # Login endpoint - strict limit
    app.add_url_rule(
        "/login",
        "login",
        view_func=limiter.limit("5 per minute")(lambda: None)
    )
    
    # API endpoints - moderate limit
    app.add_url_rule(
        "/api/*",
        "api_calls",
        view_func=limiter.limit("100 per minute")(lambda: None)
    )
    
    # General limit for all requests
    limiter.limit("200 per day")(app)


# ============================================================================
# PHASE 15: REQUEST LOGGING MIDDLEWARE
# ============================================================================

def setup_request_logging(app):
    """Log all requests for audit trail"""
    
    @app.before_request
    def log_request():
        g.request_start = datetime.utcnow()
        # Store request info for later logging
        g.request_info = {
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", "Unknown"),
            "timestamp": g.request_start.isoformat()
        }
        
        # Log request to structured format
        logger.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")
    
    @app.after_request
    def log_response(response):
        if hasattr(g, 'request_start'):
            duration = (datetime.utcnow() - g.request_start).total_seconds()
            
            request_log = {
                **g.request_info,
                "status_code": response.status_code,
                "duration_seconds": duration
            }
            
            # Log slow requests
            if duration > 1.0:
                logger.warning(f"Slow request: {duration:.2f}s | {request_log}")
            else:
                logger.debug(f"Response: {response.status_code} | {duration:.2f}s")
        
        return response
