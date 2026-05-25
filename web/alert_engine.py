import logging
from web.models import db, Server, SystemAlert
from web.services.notification_service import create_notification

# Static rule definition for simplicity. In a real system, this would be a DB table `AlertRule`.
ALERT_RULES = [
    {"metric": "cpu_util_percent", "op": ">", "threshold": 90.0, "severity": "critical", "message": "High CPU Usage"},
    {"metric": "ram_util_percent", "op": ">", "threshold": 90.0, "severity": "high", "message": "High Memory Usage"},
    {"metric": "ssd_util_percent", "op": ">", "threshold": 85.0, "severity": "warning", "message": "Low Disk Space"}
]

def evaluate_metric_for_alerts(metric):
    """Evaluate a newly inserted metric against alert rules using basic engine"""
    server = db.session.get(Server, metric.server_id)
    if not server:
        return
        
    for rule in ALERT_RULES:
        # Get the actual value from the metric model dynamically
        val = getattr(metric, rule["metric"], None)
        if val is None:
            continue
            
        triggered = False
        if rule["op"] == ">" and val > rule["threshold"]:
            triggered = True
        elif rule["op"] == "<" and val < rule["threshold"]:
            triggered = True
            
        if triggered:
            # deduplication: check if active alert for this metric exists
            existing = SystemAlert.query.filter_by(
                server_id=server.id, 
                alert_type=rule["metric"], 
                is_active=True
            ).first()
            
            if not existing:
                alert = SystemAlert()
                alert.server_id = server.id
                alert.alert_type = rule["metric"]
                alert.severity = rule["severity"]
                alert.message = f"{rule['message']} ({val}% {rule['op']} {rule['threshold']}%)"
                alert.is_active = True
                db.session.add(alert)
                db.session.commit()
                
                # Notifications stub
                send_notification(alert)
        else:
            # auto-resolve logic
            existing = SystemAlert.query.filter_by(
                server_id=server.id, 
                alert_type=rule["metric"], 
                is_active=True
            ).first()
            if existing:
                existing.is_active = False
                existing.resolved_at = metric.timestamp
                db.session.commit()
                logging.info(f"Alert resolved: {existing.message}")

def send_notification(alert):
    """Stub for Email SMTP or Webhook logic"""
    logging.warning(f"ALERT TRIGGERED: [Tenant {alert.tenant_id}] Server {alert.server_id} - {alert.message}")
    # Also create a SyncNotification so the UI bell shows the alert
    try:
        create_notification(alert.tenant_id or server.tenant_id if hasattr(alert, 'tenant_id') else None,
                            'alert',
                            f'Alert: {getattr(alert, "message", "System Alert")}',
                            f"Server {getattr(alert, 'server_id', '')}: {getattr(alert, 'message', '')}",
                            {'alert_id': getattr(alert, 'id', None)})
    except Exception as e:
        logging.debug(f"Failed to create UI notification for alert: {e}")
