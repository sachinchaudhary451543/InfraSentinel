"""
Productivity Engine
Transforms raw agent activity telemetry into rich relational models:
ActivitySession, AppUsage, FocusSession, and AttendanceRecord.
"""
from datetime import datetime, timedelta
import logging
from web.models import db, EmployeeDeviceAssignment, ActivitySession, AppUsage, AttendanceRecord, ProductivityClassification

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 5 # Break sessions if gap is larger than 5 mins

class ProductivityEngine:
    
    @staticmethod
    def process_agent_activity(tenant_id: int, server_id: int, logged_in_user: str, 
                               active_app: str, window_title: str, browser_url: str, 
                               idle_time_seconds: int, timestamp: datetime) -> None:
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
            # If no assignment exists yet, the Identity Correlation Engine hasn't run or failed.
            # We skip detailed productivity tracking until identity is resolved.
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
        
        # If we have a session, but it's too old or from a different day, close it
        if session:
            # Check if session is from a previous day
            if session.start_time.date() != timestamp.date():
                session.end_time = session.start_time.replace(hour=23, minute=59, second=59)
                session = None
            # Check if session timeout exceeded
            elif hasattr(session, 'last_ping') and session.last_ping < cutoff_time:
                session.end_time = session.last_ping
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
            
        # Temporarily store last ping on object to check next time (since this script runs per payload)
        # Ideally, we should add last_activity to ActivitySession model or use end_time dynamically
        session.last_ping = timestamp 
        
        # We use the integer 'minutes' columns to store SECONDS for higher precision without schema changes.
        duration_seconds = 30 # Default assumption if no previous ping
        if hasattr(session, 'last_activity_time') and session.last_activity_time:
            delta = int((timestamp - session.last_activity_time).total_seconds())
            if 0 < delta < 300: # Cap at 5 mins
                duration_seconds = delta
        session.last_activity_time = timestamp
        
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
                
        # Update session aggregates (storing SECONDS in the minutes columns)
        if idle_time_seconds < 60:
            session.active_minutes = (session.active_minutes or 0) + duration_seconds
            attendance.total_active_minutes = (attendance.total_active_minutes or 0) + duration_seconds
            if classification == 'productive':
                session.productive_minutes = (session.productive_minutes or 0) + duration_seconds
            elif classification == 'non_productive':
                session.non_productive_minutes = (session.non_productive_minutes or 0) + duration_seconds
        else:
            session.idle_minutes = (session.idle_minutes or 0) + duration_seconds
            attendance.total_idle_minutes = (attendance.total_idle_minutes or 0) + duration_seconds
            
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
