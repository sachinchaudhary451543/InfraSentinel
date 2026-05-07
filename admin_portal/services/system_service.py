"""
System Service
Handles system management business logic
"""

import logging
from admin_portal.models import db, Server, Metric
from sqlalchemy import func, desc
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SystemService:
    """Service for system management operations"""
    
    @staticmethod
    def get_all_systems(tenant_id):
        """Get all systems for a tenant"""
        try:
            return Server.query.filter_by(tenant_id=tenant_id).all()
        except Exception as e:
            logger.error(f"Error fetching systems: {e}")
            return []
    
    @staticmethod
    def get_system_by_id(system_id, tenant_id):
        """Get system by ID with authorization check"""
        try:
            return Server.query.filter_by(
                id=system_id, 
                tenant_id=tenant_id
            ).first()
        except Exception as e:
            logger.error(f"Error fetching system {system_id}: {e}")
            return None
    
    @staticmethod
    def get_system_status(system_id):
        """Get current status of a system"""
        try:
            latest_metrics = Metric.query.filter_by(
                server_id=system_id
            ).order_by(desc(Metric.timestamp)).first()
            
            if not latest_metrics:
                return {'status': 'offline', 'last_seen': None}
            
            # System is online if last metric is within 2 minutes
            time_diff = datetime.utcnow() - latest_metrics.timestamp
            is_online = time_diff < timedelta(minutes=2)
            
            return {
                'status': 'online' if is_online else 'offline',
                'last_seen': latest_metrics.timestamp,
                'cpu': latest_metrics.cpu_usage,
                'memory': latest_metrics.memory_usage,
                'disk': latest_metrics.disk_usage
            }
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {'status': 'error', 'last_seen': None}
    
    @staticmethod
    def get_system_health_score(system_id, hours=24):
        """Calculate overall health score for a system (0-100)"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            metrics = Metric.query.filter(
                Metric.server_id == system_id,
                Metric.timestamp >= cutoff_time
            ).all()
            
            if not metrics:
                return 0
            
            # Calculate average CPU and Memory usage
            avg_cpu = sum(m.cpu_usage or 0 for m in metrics) / len(metrics)
            avg_memory = sum(m.memory_usage or 0 for m in metrics) / len(metrics)
            
            # Health score calculation: 100 - (avg_cpu * 0.4 + avg_memory * 0.6)
            # This penalizes high memory usage more
            health_score = max(0, min(100, 100 - (avg_cpu * 0.4 + avg_memory * 0.6)))
            return round(health_score)
        except Exception as e:
            logger.error(f"Error calculating health score: {e}")
            return 0
    
    @staticmethod
    def register_system(hostname, ip_address, tenant_id):
        """Register a new system"""
        try:
            system = Server(
                hostname=hostname,
                ip_address=ip_address,
                tenant_id=tenant_id
            )
            db.session.add(system)
            db.session.commit()
            logger.info(f"System registered: {hostname}")
            return system
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error registering system: {e}")
            return None
    
    @staticmethod
    def delete_system(system_id, tenant_id):
        """Delete a system"""
        try:
            system = Server.query.filter_by(
                id=system_id,
                tenant_id=tenant_id
            ).first()
            
            if not system:
                return False
            
            db.session.delete(system)
            db.session.commit()
            logger.info(f"System deleted: {system.hostname}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting system: {e}")
            return False
    
    @staticmethod
    def get_system_count(tenant_id):
        """Get count of systems for a tenant"""
        try:
            return Server.query.filter_by(tenant_id=tenant_id).count()
        except Exception as e:
            logger.error(f"Error counting systems: {e}")
            return 0
    
    @staticmethod
    def get_online_system_count(tenant_id):
        """Get count of online systems for a tenant"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=2)
            online_systems = db.session.query(Server).filter(
                Server.tenant_id == tenant_id,
                Server.id.in_(
                    db.session.query(Metric.server_id).filter(
                        Metric.timestamp >= cutoff_time
                    ).distinct()
                )
            ).count()
            return online_systems
        except Exception as e:
            logger.error(f"Error counting online systems: {e}")
            return 0
