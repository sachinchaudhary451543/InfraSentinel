"""
Auto-Heal Engine - Intelligent issue detection and automatic remediation

Monitors system health and automatically triggers fixes for common issues:
- High CPU
- Low disk space
- Low memory
- Service failures
"""

import logging
import subprocess
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class IssueType(Enum):
    """Types of system issues that can be detected"""
    HIGH_CPU = "HighCPU"
    LOW_DISK = "LowDisk"
    LOW_MEMORY = "LowMemory"
    SERVICE_DOWN = "ServiceDown"
    NETWORK_UNREACHABLE = "NetworkUnreachable"
    PROCESS_CRASH = "ProcessCrash"


class RemediationAction(Enum):
    """Automatic remediation actions"""
    KILL_PROCESS = "KillProcess"
    RESTART_SERVICE = "RestartService"
    CLEANUP_TEMP = "CleanupTemp"
    CLEAR_CACHE = "ClearCache"
    RESTART_SYSTEM = "RestartSystem"
    ALERT_ONLY = "AlertOnly"


@dataclass
class HealthIssue:
    """Represents a detected system health issue"""
    issue_type: IssueType
    severity: str  # critical, high, medium, low
    message: str
    detected_at: str
    affected_resource: Optional[str] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    recommended_action: Optional[RemediationAction] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity,
            "message": self.message,
            "detected_at": self.detected_at,
            "affected_resource": self.affected_resource,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "recommended_action": self.recommended_action.value if self.recommended_action else None,
        }


class AutoHealEngine:
    """
    Intelligent auto-healing system for enterprise monitoring
    """
    
    def __init__(self, config: Dict[str, Any], remote_executor: Optional[Any] = None):
        """
        Initialize auto-heal engine
        
        Args:
            config: System configuration
            remote_executor: RemoteExecutor instance for executing fixes
        """
        self.config = config
        self.remote_executor = remote_executor
        
        # Load thresholds from config
        monitoring_config = config.get('monitoring', {})
        self.high_cpu_threshold = monitoring_config.get('high_cpu_threshold', 90)
        self.low_disk_threshold = monitoring_config.get('low_disk_threshold', 10)  # GB
        self.low_ram_threshold = monitoring_config.get('low_ram_threshold', 20)  # %
        
        # Issue history
        self.detected_issues: List[HealthIssue] = []
        self.remediated_issues: List[HealthIssue] = []
    
    def check_system_health(self, metrics: Dict[str, Any]) -> List[HealthIssue]:
        """
        Check system health based on metrics
        
        Args:
            metrics: Collected system metrics
            
        Returns:
            List of detected issues
        """
        issues = []
        timestamp = datetime.utcnow().isoformat()
        
        # Extract metrics
        collectors = metrics.get('collectors', {})
        
        # Check CPU usage
        cpu_metrics = collectors.get('cpu', {})
        if cpu_metrics and 'usage_percent' in cpu_metrics:
            cpu_usage = cpu_metrics['usage_percent']
            if cpu_usage > self.high_cpu_threshold:
                issues.append(HealthIssue(
                    issue_type=IssueType.HIGH_CPU,
                    severity="high" if cpu_usage > 95 else "medium",
                    message=f"CPU usage is {cpu_usage}% (threshold: {self.high_cpu_threshold}%)",
                    detected_at=timestamp,
                    current_value=cpu_usage,
                    threshold=self.high_cpu_threshold,
                    recommended_action=RemediationAction.KILL_PROCESS
                ))
        
        # Check disk space
        disk_metrics = collectors.get('disk', {})
        if disk_metrics and 'available_gb' in disk_metrics:
            available_gb = disk_metrics['available_gb']
            if available_gb < self.low_disk_threshold:
                issues.append(HealthIssue(
                    issue_type=IssueType.LOW_DISK,
                    severity="critical" if available_gb < 5 else "high",
                    message=f"Low disk space: {available_gb}GB available (threshold: {self.low_disk_threshold}GB)",
                    detected_at=timestamp,
                    affected_resource=disk_metrics.get('drive', 'C:'),
                    current_value=available_gb,
                    threshold=self.low_disk_threshold,
                    recommended_action=RemediationAction.CLEANUP_TEMP
                ))
        
        # Check memory
        memory_metrics = collectors.get('memory', {})
        if memory_metrics and 'used_percent' in memory_metrics:
            memory_used = memory_metrics['used_percent']
            if memory_used > (100 - self.low_ram_threshold):
                issues.append(HealthIssue(
                    issue_type=IssueType.LOW_MEMORY,
                    severity="high",
                    message=f"Low memory: {memory_used}% used (threshold: {100 - self.low_ram_threshold}%)",
                    detected_at=timestamp,
                    current_value=memory_used,
                    threshold=100 - self.low_ram_threshold,
                    recommended_action=RemediationAction.ALERT_ONLY
                ))
        
        # Store detected issues
        self.detected_issues.extend(issues)
        
        return issues
    
    def remediate_issue(
        self,
        issue: HealthIssue,
        approval_callback: Optional[Callable[[HealthIssue], bool]] = None
    ) -> bool:
        """
        Attempt to automatically remediate an issue
        
        Args:
            issue: HealthIssue to remediate
            approval_callback: Optional callback for approval (for critical actions)
            
        Returns:
            True if remediation succeeded or was not needed
        """
        if not issue.recommended_action:
            logger.info(f"No recommended action for {issue.issue_type.value}")
            return False
        
        # Check if approval is needed for critical actions
        if issue.severity == "critical" and approval_callback:
            if not approval_callback(issue):
                logger.info(f"Remediation for {issue.issue_type.value} was not approved")
                return False
        
        try:
            if issue.recommended_action == RemediationAction.CLEANUP_TEMP:
                return self._cleanup_temp_files()
            elif issue.recommended_action == RemediationAction.KILL_PROCESS:
                return self._kill_high_cpu_process()
            elif issue.recommended_action == RemediationAction.RESTART_SERVICE:
                return self._restart_service(issue.affected_resource)
            elif issue.recommended_action == RemediationAction.CLEAR_CACHE:
                return self._clear_caches()
            elif issue.recommended_action == RemediationAction.ALERT_ONLY:
                logger.warning(f"Issue requires manual intervention: {issue.message}")
                return False
            else:
                logger.warning(f"Unknown remediation action: {issue.recommended_action}")
                return False
        
        except Exception as e:
            logger.error(f"Remediation failed for {issue.issue_type.value}: {e}")
            return False
    
    def _cleanup_temp_files(self) -> bool:
        """Clean up temporary files"""
        try:
            script = """
            $TempDirs = @(
                "C:\\Windows\\Temp",
                "C:\\Users\\*\\AppData\\Local\\Temp",
                "$env:TEMP"
            )
            
            foreach ($dir in $TempDirs) {
                Get-ChildItem -Path $dir -Recurse -ErrorAction SilentlyContinue | 
                    Where-Object {$_.CreationTime -lt (Get-Date).AddDays(-7)} | 
                    Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
            }
            
            Write-Host "Cleanup completed"
            """
            
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            success = result.returncode == 0
            logger.info(f"Temp cleanup {'succeeded' if success else 'failed'}")
            return success
        
        except Exception as e:
            logger.error(f"Temp cleanup error: {e}")
            return False
    
    def _kill_high_cpu_process(self) -> bool:
        """Kill process with highest CPU usage"""
        try:
            # Get process with highest CPU
            script = """
            Get-Process | 
                Select-Object ProcessName, @{n='CPUPercent';e={$_.CPU}} | 
                Sort-Object CPUPercent -Descending | 
                Select-Object -First 1 | 
                ConvertTo-Json
            """
            
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return False
            
            import json
            process_info = json.loads(result.stdout)
            process_name = process_info.get('ProcessName')
            
            if not process_name or process_name.lower() == 'system':
                logger.warning("Cannot kill system processes")
                return False
            
            # Kill the process
            kill_result = subprocess.run(
                f"taskkill /IM {process_name}.exe /F",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            success = kill_result.returncode == 0
            logger.info(f"Process kill {'succeeded' if success else 'failed'} for {process_name}")
            return success
        
        except Exception as e:
            logger.error(f"Process kill error: {e}")
            return False
    
    def _restart_service(self, service_name: Optional[str]) -> bool:
        """Restart a Windows service"""
        if not service_name:
            return False
        
        try:
            cmd = f"powershell -Command \"Restart-Service -Name '{service_name}' -Force\""
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            success = result.returncode == 0
            logger.info(f"Service restart {'succeeded' if success else 'failed'} for {service_name}")
            return success
        
        except Exception as e:
            logger.error(f"Service restart error: {e}")
            return False
    
    def _clear_caches(self) -> bool:
        """Clear system caches"""
        try:
            script = """
            # Clear DNS cache
            ipconfig /flushdns | Out-Null
            
            # Clear file system cache (requires admin)
            Clear-DnsClientCache -ErrorAction SilentlyContinue
            
            Write-Host "Caches cleared"
            """
            
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            success = result.returncode == 0
            logger.info(f"Cache clear {'succeeded' if success else 'failed'}")
            return success
        
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get overall health report"""
        total_issues = len(self.detected_issues)
        critical = sum(1 for i in self.detected_issues if i.severity == "critical")
        high = sum(1 for i in self.detected_issues if i.severity == "high")
        remediated = len(self.remediated_issues)
        
        return {
            "total_issues_detected": total_issues,
            "critical": critical,
            "high": high,
            "remediated": remediated,
            "recent_issues": [i.to_dict() for i in self.detected_issues[-20:]],
        }
