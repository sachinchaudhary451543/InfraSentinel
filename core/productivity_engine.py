"""
Productivity Engine
Transforms raw agent activity telemetry into rich relational models:
ActivitySession, AppUsage, FocusSession, and AttendanceRecord.
"""
from datetime import datetime, timedelta
import logging
from web.models import db, Server, EmployeeDeviceAssignment, ActivitySession, AppUsage, AttendanceRecord, ProductivityClassification, EmployeeActivity

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 5 # Break sessions if gap is larger than 5 mins

class ProductivityEngine:
    
    @staticmethod
    def process_agent_activity(tenant_id: int, server_id: int, logged_in_user: str, 
                               active_app: str, window_title: str, browser_url: str, 
                               idle_time_seconds: int, timestamp: datetime,
                               interval_seconds: int = 30) -> None:
        """
        Process incoming agent activity.
        Must be called from within an active Flask app context.
        """
        if not logged_in_user:
            return
            
        # 1. Resolve Employee via EmployeeDeviceAssignment
        assignment = EmployeeDeviceAssignment.query.filter_by(
            tenant_id=tenant_id,
            server_id=server_id,
            is_active=True
        ).first()
        
        if not assignment:
            # If no assignment exists yet, attempt to resolve it again before skipping.
            from core.identity_correlation import IdentityCorrelationService
            try:
                server = Server.query.get(server_id)
                hostname = server.hostname if server else ''
                serial_number = getattr(server, 'serial_number', '') if server else ''
                IdentityCorrelationService.correlate_agent_payload(
                    tenant_id=tenant_id,
                    server_id=server_id,
                    hostname=hostname,
                    serial_number=serial_number,
                    logged_in_user=logged_in_user
                )
                assignment = EmployeeDeviceAssignment.query.filter_by(
                    tenant_id=tenant_id,
                    server_id=server_id,
                    is_active=True
                ).first()
            except Exception as e:
                logger.warning(f"Identity re-correlation failed for productivity: {e}")

        if not assignment:
            # Still no active assignment; skip detailed productivity tracking.
            return
            
        employee_id = assignment.employee_id
        
        # 2. Update or Create AttendanceRecord for today
        today = timestamp.date()
        attendance = AttendanceRecord.query.filter_by(
            tenant_id=tenant_id,
            employee_id=employee_id,
            date=today
        ).first()
        
        if not attendance:
            attendance = AttendanceRecord(
                tenant_id=tenant_id,
                employee_id=employee_id,
                date=today,
                first_activity=timestamp,
                last_activity=timestamp,
                status='present'
            )
            db.session.add(attendance)
        else:
            if not attendance.first_activity or timestamp < attendance.first_activity:
                attendance.first_activity = timestamp
            if not attendance.last_activity or timestamp > attendance.last_activity:
                attendance.last_activity = timestamp
                
        # 3. Find active ActivitySession
        # An active session is one that hasn't ended and the last activity was within SESSION_TIMEOUT
        cutoff_time = timestamp - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        
        session = ActivitySession.query.filter(
            ActivitySession.tenant_id == tenant_id,
            ActivitySession.employee_id == employee_id,
            ActivitySession.server_id == server_id,
            ActivitySession.end_time.is_(None)
        ).order_by(ActivitySession.start_time.desc()).first()
        
        # Determine last activity time from database
        # Note: EmployeeActivity was committed right before this in api.py, so we search for the last one before current timestamp.
        last_activity = EmployeeActivity.query.filter(
            EmployeeActivity.server_id == server_id,
            EmployeeActivity.timestamp < timestamp
        ).order_by(EmployeeActivity.timestamp.desc()).first()
        
        last_activity_time = last_activity.timestamp if last_activity else None
        
        # If we have a session, but it's too old or from a different day, close it
        is_new_session = False
        if session:
            # Check if session is from a previous day
            if session.start_time.date() != timestamp.date():
                session.end_time = last_activity_time or session.start_time.replace(hour=23, minute=59, second=59)
                session = None
            # Check if session timeout exceeded
            elif last_activity_time and last_activity_time < cutoff_time:
                session.end_time = last_activity_time
                session = None
            
        if not session:
            session = ActivitySession(
                tenant_id=tenant_id,
                employee_id=employee_id,
                server_id=server_id,
                start_time=timestamp
            )
            db.session.add(session)
            db.session.flush() # get ID
            is_new_session = True
            
        # We use the integer 'minutes' columns to store SECONDS for higher precision without schema changes.
        duration_seconds = interval_seconds # Default assumption
        if not is_new_session and last_activity_time:
            delta = int((timestamp - last_activity_time).total_seconds())
            if 0 < delta < 300: # Cap at 5 mins
                duration_seconds = delta
        
        # Determine classification
        classification = 'neutral'
        if active_app:
            # Simple matching (in production, use Regex or exact match from DB)
            rule = ProductivityClassification.query.filter(
                ProductivityClassification.tenant_id == tenant_id,
                ProductivityClassification.pattern.ilike(f"%{active_app}%")
            ).first()
            if rule:
                classification = rule.category
            else:
                # Built-in fallback classification rules
                app_lower = active_app.lower()
                productive_keywords = [
                    'code', 'studio', 'excel', 'word', 'teams', 'slack', 'zoom', 'powerpnt', 'outlook',
                    'mstsc', 'chrome', 'msedge', 'pycharm', 'idea', 'git', 'docker', 'cmd', 'powershell',
                    'bash', 'ssh', 'putty', 'notepad', 'sublime', 'postman', 'workbench', 'developer',
                    'terminal', 'explorer', 'sourcetree'
                ]
                non_productive_keywords = [
                    'netflix', 'youtube', 'facebook', 'instagram', 'twitter', 'tiktok', 'spotify',
                    'steam', 'discord', 'game', 'xbox', 'candycrush', 'play', 'video'
                ]
                
                # Check productive keywords first
                if any(kw in app_lower for kw in productive_keywords):
                    classification = 'productive'
                # Check non-productive keywords
                elif any(kw in app_lower for kw in non_productive_keywords):
                    classification = 'non_productive'
                
        # Update session aggregates (storing SECONDS in the minutes columns)
        if idle_time_seconds < 60:
            session.active_seconds = (session.active_seconds or 0) + duration_seconds
            attendance.total_active_seconds = (attendance.total_active_seconds or 0) + duration_seconds

            # Backward compatibility
            session.active_minutes = session.active_seconds
            attendance.total_active_minutes = attendance.total_active_seconds

            if classification == 'productive':
                session.productive_minutes = (session.productive_minutes or 0) + duration_seconds
                session.productive_seconds = (session.productive_seconds or 0) + duration_seconds
            elif classification == 'non_productive':
                session.non_productive_minutes = (session.non_productive_minutes or 0) + duration_seconds
                session.non_productive_seconds = (session.non_productive_seconds or 0) + duration_seconds
        else:
            session.idle_minutes = (session.idle_minutes or 0) + duration_seconds
            session.idle_seconds = (session.idle_seconds or 0) + duration_seconds
            attendance.total_idle_minutes = (attendance.total_idle_minutes or 0) + duration_seconds
            attendance.total_idle_seconds = (attendance.total_idle_seconds or 0) + duration_seconds
            
        # 4. Record AppUsage
        if active_app:
            usage = AppUsage(
                tenant_id=tenant_id,
                session_id=session.id,
                app_name=active_app,
                window_title=window_title,
                url=browser_url,
                start_time=timestamp,
                duration_seconds=duration_seconds,
                classification=classification
            )
            db.session.add(usage)
            
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to save productivity metrics: {e}")
            db.session.rollback()
