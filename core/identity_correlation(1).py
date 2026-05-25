"""Identity correlation helpers

Provides hostname and user normalization utilities used by agent ingestion
and Azure sync routines.

This module is intentionally lightweight so deployments that don't need
advanced correlation can still import the helper functions. Improve as needed.
"""
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def normalize_hostname(name: str) -> str:
    """Normalize a device hostname for correlation and matching.

    Rules:
    - Return empty string for falsy input
    - Strip surrounding whitespace
    - Remove domain parts after a dot (keep left-most label)
    - Replace non-alphanumeric characters with hyphens
    - Collapse multiple hyphens and trim
    - Lowercase the result
    """
    if not name:
        return ""
    s = str(name).strip()
    # If it's an IPv4/IPv6 address, return as-is (lowercased)
    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", s):
        return s.lower()

    if '.' in s:
        s = s.split('.')[0]

    s = re.sub(r'[^A-Za-z0-9]+', '-', s)
    s = re.sub(r'-{2,}', '-', s)
    s = s.strip('-')
    return s.lower()


def normalize_userprincipal(upn: str) -> str:
    """Simple UPN normalizer: return local part (before @) lowercased."""
    if not upn:
        return ''
    return str(upn).split('@', 1)[0].lower()


class IdentityCorrelationService:
    """Minimal identity correlation service for agent and Azure sync.

    This implementation is intentionally lightweight: it will not fail imports
    and will safely no-op when full backend correlation is not available.
    """

    @staticmethod
    def correlate_agent_payload(
        tenant_id,
        server_id,
        hostname,
        serial_number,
        logged_in_user
    ):
        try:
            if not tenant_id or not server_id:
                return

            if not logged_in_user:
                return

            from sqlalchemy import or_
            from web.models import db, Employee, EmployeeAssetLog

            normalized_user = IdentityCorrelationService.normalize_userprincipal(logged_in_user)
            employee = Employee.query.filter(
                Employee.tenant_id == tenant_id,
                or_(Employee.local_username == normalized_user, Employee.email == normalized_user)
            ).first()

            if not employee:
                return

            asset_log = EmployeeAssetLog(
                server_id=server_id,
                tenant_id=tenant_id,
                employee_id=str(employee.id),
                employee_email=employee.email or normalized_user,
                hostname=hostname or '',
                ip_address='',
                os_info='',
                domain='',
                device_type='agent',
                login_timestamp=datetime.utcnow()
            )
            db.session.add(asset_log)
            db.session.commit()
        except Exception as exc:
            logger.debug(f"IdentityCorrelationService no-op correlation: {exc}")
            try:
                from web.models import db
                db.session.rollback()
            except Exception:
                pass

    @staticmethod
    def resolve_device_ownership(tenant_id):
        try:
            logger.debug(f"IdentityCorrelationService.resolve_device_ownership({tenant_id}) called")
        except Exception:
            pass
