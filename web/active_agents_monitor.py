"""
Active Agents Monitor
====================
Displays actual active agents from database instead of dummy data.
Shows agents with real metrics, last seen timestamp, and current status.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from web.models import db, Server, Metric, Tenant

logger = logging.getLogger("[ACTIVE_AGENTS]")


class ActiveAgentsMonitor:
    """Service to track and report on active monitoring agents"""
    
    # Cache for active agents (refresh every 30 seconds)
    _cache = {}
    _cache_ttl_sec = 30
    
    @staticmethod
    def get_active_agents_for_tenant(tenant_id: Optional[int] = None) -> List[Dict]:
        """
        Get list of actually active agents (with recent metrics).
        
        Returns agents that:
        - Have agent_installed = True
        - Have received metrics in last 5 minutes
        - Include current status, CPU, RAM, Disk, last seen time
        
        Args:
            tenant_id: Filter by tenant (None = all tenants)
        
        Returns:
            List of active agent dictionaries
        """
        
        try:
            now = datetime.utcnow()
            cache_key = f"active_agents_{tenant_id}"
            
            # Check cache
            cache_entry = ActiveAgentsMonitor._cache.get(cache_key)
            if cache_entry:
                age_sec = (now - cache_entry['cached_at']).total_seconds()
                if age_sec <= ActiveAgentsMonitor._cache_ttl_sec:
                    logger.debug(f"Using cached active agents (age: {age_sec:.1f}s)")
                    return cache_entry['result']
            
            # Define "active" as having metrics in last 5 minutes
            active_threshold = now - timedelta(minutes=5)
            
            # Query servers with recent metrics
            if tenant_id:
                # Get servers for this tenant with agent installed
                servers = db.session.query(Server).filter(
                    Server.tenant_id == tenant_id,
                    Server.agent_installed == True
                ).all()
            else:
                # Get all servers with agent installed
                servers = db.session.query(Server).filter(
                    Server.agent_installed == True
                ).all()
            
            server_ids = [s.id for s in servers]
            
            # Get latest metric for each server
            from sqlalchemy import func, and_, desc
            
            active_servers = []
            
            if server_ids:
                # Get latest metric per server
                subq = db.session.query(
                    Metric.server_id,
                    func.max(Metric.timestamp).label('max_timestamp')
                ).filter(
                    Metric.server_id.in_(server_ids),
                    Metric.timestamp >= active_threshold
                ).group_by(Metric.server_id).subquery()
                
                # Fetch full metrics
                recent_metrics = db.session.query(Metric).join(
                    subq, and_(
                        Metric.server_id == subq.c.server_id,
                        Metric.timestamp == subq.c.max_timestamp
                    )
                ).all()
                
                metrics_by_server = {m.server_id: m for m in recent_metrics}
                
                # Build agent list
                for server in servers:
                    metric = metrics_by_server.get(server.id)
                    
                    if metric:
                        # Calculate time since last metric
                        last_seen = metric.timestamp
                        seconds_ago = (now - last_seen).total_seconds()
                        
                        active_servers.append({
                            'id': server.id,
                            'hostname': server.hostname or server.name,
                            'ip_address': server.ip,
                            'os_info': server.os_info or 'Unknown',
                            'agent_version': server.agent_version or 'Unknown',
                            'tenant_id': server.tenant_id,
                            'status': 'online',
                            'is_active': True,
                            'last_seen': last_seen.isoformat(),
                            'seconds_ago': int(seconds_ago),
                            'metrics': {
                                'cpu_percent': metric.cpu_util_percent or 0,
                                'ram_percent': metric.ram_util_percent or 0,
                                'disk_percent': metric.ssd_util_percent or 0,
                                'total_ram_gb': metric.total_ram_gb or 0,
                                'used_ram_gb': metric.used_ram_gb or 0,
                                'total_disk_gb': metric.total_ssd_gb or 0,
                                'used_disk_gb': metric.used_ssd_gb or 0,
                            },
                            'virtual_cores': metric.virtual_cores or 0,
                        })
            
            # Sort by most recent first
            active_servers.sort(
                key=lambda x: x['seconds_ago']
            )
            
            # Cache result
            ActiveAgentsMonitor._cache[cache_key] = {
                'cached_at': now,
                'result': active_servers
            }
            
            logger.info(f"Found {len(active_servers)} active agents for tenant {tenant_id}")
            return active_servers
            
        except Exception as e:
            logger.error(f"Error fetching active agents: {e}", exc_info=True)
            return []
    
    @staticmethod
    def get_inactive_agents_for_tenant(tenant_id: Optional[int] = None) -> List[Dict]:
        """
        Get list of installed but inactive agents (no recent metrics).
        
        Returns agents that:
        - Have agent_installed = True
        - Have NO metrics in last 5 minutes
        - Include last seen time if available
        
        Args:
            tenant_id: Filter by tenant (None = all tenants)
        
        Returns:
            List of inactive agent dictionaries
        """
        
        try:
            now = datetime.utcnow()
            active_threshold = now - timedelta(minutes=5)
            
            # Query servers with agent installed
            if tenant_id:
                query = db.session.query(Server).filter(
                    Server.tenant_id == tenant_id,
                    Server.agent_installed == True
                )
            else:
                query = db.session.query(Server).filter(
                    Server.agent_installed == True
                )
            
            servers = query.all()
            server_ids = [s.id for s in servers]
            
            inactive_servers = []
            
            if server_ids:
                # Get servers that don't have recent metrics
                from sqlalchemy import func
                
                # Servers with recent metrics
                active_ids = db.session.query(Metric.server_id).filter(
                    Metric.server_id.in_(server_ids),
                    Metric.timestamp >= active_threshold
                ).group_by(Metric.server_id).all()
                
                active_set = {row[0] for row in active_ids}
                
                # Get last metric for inactive servers
                last_metrics = db.session.query(
                    Metric.server_id,
                    func.max(Metric.timestamp).label('last_timestamp')
                ).filter(
                    Metric.server_id.in_(server_ids)
                ).group_by(Metric.server_id).all()
                
                last_timestamp_by_server = {m[0]: m[1] for m in last_metrics}
                
                # Build inactive list
                for server in servers:
                    if server.id not in active_set:
                        last_timestamp = last_timestamp_by_server.get(server.id)
                        
                        seconds_since = None
                        if last_timestamp:
                            seconds_since = int((now - last_timestamp).total_seconds())
                        
                        inactive_servers.append({
                            'id': server.id,
                            'hostname': server.hostname or server.name,
                            'ip_address': server.ip,
                            'os_info': server.os_info or 'Unknown',
                            'agent_version': server.agent_version or 'Unknown',
                            'tenant_id': server.tenant_id,
                            'status': 'offline',
                            'is_active': False,
                            'last_seen': last_timestamp.isoformat() if last_timestamp else None,
                            'seconds_ago': seconds_since,
                        })
                
                # Sort by most recently seen first
                inactive_servers.sort(
                    key=lambda x: x['seconds_ago'] if x['seconds_ago'] is not None else float('inf')
                )
            
            logger.info(f"Found {len(inactive_servers)} inactive agents for tenant {tenant_id}")
            return inactive_servers
            
        except Exception as e:
            logger.error(f"Error fetching inactive agents: {e}", exc_info=True)
            return []
    
    @staticmethod
    def get_agents_by_tenant() -> Dict[str, Dict]:
        """
        Get aggregated agent statistics by tenant.
        
        Returns:
            Dict with tenant data and active/inactive agent counts
        """
        
        try:
            from sqlalchemy import func
            
            tenants = db.session.query(Tenant).all()
            
            result = {}
            
            for tenant in tenants:
                # Count agents
                total_agents = db.session.query(func.count(Server.id)).filter(
                    Server.tenant_id == tenant.id,
                    Server.agent_installed == True
                ).scalar() or 0
                
                # Count active agents (metrics in last 5 minutes)
                now = datetime.utcnow()
                active_threshold = now - timedelta(minutes=5)
                
                active_agent_ids = db.session.query(Metric.server_id).filter(
                    Metric.timestamp >= active_threshold
                ).distinct().all()
                
                active_set = {row[0] for row in active_agent_ids}
                
                # Get agents for this tenant
                tenant_agents = db.session.query(Server.id).filter(
                    Server.tenant_id == tenant.id,
                    Server.agent_installed == True
                ).all()
                
                tenant_agent_ids = {row[0] for row in tenant_agents}
                active_count = len(tenant_agent_ids & active_set)
                
                result[tenant.name] = {
                    'tenant_id': tenant.id,
                    'total_agents': total_agents,
                    'active_agents': active_count,
                    'inactive_agents': total_agents - active_count,
                    'online_percentage': round(
                        (active_count / total_agents * 100) if total_agents > 0 else 0,
                        2
                    )
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting agents by tenant: {e}")
            return {}
    
    @staticmethod
    def clear_cache():
        """Clear the active agents cache"""
        ActiveAgentsMonitor._cache.clear()
        logger.info("Active agents cache cleared")
