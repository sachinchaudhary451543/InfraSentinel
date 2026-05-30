"""
PHASE 12: Background Worker System with RQ (Redis Queue)
Handles async tasks:
- Command execution
- Alert processing
- Activity ingestion
- Report generation
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict
from redis import Redis
from rq import Queue, Worker
from rq.job import JobStatus
from functools import wraps

# ============================================================================
# CONFIGURATION
# ============================================================================

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_CONN = Redis.from_url(REDIS_URL)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [RQ-WORKER] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ServerMonitor-Workers")

# Initialize job queues
jobs_queue = Queue('jobs', connection=REDIS_CONN)
alerts_queue = Queue('alerts', connection=REDIS_CONN)
metrics_queue = Queue('metrics', connection=REDIS_CONN)


# ============================================================================
# DECORATORS & UTILITIES
# ============================================================================

def log_job(func):
    """Decorator to log job execution"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Starting job: {func.__name__} | Args: {args[:2]}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"Completed job: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"Failed job: {func.__name__} | Error: {e}")
            raise
    return wrapper


def enqueue_job(queue: Queue, func, *args, job_timeout=360, **kwargs):
    """Enqueue a job with metadata"""
    job = queue.enqueue(
        func,
        *args,
        job_timeout=job_timeout,
        meta={
            'enqueued_at': datetime.utcnow().isoformat(),
            'function_name': func.__name__
        },
        **kwargs
    )
    logger.info(f"Enqueued job: {job.id} | Function: {func.__name__}")
    return job


# ============================================================================
# PHASE 12: ASYNC COMMAND EXECUTION
# ============================================================================

@log_job
def execute_remote_command(command_id: int, server_id: int, command: str, 
                          agent_key: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Execute command on remote server asynchronously
    Called from API endpoint instead of blocking request
    """
    from web.models import db, DeploymentJob, Server
    
    try:
        # Get job record
        job_record = db.session.get(DeploymentJob, command_id)
        if not job_record:
            logger.error(f"Job {command_id} not found")
            return {"status": "error", "message": "Job not found"}
        
        # Update to running
        job_record.status = "running"
        job_record.started_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Executing command {command_id} on server {server_id}")
        
        # Simulate command execution (in real system, this would poll/wait for agent response)
        import subprocess
        import platform
        
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        
        output = result.stdout + result.stderr
        status = 'completed' if result.returncode == 0 else 'failed'
        
        # Update job record
        job_record.status = status
        job_record.output = output
        job_record.completed_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Command {command_id} completed with status: {status}")
        
        return {
            "status": "success",
            "job_id": command_id,
            "execution_status": status,
            "output_length": len(output)
        }
    
    except subprocess.TimeoutExpired:
        job_record.status = "timeout"
        job_record.output = f"Command timeout after {timeout}s"
        db.session.commit()
        logger.error(f"Command {command_id} timeout")
        return {"status": "timeout"}
    
    except Exception as e:
        job_record.status = "error"
        job_record.output = str(e)
        db.session.commit()
        logger.error(f"Command {command_id} error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# PHASE 12: ASYNC ALERT PROCESSING
# ============================================================================

@log_job
def process_system_alert(server_id: int, alert_type: str, 
                        threshold: float, current_value: float) -> Dict[str, Any]:
    """
    Process and store system alerts asynchronously
    Called when metrics exceed thresholds
    """
    from web.models import db, SystemAlert, Server
    
    try:
        server = db.session.get(Server, server_id)
        if not server:
            logger.error(f"Server {server_id} not found")
            return {"status": "error", "message": "Server not found"}
        
        # Check if alert already exists (avoid duplicates)
        existing = SystemAlert.query.filter_by(
            server_id=server_id,
            alert_type=alert_type,
            is_active=True
        ).first()
        
        if not existing:
            alert = SystemAlert(
                server_id=server_id,
                alert_type=alert_type,
                is_active=True,
                description=f"{alert_type} exceeded threshold: {current_value:.2f}% (threshold: {threshold:.2f}%)",
                created_at=datetime.utcnow()
            )
            db.session.add(alert)
            logger.info(f"Created alert: {alert_type} on server {server_id}")
        else:
            existing.updated_at = datetime.utcnow()
            logger.info(f"Updated existing alert: {alert_type} on server {server_id}")
        
        db.session.commit()
        
        return {
            "status": "success",
            "server_id": server_id,
            "alert_type": alert_type
        }
    
    except Exception as e:
        logger.error(f"Alert processing error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# PHASE 12: ASYNC METRICS INGESTION
# ============================================================================

@log_job
def ingest_metrics_batch(metrics_list: list) -> Dict[str, Any]:
    """
    Ingest batch of metrics asynchronously
    Avoids blocking on database writes
    """
    from web.models import db, Metric, Server
    
    inserted = 0
    errors = 0
    
    try:
        for metric_data in metrics_list:
            try:
                # Find server by hostname
                server = Server.query.filter_by(
                    hostname=metric_data['hostname'],
                    tenant_id=metric_data.get('tenant_id', 1)
                ).first()
                
                if not server:
                    logger.warning(f"Server {metric_data['hostname']} not found")
                    errors += 1
                    continue
                
                # Create metric record
                metric = Metric(
                    server_id=server.id,
                    cpu_util_percent=metric_data.get('cpu_percent', 0),
                    ram_util_percent=metric_data.get('ram_percent', 0),
                    ssd_util_percent=metric_data.get('disk_percent', 0),
                    timestamp=datetime.fromisoformat(metric_data['timestamp'])
                )
                db.session.add(metric)
                inserted += 1
                
                # Check for alerts (high CPU, memory, disk)
                for alert_type, value_key, threshold in [
                    ("High CPU", "cpu_percent", 80),
                    ("High Memory", "ram_percent", 90),
                    ("Low Disk Space", "disk_percent", 95)
                ]:
                    current_value = metric_data.get(value_key, 0)
                    if current_value > threshold:
                        # Enqueue alert processing
                        enqueue_job(
                            alerts_queue,
                            process_system_alert,
                            server.id,
                            alert_type,
                            threshold,
                            current_value
                        )
            
            except Exception as e:
                logger.error(f"Error ingesting metric: {e}")
                errors += 1
        
        # Batch commit
        db.session.commit()
        
        logger.info(f"Ingested {inserted} metrics, {errors} errors")
        return {
            "status": "success",
            "inserted": inserted,
            "errors": errors
        }
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Batch ingestion error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# PHASE 15: ERROR TRACKING & MONITORING
# ============================================================================

@log_job
def log_error_event(source: str, error_type: str, error_message: str, 
                   context: Dict = None) -> Dict[str, Any]:
    """
    Log application errors for monitoring
    Can be integrated with error tracking services (Sentry, etc.)
    """
    from web.models import db
    
    error_record = {
        "source": source,
        "error_type": error_type,
        "message": error_message,
        "context": context or {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.error(f"Error tracked: {error_type} from {source} | {error_message}")
    
    # Store in Redis for recent error tracking
    REDIS_CONN.lpush("error_log", json.dumps(error_record))
    REDIS_CONN.ltrim("error_log", 0, 1000)  # Keep last 1000 errors
    REDIS_CONN.expire("error_log", 86400)  # Expire after 24 hours
    
    # Optional: Send to external error tracking service
    # sentry_sdk.capture_exception(context)
    
    return {
        "status": "success",
        "error_id": source,
        "logged_at": error_record['timestamp']
    }


# ============================================================================
# PHASE 12: REPORT GENERATION
# ============================================================================

@log_job
def generate_daily_report(tenant_id: int) -> Dict[str, Any]:
    """
    Generate daily system report asynchronously
    """
    from web.models import db, Server, Metric, SystemAlert
    from datetime import timedelta
    
    try:
        cutoff = datetime.utcnow() - timedelta(days=1)
        
        # Get servers
        servers = Server.query.filter_by(tenant_id=tenant_id).all()
        
        report = {
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "servers_count": len(servers),
            "metrics_24h": Metric.query.filter(Metric.timestamp > cutoff).count(),
            "active_alerts": SystemAlert.query.filter(
                SystemAlert.is_active == True
            ).count(),
            "servers": []
        }
        
        for server in servers:
            metrics = Metric.query.filter(
                Metric.server_id == server.id,
                Metric.timestamp > cutoff
            ).all()
            
            if metrics:
                avg_cpu = sum(m.cpu_util_percent for m in metrics) / len(metrics)
                avg_ram = sum(m.ram_util_percent for m in metrics) / len(metrics)
                avg_disk = sum(m.ssd_util_percent for m in metrics) / len(metrics)
            else:
                avg_cpu = avg_ram = avg_disk = 0
            
            report["servers"].append({
                "id": server.id,
                "hostname": server.hostname,
                "avg_cpu_24h": round(avg_cpu, 2),
                "avg_ram_24h": round(avg_ram, 2),
                "avg_disk_24h": round(avg_disk, 2)
            })
        
        # Store report in Redis (or database)
        REDIS_CONN.setex(
            f"report:tenant:{tenant_id}:{datetime.utcnow().date()}",
            86400 * 7,  # 7 days
            json.dumps(report)
        )
        
        logger.info(f"Generated report for tenant {tenant_id}")
        return report
    
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# WORKER INITIALIZATION
# ============================================================================

def start_worker(queue_names=None):
    """Start RQ worker"""
    if queue_names is None:
        queue_names = ['jobs', 'alerts', 'metrics']
    
    queues = [Queue(name, connection=REDIS_CONN) for name in queue_names]
    
    logger.info(f"Starting RQ worker for queues: {queue_names}")
    
    worker = Worker(queues, connection=REDIS_CONN)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    start_worker()
