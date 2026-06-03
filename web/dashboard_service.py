"""
Optimized Dashboard Service - Batch query operations
=====================================================
Fixes N+1 query problem by using eager loading and batch queries.
All required data fetched in minimal queries instead of per-server lookups.
"""

import logging
from datetime import datetime
from sqlalchemy import and_, func

from web.models import (
    db, Server, Metric, AzureDevice, AzureUser, AzureDeviceOwner,
    EmployeeAssetLog, SystemAlert, SystemDiscovery, VM, Screenshot, EmployeeActivity
)

logger = logging.getLogger("[DASHBOARD_SERVICE]")


class OptimizedDashboardService:
    """Service to fetch dashboard data with minimal queries"""
    
    @staticmethod
    def get_dashboard_data(current_user):
        """
        Fetch all dashboard data with optimized queries.
        Returns: dict with all data needed for dashboard template
        
        Performance target: < 200ms total query time (vs current 2500ms)
        """
        
        try:
            # ─── STEP 1: Get server list with permission filtering ───
            query = db.session.query(Server).filter(
                Server.status.in_(['online', 'idle', 'active', None])
            )
            if current_user.is_superadmin:
                servers = query.all()
            elif current_user.tenant_id:
                servers = query.filter_by(tenant_id=current_user.tenant_id).all()
            else:
                servers = []
            
            server_ids = [s.id for s in servers]
            
            # ─── STEP 2: Fetch latest metrics for all servers (batch query) ───
            latest_metrics = {}
            if server_ids:
                # Subquery to get latest metric per server
                
                subq = db.session.query(
                    Metric.server_id,
                    func.max(Metric.id).label('max_id')
                ).filter(Metric.server_id.in_(server_ids)).group_by(Metric.server_id).subquery()
                
                # Fetch those specific metrics
                metrics_list = db.session.query(Metric).join(
                    subq, and_(
                        Metric.server_id == subq.c.server_id,
                        Metric.id == subq.c.max_id
                    )
                ).all()
                
                for m in metrics_list:
                    latest_metrics[m.server_id] = m
                    
            # ─── STEP 2b: Fetch latest screenshots and productivity (batch query) ───
            latest_screenshots = {}
            productivity_stats = {}
            if server_ids:
                # Screenshots
                subq_ss = db.session.query(
                    Screenshot.server_id,
                    func.max(Screenshot.id).label('max_id')
                ).filter(Screenshot.server_id.in_(server_ids)).group_by(Screenshot.server_id).subquery()
                
                ss_list = db.session.query(Screenshot).join(
                    subq_ss, and_(
                        Screenshot.server_id == subq_ss.c.server_id,
                        Screenshot.id == subq_ss.c.max_id
                    )
                ).all()
                for ss in ss_list:
                    latest_screenshots[ss.server_id] = ss
                    
                # Productivity (Active vs Total counts today)
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                activities = db.session.query(
                    EmployeeActivity.server_id,
                    func.count(EmployeeActivity.id).label('total_count'),
                    func.sum(db.case((EmployeeActivity.idle_time < 60, 1), else_=0)).label('active_count'),
                    func.min(EmployeeActivity.timestamp).label('min_timestamp'),
                    func.max(EmployeeActivity.timestamp).label('max_timestamp')
                ).filter(
                    EmployeeActivity.server_id.in_(server_ids),
                    EmployeeActivity.timestamp >= today_start
                ).group_by(EmployeeActivity.server_id).all()
                
                for act in activities:
                    active_count = act.active_count or 0
                    total_count = act.total_count or 0
                    min_ts = act.min_timestamp
                    max_ts = act.max_timestamp
                    
                    # Estimate the agent reporting interval dynamically
                    interval = 30
                    if total_count > 1 and min_ts and max_ts:
                        span_sec = (max_ts - min_ts).total_seconds()
                        avg_diff = span_sec / (total_count - 1)
                        # Cap the estimated interval to realistic agent ping frequencies (e.g. 10s to 60s)
                        if 10 <= avg_diff <= 60:
                            interval = int(round(avg_diff))
                    
                    active_time = int(active_count) * interval
                    total_time = int(total_count) * interval
                    percent = int((active_time / total_time * 100)) if total_time > 0 else 0
                    productivity_stats[act.server_id] = {
                        'active_time_str': f"{active_time // 3600}h {(active_time % 3600) // 60}m",
                        'percent': percent,
                        'total_time': total_time
                    }
            
            # ─── STEP 3: Fetch ACTIVE Azure devices only (exclude stale/inactive) ───
            if current_user.is_superadmin:
                azure_devices = db.session.query(AzureDevice).filter(
                    AzureDevice.is_active == 1,
                    AzureDevice.device_status == 'active'
                ).all()
            else:
                azure_devices = db.session.query(AzureDevice).filter(
                    AzureDevice.tenant_id == current_user.tenant_id,
                    AzureDevice.is_active == 1,
                    AzureDevice.device_status == 'active'
                ).all()
            
            # ─── STEP 4: Build owner mappings (batch queries) ───
            owner_by_device_id = {}
            owner_by_server_id = {}
            
            if current_user.tenant_id:
                # Fetch all ACTIVE Azure users only
                azure_users = db.session.query(AzureUser).filter(
                    AzureUser.tenant_id == current_user.tenant_id,
                    AzureUser.is_active == 1,
                    AzureUser.employment_status == 'active'
                ).all()
                user_by_id = {u.id: u for u in azure_users}
                
                # Fetch all Azure device owners at once
                azure_owners = db.session.query(AzureDeviceOwner).filter_by(
                    tenant_id=current_user.tenant_id
                ).all()
                for o in azure_owners:
                    u = user_by_id.get(o.user_id)
                    if u:
                        owner_by_device_id[o.device_id] = u.display_name or u.email
                
                # Fetch employee asset logs (latest per server)
                # This is one batch query, not N queries
                asset_logs = db.session.query(EmployeeAssetLog).filter(
                    EmployeeAssetLog.tenant_id == current_user.tenant_id,
                    EmployeeAssetLog.server_id.in_(server_ids)
                ).order_by(EmployeeAssetLog.login_timestamp.desc()).all()
                
                seen_servers = set()
                for log in asset_logs:
                    if log.server_id not in seen_servers:
                        owner_by_server_id[log.server_id] = log.employee_email or log.employee_id
                        seen_servers.add(log.server_id)
            
            # ─── STEP 5: Get counts (optimized queries) ───
            online_count = sum(1 for s in servers if s.is_online)
            agent_count = sum(1 for s in servers if getattr(s, 'agent_installed', False))
            
            # Batch count queries
            if current_user.is_superadmin:
                vm_count = db.session.query(func.count(VM.id)).scalar() or 0
                discovered_count = db.session.query(func.count(SystemDiscovery.id)).filter_by(
                    status='pending'
                ).scalar() or 0
                alert_count = db.session.query(func.count(SystemAlert.id)).filter_by(
                    is_active=True
                ).scalar() or 0
            else:
                # Join queries for tenant-specific counts
                vm_count = db.session.query(func.count(VM.id)).join(Server).filter(
                    Server.tenant_id == current_user.tenant_id
                ).scalar() or 0
                
                discovered_count = db.session.query(func.count(SystemDiscovery.id)).filter_by(
                    tenant_id=current_user.tenant_id,
                    status='pending'
                ).scalar() or 0
                
                alert_count = db.session.query(func.count(SystemAlert.id)).join(Server).filter(
                    Server.tenant_id == current_user.tenant_id,
                    SystemAlert.is_active == True
                ).scalar() or 0
            
            # ─── STEP 6: Build inventory list (no additional queries) ───
            inventory = []
            seen_names = set()
            
            # Helper function to check if online
            def check_online(s):
                return s and s.is_online
            
            # Add agent servers
            for s in servers:
                name_lower = (s.hostname or s.name).lower()
                seen_names.add(name_lower)
                is_online = check_online(s)
                
                # Use pre-fetched metric
                metric = latest_metrics.get(s.id)
                cpu = metric.cpu_util_percent if metric else 0
                ram = metric.ram_util_percent if metric else 0
                disk = metric.ssd_util_percent if metric else 0
                
                # Resolve assigned user
                assigned_user = owner_by_server_id.get(s.id)
                if not assigned_user and s.azure_device_id:
                    # Try to find the AzureDevice by its azure string ID to get the integer PK
                    for adev in azure_devices:
                        if adev.device_id == s.azure_device_id:
                            assigned_user = owner_by_device_id.get(adev.id)
                            break
                
                inventory.append({
                    'id': s.id,
                    'hostname': s.hostname or s.name,
                    'os_info': s.os_info or 'Unknown',
                    'server_type': s.server_type or 'Endpoint',
                    'agent_installed': s.agent_installed,
                    'agent_version': s.agent_version,
                    'status_label': s.status_label,
                    'is_online': is_online,
                    'type': s.type or 'agent',
                    'ip': s.ip or 'Unknown',
                    'is_hyperv_host': s.is_hyperv_host,
                    'cpu': metric.cpu if metric else None,
                    'ram': metric.ram if metric else None,
                    'disk': metric.disk if metric else None,
                    'cpu_percent': cpu or 0,
                    'memory_percent': ram or 0,
                    'disk_percent': disk or 0,
                    'assigned_user': assigned_user,
                    'azure_device_id': s.azure_device_id or ''
                })
            
            # Omitted adding Azure-only devices to monitoring dashboard as per requirements
            pass
            
            # Sort online systems to top
            inventory.sort(key=lambda x: x.get('is_online', False), reverse=True)
            
            # Add computed metric fields to servers for template rendering
            for s in servers:
                metric = latest_metrics.get(s.id)
                setattr(s, 'cpu_percent', metric.cpu_util_percent if metric else 0)
                setattr(s, 'memory_percent', metric.ram_util_percent if metric else 0)
                setattr(s, 'disk_percent', metric.ssd_util_percent if metric else 0)
                # Add VM count from relationship
                setattr(s, 'vms_list', s.vms.all())
                
                # Add screenshot and productivity
                ss = latest_screenshots.get(s.id)
                setattr(s, 'latest_screenshot_url', f"/api/screenshot/{ss.id}" if ss else None)
                
                prod = productivity_stats.get(s.id)
                if prod:
                    setattr(s, 'productivity_str', prod['active_time_str'])
                    setattr(s, 'productivity_percent', prod['percent'])
                else:
                    setattr(s, 'productivity_str', "—")
                    setattr(s, 'productivity_percent', 0)
            
            servers_sorted = sorted(servers, key=lambda x: x.is_online, reverse=True)
            
            return {
                'servers': servers_sorted,
                'inventory': inventory,
                'total_systems': len(inventory),
                'agent_count': agent_count,
                'online_count': online_count,
                'alert_count': alert_count,
                'vm_count': vm_count,
                'discovered_count': discovered_count,
            }
        
        except Exception as e:
            logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
            return {
                'servers': [],
                'inventory': [],
                'total_systems': 0,
                'agent_count': 0,
                'online_count': 0,
                'alert_count': 0,
                'vm_count': 0,
                'discovered_count': 0,
            }
