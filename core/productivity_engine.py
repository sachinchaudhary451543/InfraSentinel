"""
Productivity Engine
Transforms raw agent activity telemetry into rich relational models:
ActivitySession, AppUsage, FocusSession, and AttendanceRecord.
"""
from datetime import datetime, timedelta
import logging
from web.models import (
    db, EmployeeActivity, EmployeeDeviceAssignment, ActivitySession, AppUsage,
    AttendanceRecord, ProductivityClassification, Employee,
)

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 5 # Break sessions if gap is larger than 5 mins
MAX_HEARTBEAT_GAP_SECONDS = SESSION_TIMEOUT_MINUTES * 60

class ProductivityEngine:

    @staticmethod
    def _rebuild_session_totals(session: ActivitySession, logged_in_user: str, timestamp: datetime) -> None:
        """Recalculate session totals from persisted agent heartbeat timestamps.

        Agent intervals are configurable, so a fixed duration per sample inflates
        totals whenever the interval differs from that assumption. The current
        sample is already stored in ``EmployeeActivity`` before this method runs.
        """
        employee = db.session.get(Employee, session.employee_id)
        identity_aliases = {logged_in_user}
        if employee:
            for identity in (employee.email, employee.local_username, (employee.email or '').split('@', 1)[0]):
                if identity:
                    identity_aliases.add(identity)
        identity_aliases_normalized = {identity.lower() for identity in identity_aliases}

        samples = EmployeeActivity.query.filter(
            EmployeeActivity.server_id == session.server_id,
            db.func.lower(EmployeeActivity.user).in_(identity_aliases_normalized),
            EmployeeActivity.timestamp >= session.start_time,
            EmployeeActivity.timestamp <= timestamp,
        ).order_by(EmployeeActivity.timestamp.asc()).all()

        usages = {
            usage.start_time: usage
            for usage in AppUsage.query.filter_by(session_id=session.id).all()
            if usage.start_time
        }

        active_seconds = idle_seconds = productive_seconds = non_productive_seconds = 0
        previous = None
        for sample in samples:
            duration_seconds = 0
            if previous:
                duration_seconds = max(0, min(
                    int((sample.timestamp - previous.timestamp).total_seconds()),
                    MAX_HEARTBEAT_GAP_SECONDS,
                ))

            usage = usages.get(sample.timestamp)
            if usage:
                usage.duration_seconds = duration_seconds

            if sample.idle_time < 60:
                active_seconds += duration_seconds
                if usage and usage.classification == 'productive':
                    productive_seconds += duration_seconds
                elif usage and usage.classification == 'non_productive':
                    non_productive_seconds += duration_seconds
            else:
                idle_seconds += duration_seconds
            previous = sample

        # Legacy column names are retained, but all values are seconds.
        session.active_minutes = active_seconds
        session.idle_minutes = idle_seconds
        session.productive_minutes = productive_seconds
        session.non_productive_minutes = non_productive_seconds

    
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
            # Check persisted heartbeat time; instance-only attributes are lost
            # between Flask requests and cannot reliably close stale sessions.
            else:
                employee = db.session.get(Employee, employee_id)
                identity_aliases = {logged_in_user}
                if employee:
                    for identity in (employee.email, employee.local_username, (employee.email or '').split('@', 1)[0]):
                        if identity:
                            identity_aliases.add(identity)
                identity_aliases_normalized = {identity.lower() for identity in identity_aliases}
                last_sample = EmployeeActivity.query.filter(
                    EmployeeActivity.server_id == server_id,
                    db.func.lower(EmployeeActivity.user).in_(identity_aliases_normalized),
                    EmployeeActivity.timestamp >= session.start_time,
                    EmployeeActivity.timestamp < timestamp,
                ).order_by(EmployeeActivity.timestamp.desc()).first()
                if last_sample and last_sample.timestamp < cutoff_time:
                    session.end_time = last_sample.timestamp
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
                
        # 4. Record AppUsage. Its duration is rebuilt below from actual heartbeats.
        if active_app:
            usage = AppUsage(
                tenant_id=tenant_id,
                session_id=session.id,
                app_name=active_app,
                window_title=window_title,
                url=browser_url,
                start_time=timestamp,
                duration_seconds=0,
                classification=classification
            )
            db.session.add(usage)

        db.session.flush()
        ProductivityEngine._rebuild_session_totals(session, logged_in_user, timestamp)

        # Attendance is the sum of actual session durations, not a fixed number
        # of seconds per heartbeat.
        day_sessions = ActivitySession.query.filter_by(
            tenant_id=tenant_id,
            employee_id=employee_id,
        ).filter(ActivitySession.start_time >= datetime.combine(today, datetime.min.time())).all()
        attendance.total_active_minutes = sum(s.active_minutes or 0 for s in day_sessions)
        attendance.total_idle_minutes = sum(s.idle_minutes or 0 for s in day_sessions)
            
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to save productivity metrics: {e}")
            db.session.rollback()
