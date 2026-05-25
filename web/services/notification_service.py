"""Notification helpers to create SyncNotification records used by the UI bell."""
from datetime import datetime
import json
import logging
from web.models import db, SyncNotification

logger = logging.getLogger("notification_service")


def create_notification(tenant_id: int, category: str, title: str, message: str, breakdown: dict = None):
    try:
        notif = SyncNotification(
            tenant_id=tenant_id,
            category=category or 'sync',
            title=title or '',
            message=message or '',
            breakdown=json.dumps(breakdown) if breakdown else None,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.session.add(notif)
        db.session.commit()

        # Keep only latest 50 notifications per tenant
        try:
            old_ids = db.session.query(SyncNotification.id).filter_by(tenant_id=tenant_id).order_by(SyncNotification.created_at.desc()).offset(50).all()
            if old_ids:
                db.session.query(SyncNotification).filter(SyncNotification.id.in_([r[0] for r in old_ids])).delete(synchronize_session=False)
                db.session.commit()
        except Exception:
            db.session.rollback()

        return notif
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return None
