"""
Metrics Service
Handles metrics collection and analysis
"""

import logging
from admin_portal.models import db, Metric
from sqlalchemy import func, desc, asc
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricService:
    """Service for metrics operations"""
    
    @staticmethod
    def get_latest_metrics(system_id):
        """Get latest metrics for a system"""
        try:
            return Metric.query.filter_by(
                server_id=system_id
            ).order_by(desc(Metric.timestamp)).first()
        except Exception as e:
            logger.error(f"Error fetching latest metrics: {e}")
            return None
    
    @staticmethod
    def get_metrics_history(system_id, hours=24, limit=100):
        """Get historical metrics for a system"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            return Metric.query.filter(
                Metric.server_id == system_id,
                Metric.timestamp >= cutoff_time
            ).order_by(asc(Metric.timestamp)).limit(limit).all()
        except Exception as e:
            logger.error(f"Error fetching metrics history: {e}")
            return []
    
    @staticmethod
    def get_average_metrics(system_id, hours=24):
        """Get average metrics for a system in given period"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            result = db.session.query(
                func.avg(Metric.cpu_usage).label('avg_cpu'),
                func.avg(Metric.memory_usage).label('avg_memory'),
                func.avg(Metric.disk_usage).label('avg_disk'),
                func.max(Metric.cpu_usage).label('max_cpu'),
                func.max(Metric.memory_usage).label('max_memory'),
                func.max(Metric.disk_usage).label('max_disk')
            ).filter(
                Metric.server_id == system_id,
                Metric.timestamp >= cutoff_time
            ).first()
            
            if not result:
                return None
            
            return {
                'avg_cpu': round(result.avg_cpu or 0, 2),
                'avg_memory': round(result.avg_memory or 0, 2),
                'avg_disk': round(result.avg_disk or 0, 2),
                'max_cpu': round(result.max_cpu or 0, 2),
                'max_memory': round(result.max_memory or 0, 2),
                'max_disk': round(result.max_disk or 0, 2)
            }
        except Exception as e:
            logger.error(f"Error calculating average metrics: {e}")
            return None
    
    @staticmethod
    def store_metrics(server_id, cpu_usage, memory_usage, disk_usage, timestamp=None):
        """Store metrics for a system"""
        try:
            metric = Metric(
                server_id=server_id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage=disk_usage,
                timestamp=timestamp or datetime.utcnow()
            )
            db.session.add(metric)
            db.session.commit()
            logger.debug(f"Metrics stored for server {server_id}")
            return metric
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error storing metrics: {e}")
            return None
    
    @staticmethod
    def cleanup_old_metrics(days=30):
        """Delete metrics older than specified days"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            deleted = db.session.query(Metric).filter(
                Metric.timestamp < cutoff_time
            ).delete()
            db.session.commit()
            logger.info(f"Deleted {deleted} old metric records")
            return deleted
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cleaning up old metrics: {e}")
            return 0
    
    @staticmethod
    def get_metrics_summary(systems_ids, hours=24):
        """Get summary metrics for multiple systems"""
        try:
            result = db.session.query(
                func.avg(Metric.cpu_usage).label('avg_cpu'),
                func.avg(Metric.memory_usage).label('avg_memory'),
                func.avg(Metric.disk_usage).label('avg_disk')
            ).filter(
                Metric.server_id.in_(systems_ids),
                Metric.timestamp >= datetime.utcnow() - timedelta(hours=hours)
            ).first()
            
            if not result:
                return {'avg_cpu': 0, 'avg_memory': 0, 'avg_disk': 0}
            
            return {
                'avg_cpu': round(result.avg_cpu or 0, 2),
                'avg_memory': round(result.avg_memory or 0, 2),
                'avg_disk': round(result.avg_disk or 0, 2)
            }
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return {'avg_cpu': 0, 'avg_memory': 0, 'avg_disk': 0}
