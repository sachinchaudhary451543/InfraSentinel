"""Productivity engine for processing raw agent activity into attendance/session summaries.

This module provides a minimal implementation to support legacy agent endpoints
that expect a ProductivityEngine class to exist. It maintains basic attendance
records without requiring a full deep work/session pipeline.
"""
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


class ProductivityEngine:
    @staticmethod
    def process_agent_activity(
        tenant_id,
        server_id,
        logged_in_user,
        active_app,
        window_title,
        browser_url,
        idle_time_seconds,
        timestamp
    ):
        try:
            if not tenant_id or not server_id or not logged_in_user:
                return

            from sqlalchemy import or_
            from web.models import db, Employee, AttendanceRecord

            normalized_user = str(logged_in_user).strip().lower()
            # Simple lookup by local username or email
            employee = Employee.query.filter(
                Employee.tenant_id == tenant_id,
                or_(Employee.local_username == normalized_user, Employee.email == normalized_user)
            ).first()

            if not employee:
                logger.debug(f"ProductivityEngine: no employee match for {normalized_user}")
                return

            target_date = timestamp.date() if isinstance(timestamp, datetime) else date.today()
            attendance = AttendanceRecord.query.filter_by(
                tenant_id=tenant_id,
                employee_id=employee.id,
                date=target_date
            ).first()

            if attendance is None:
                attendance = AttendanceRecord(
                    tenant_id=tenant_id,
                    employee_id=employee.id,
                    date=target_date,
                    first_activity=timestamp,
                    last_activity=timestamp,
                    total_active_minutes=0,
                    total_idle_minutes=int(idle_time_seconds / 60) if idle_time_seconds is not None else 0,
                    status='present'
                )
                db.session.add(attendance)
            else:
                if attendance.first_activity is None or timestamp < attendance.first_activity:
                    attendance.first_activity = timestamp
                if attendance.last_activity is None or timestamp > attendance.last_activity:
                    attendance.last_activity = timestamp
                if attendance.total_idle_minutes is None:
                    attendance.total_idle_minutes = 0
                attendance.total_idle_minutes += int(idle_time_seconds / 60) if idle_time_seconds is not None else 0
                attendance.status = attendance.status or 'present'

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception as exc:
            logger.debug(f"ProductivityEngine.process_agent_activity no-op: {exc}")
