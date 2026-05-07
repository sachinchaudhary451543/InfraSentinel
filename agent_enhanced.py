"""
PHASE 13: Enhanced Agent with Heartbeat, Retry, and Structured Logging
- 30-second heartbeat pings
- Automatic offline detection
- Retry failed API calls (3 attempts, exponential backoff)
- Comprehensive structured logging
- Command validation before execution
"""

import time
import requests
import psutil
import platform
import socket
import logging
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any
import subprocess
import hashlib

# ============================================================================
# PHASE 15: STRUCTURED LOGGING
# ============================================================================

class StructuredLogger:
    """Structured logging with JSON output and file rotation"""
    
    def __init__(self, name: str, log_file: str = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with JSON formatting
        if log_file:
            import os
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)
    
    def log_event(self, level: str, event: str, **context):
        """Log structured event with context"""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "hostname": socket.gethostname(),
            **context
        }
        message = json.dumps(data)
        
        if level.upper() == "INFO":
            self.logger.info(message)
        elif level.upper() == "ERROR":
            self.logger.error(message)
        elif level.upper() == "WARNING":
            self.logger.warning(message)
        elif level.upper() == "DEBUG":
            self.logger.debug(message)

# Initialize logger
logger = StructuredLogger(
    "ServerMonitor-Agent",
    log_file="logs/agent.log"
)

# ============================================================================
# PHASE 12 & 13: CONFIG & AGENT SETTINGS
# ============================================================================

class AgentConfig:
    """Configuration management with environment variable support"""
    
    # API Configuration
    SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080").rstrip('/')
    AGENT_KEY = os.environ.get("AGENT_KEY", "demo_mode_key")
    AGENT_ID = os.environ.get("AGENT_ID", socket.gethostname())
    
    # Timing
    METRICS_INTERVAL = int(os.environ.get("METRICS_INTERVAL", "30"))  # seconds
    HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))  # seconds
    COMMAND_POLL_INTERVAL = int(os.environ.get("COMMAND_POLL_INTERVAL", "15"))  # seconds
    
    # Retry strategy (exponential backoff)
    MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
    RETRY_DELAY = float(os.environ.get("RETRY_DELAY", "1.0"))  # seconds
    RETRY_BACKOFF = float(os.environ.get("RETRY_BACKOFF", "2.0"))  # multiplier
    
    # Timeouts
    REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "10"))
    COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "60"))
    
    # Security
    REQUIRE_HTTPS = os.environ.get("REQUIRE_HTTPS", "false").lower() == "true"
    VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() == "true"


os = __import__('os')


class RetryStrategy:
    """Exponential backoff retry mechanism"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, backoff: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff = backoff
    
    def execute(self, func, *args, **kwargs):
        """Execute function with retries"""
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.log_event("INFO", "retry_attempt", 
                    attempt=attempt, 
                    max_retries=self.max_retries,
                    function=func.__name__)
                
                return func(*args, **kwargs)
            
            except requests.RequestException as e:
                last_error = e
                
                if attempt < self.max_retries:
                    delay = self.base_delay * (self.backoff ** (attempt - 1))
                    logger.log_event("WARNING", "retry_wait",
                        attempt=attempt,
                        delay_seconds=delay,
                        error=str(e))
                    time.sleep(delay)
                else:
                    logger.log_event("ERROR", "retry_exhausted",
                        total_attempts=self.max_retries,
                        error=str(last_error))
        
        raise last_error


# ============================================================================
# PHASE 14: COMMAND VALIDATION & SECURITY
# ============================================================================

class CommandValidator:
    """Validate and sanitize commands before execution"""
    
    # Blocked command patterns (security)
    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",      # rm -rf /
        r"mkfs",                # Format filesystem
        r"dd\s+if=",           # Direct disk write
        r":\(\)",              # Bash fork bomb
        r">&\s*\/dev\/zero",   # Null infinite write
    ]
    
    # Blocked executables
    BLOCKED_EXECUTABLES = [
        "format.exe", "diskpart.exe",  # Windows disk format
        "shutdown.exe", "halt",         # Shutdown commands
    ]
    
    @staticmethod
    def validate(command: str) -> bool:
        """Check if command is safe to execute"""
        import re
        
        # Check dangerous patterns
        for pattern in CommandValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                logger.log_event("ERROR", "dangerous_command_blocked",
                    pattern=pattern, 
                    command_hash=hashlib.sha256(command.encode()).hexdigest())
                return False
        
        # Check blocked executables
        cmd_lower = command.lower()
        for blocked in CommandValidator.BLOCKED_EXECUTABLES:
            if blocked in cmd_lower:
                logger.log_event("ERROR", "blocked_executable",
                    executable=blocked,
                    command_hash=hashlib.sha256(command.encode()).hexdigest())
                return False
        
        logger.log_event("INFO", "command_validated",
            command_length=len(command))
        return True


# ============================================================================
# SYSTEM METRICS COLLECTION
# ============================================================================

class SystemMetricsCollector:
    """Collect system metrics using psutil"""
    
    @staticmethod
    def collect() -> Dict[str, Any]:
        """Collect comprehensive system metrics"""
        hostname = socket.gethostname()
        os_info = f"{platform.system()} {platform.release()}"
        
        try:
            ip = socket.gethostbyname(hostname)
        except:
            ip = "127.0.0.1"
        
        # Logged-in User (for employee asset detection)
        logged_in_user = None
        try:
            import getpass
            username = getpass.getuser()
            # Uncomment next line to format as email:
            # logged_in_user = f"{username}@company.com"
            logged_in_user = username
        except Exception as e:
            logger.log_event("WARNING", "failed_to_get_user", error=str(e))
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        total_ram_gb = round(mem.total / (1024**3), 2)
        used_ram_gb = round(mem.used / (1024**3), 2)
        
        # Disk metrics
        try:
            disk = psutil.disk_usage('/')
        except:
            disk = psutil.disk_usage('C:\\')
        
        disk_percent = disk.percent
        total_disk_gb = round(disk.total / (1024**3), 2)
        used_disk_gb = round(disk.used / (1024**3), 2)
        
        # Network (optional)
        try:
            net_io = psutil.net_io_counters()
            net_bytes_sent = net_io.bytes_sent
            net_bytes_recv = net_io.bytes_recv
        except:
            net_bytes_sent = 0
            net_bytes_recv = 0
        
        # Process count
        process_count = len(psutil.pids())
        
        payload = {
            "agent_key": AgentConfig.AGENT_KEY,
            "agent_id": AgentConfig.AGENT_ID,
            "hostname": hostname,
            "os_info": os_info,
            "ip": ip,
            "logged_in_user": logged_in_user,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "ram_percent": ram_percent,
                "total_ram_gb": total_ram_gb,
                "used_ram_gb": used_ram_gb,
                "disk_percent": disk_percent,
                "total_disk_gb": total_disk_gb,
                "used_disk_gb": used_disk_gb,
                "net_bytes_sent": net_bytes_sent,
                "net_bytes_recv": net_bytes_recv,
                "process_count": process_count
            }
        }
        
        return payload


# ============================================================================
# AGENT CORE
# ============================================================================

class EnhancedAgent:
    """Enhanced agent with heartbeat, retries, and validation"""
    
    def __init__(self):
        self.config = AgentConfig
        self.retry_strategy = RetryStrategy(
            max_retries=self.config.MAX_RETRIES,
            base_delay=self.config.RETRY_DELAY,
            backoff=self.config.RETRY_BACKOFF
        )
        self.validator = CommandValidator
        self.is_running = False
        self.last_heartbeat = datetime.utcnow()
        
        logger.log_event("INFO", "agent_initialized",
            agent_id=self.config.AGENT_ID,
            server_url=self.config.SERVER_URL)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        return {
            'X-Agent-Key': self.config.AGENT_KEY,
            'X-Agent-ID': self.config.AGENT_ID,
            'X-Hostname': socket.gethostname(),
            'Content-Type': 'application/json'
        }
    
    def send_heartbeat(self) -> bool:
        """Send heartbeat ping to server (PHASE 13)"""
        payload = {
            "agent_id": self.config.AGENT_ID,
            "hostname": socket.gethostname(),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "online"
        }
        
        def _send():
            url = f"{self.config.SERVER_URL}/api/v2/agent/heartbeat"
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.config.REQUEST_TIMEOUT,
                verify=self.config.VERIFY_SSL
            )
            resp.raise_for_status()
            return True
        
        try:
            self.retry_strategy.execute(_send)
            self.last_heartbeat = datetime.utcnow()
            logger.log_event("DEBUG", "heartbeat_sent")
            return True
        except Exception as e:
            logger.log_event("ERROR", "heartbeat_failed", error=str(e))
            return False
    
    def push_metrics(self) -> bool:
        """Push system metrics to server"""
        metrics = SystemMetricsCollector.collect()
        
        def _push():
            url = f"{self.config.SERVER_URL}/api/v2/agent/metrics"
            resp = requests.post(
                url,
                json=metrics,
                timeout=self.config.REQUEST_TIMEOUT,
                verify=self.config.VERIFY_SSL
            )
            resp.raise_for_status()
            return resp
        
        try:
            response = self.retry_strategy.execute(_push)
            cpu = metrics['metrics']['cpu_percent']
            ram = metrics['metrics']['ram_percent']
            logger.log_event("INFO", "metrics_pushed",
                cpu_percent=cpu,
                ram_percent=ram)
            return True
        except Exception as e:
            logger.log_event("ERROR", "metrics_push_failed", error=str(e))
            return False
    
    def fetch_and_execute_commands(self) -> int:
        """Poll for pending commands and execute them"""
        executed = 0
        
        def _fetch():
            url = f"{self.config.SERVER_URL}/api/v2/agent/commands"
            resp = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.config.REQUEST_TIMEOUT,
                verify=self.config.VERIFY_SSL
            )
            resp.raise_for_status()
            return resp.json()
        
        try:
            commands = self.retry_strategy.execute(_fetch)
            
            for cmd in commands:
                if self._execute_command(cmd):
                    executed += 1
            
            return executed
        
        except Exception as e:
            logger.log_event("ERROR", "command_fetch_failed", error=str(e))
            return 0
    
    def _execute_command(self, cmd: Dict[str, Any]) -> bool:
        """Execute single command with validation (PHASE 14)"""
        command_id = cmd.get('command_id')
        command_str = cmd.get('command', '')
        parameters = cmd.get('parameters', '')
        
        if parameters:
            command_str += " " + parameters
        
        # Validate command (PHASE 14: Security)
        if not self.validator.validate(command_str):
            logger.log_event("ERROR", "command_rejected",
                command_id=command_id,
                reason="validation_failed")
            self._report_command_result(command_id, "", "rejected_blocked", "Dangerous command blocked")
            return False
        
        logger.log_event("INFO", "executing_command",
            command_id=command_id,
            timeout_seconds=self.config.COMMAND_TIMEOUT)
        
        try:
            # Execute with appropriate shell
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["powershell", "-Command", command_str],
                    capture_output=True,
                    text=True,
                    timeout=self.config.COMMAND_TIMEOUT
                )
            else:
                result = subprocess.run(
                    command_str,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.config.COMMAND_TIMEOUT
                )
            
            output = result.stdout + result.stderr
            status = 'completed' if result.returncode == 0 else 'failed'
            
            logger.log_event("INFO", "command_executed",
                command_id=command_id,
                status=status,
                return_code=result.returncode)
            
            self._report_command_result(command_id, output, status)
            return status == 'completed'
        
        except subprocess.TimeoutExpired:
            logger.log_event("ERROR", "command_timeout",
                command_id=command_id,
                timeout_seconds=self.config.COMMAND_TIMEOUT)
            self._report_command_result(
                command_id, 
                "", 
                'failed', 
                f"Command timeout after {self.config.COMMAND_TIMEOUT}s"
            )
            return False
        
        except Exception as e:
            logger.log_event("ERROR", "command_execution_error",
                command_id=command_id,
                error=str(e))
            self._report_command_result(command_id, "", 'failed', str(e))
            return False
    
    def _report_command_result(self, command_id: str, output: str, status: str, error: str = ""):
        """Report command execution result to server"""
        payload = {
            'command_id': command_id,
            'output': output[:10000],  # Limit output size
            'status': status,
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        def _report():
            url = f"{self.config.SERVER_URL}/api/v2/agent/commands/result"
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.config.REQUEST_TIMEOUT,
                verify=self.config.VERIFY_SSL
            )
            resp.raise_for_status()
        
        try:
            self.retry_strategy.execute(_report)
        except Exception as e:
            logger.log_event("ERROR", "result_report_failed",
                command_id=command_id,
                error=str(e))
    
    def run(self):
        """Main agent loop"""
        self.is_running = True
        logger.log_event("INFO", "agent_started",
            agent_id=self.config.AGENT_ID,
            hostname=socket.gethostname())
        
        heartbeat_counter = 0
        
        try:
            while self.is_running:
                # Heartbeat every 30 seconds (PHASE 13)
                if heartbeat_counter % (self.config.HEARTBEAT_INTERVAL // self.config.METRICS_INTERVAL) == 0:
                    self.send_heartbeat()
                
                # Push metrics
                self.push_metrics()
                
                # Poll commands
                executed = self.fetch_and_execute_commands()
                if executed > 0:
                    logger.log_event("INFO", "commands_processed", count=executed)
                
                heartbeat_counter += 1
                time.sleep(self.config.METRICS_INTERVAL)
        
        except KeyboardInterrupt:
            logger.log_event("INFO", "agent_shutdown", reason="user_interrupt")
        except Exception as e:
            logger.log_event("ERROR", "agent_fatal_error", error=str(e))
            raise


def main():
    """Entry point"""
    agent = EnhancedAgent()
    agent.run()


if __name__ == "__main__":
    main()
