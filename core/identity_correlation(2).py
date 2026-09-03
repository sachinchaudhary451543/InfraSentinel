"""
Identity Correlation Engine
Resolves mapping between PowerShell Agents (Server), Azure/Intune Devices (AzureDevice),
and Employees (AzureUser / Employee).
"""
from datetime import datetime
import logging

from sqlalchemy import func, or_

from web.models import (
    db,
    EmployeeDeviceAssignment,
    Employee,
    Server,
    AzureDevice,
    AzureDeviceOwner,
    AzureUser,
)

logger = logging.getLogger(__name__)


def normalize_hostname(hostname: str) -> str:
    """Normalize hostnames for agent, Entra ID, and FQDN comparisons."""
    if not hostname:
        return ""
    short_name = str(hostname).strip().split(".")[0]
    return short_name.replace("_", "-").lower()


def _clean_logged_in_user(logged_in_user: str) -> str:
    user = (logged_in_user or "").strip()
    if "\\" in user:
        user = user.split("\\")[-1]
    return user.lower()


def _user_prefix(value: str) -> str:
    value = _clean_logged_in_user(value)
    return value.split("@", 1)[0] if "@" in value else value


def _compact(value: str) -> str:
    return (value or "").lower().replace(".", "").replace("_", "").replace("-", "")


class IdentityCorrelationService:
    @staticmethod
    def _find_azure_device(tenant_id: int, hostname: str):
        normalized = normalize_hostname(hostname)
        if not normalized:
            return None

        device = AzureDevice.query.filter(
            AzureDevice.tenant_id == tenant_id,
            AzureDevice.normalized_hostname == normalized,
        ).first()
        if device:
            return device

        candidates = AzureDevice.query.filter(
            AzureDevice.tenant_id == tenant_id,
            or_(
                func.lower(AzureDevice.display_name) == hostname.lower(),
                AzureDevice.display_name.ilike(f"{normalized}.%"),
                AzureDevice.display_name.ilike(normalized.replace("-", "_")),
            ),
        ).all()
        for candidate in candidates:
            if normalize_hostname(candidate.display_name) == normalized:
                candidate.normalized_hostname = normalized
                return candidate
        return None

    @staticmethod
    def _find_azure_user(tenant_id: int, logged_in_user: str, azure_device=None):
        clean_user = _clean_logged_in_user(logged_in_user)
        prefix = _user_prefix(clean_user)

        if "@" in clean_user:
            user = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                func.lower(AzureUser.email) == clean_user,
            ).first()
            if user:
                return user, "email_upn"

        if prefix:
            compact_prefix = _compact(prefix)
            user = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                or_(
                    func.lower(AzureUser.mail_nickname) == prefix,
                    func.lower(AzureUser.sam_account_name) == prefix,
                    func.lower(AzureUser.employee_id) == prefix,
                    AzureUser.email.ilike(f"{prefix}@%"),
                ),
            ).first()
            if user:
                return user, "local_username"

            for candidate in AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                or_(
                    AzureUser.employee_id.isnot(None),
                    AzureUser.mail_nickname.isnot(None),
                    AzureUser.email.isnot(None),
                ),
            ).all():
                candidate_keys = {
                    _compact(candidate.employee_id),
                    _compact(candidate.mail_nickname),
                    _compact((candidate.email or "").split("@", 1)[0]),
                }
                if compact_prefix and compact_prefix in candidate_keys:
                    return candidate, "local_username_compact"

        if azure_device:
            owner = AzureDeviceOwner.query.filter(
                AzureDeviceOwner.tenant_id == tenant_id,
                or_(
                    AzureDeviceOwner.device_id == azure_device.id,
                    AzureDeviceOwner.device_id == azure_device.device_id,
                ),
            ).first()
            if owner:
                user = db.session.get(AzureUser, int(owner.user_id)) if str(owner.user_id).isdigit() else None
                if not user:
                    user = AzureUser.query.filter_by(tenant_id=tenant_id, user_id=owner.user_id).first()
                if user:
                    return user, "hostname_device_owner"

        return None, "unmatched"

    @staticmethod
    def _upsert_employee_from_azure(tenant_id: int, azure_user, local_username: str):
        email = (azure_user.email or "").lower()
        employee = Employee.query.filter(
            Employee.tenant_id == tenant_id,
            or_(
                Employee.azure_user_id == azure_user.user_id,
                func.lower(Employee.email) == email,
                func.lower(Employee.local_username) == local_username,
            ),
        ).first()

        display_name = azure_user.display_name or email or local_username
        if not employee:
            employee = Employee(
                tenant_id=tenant_id,
                name=display_name,
                email=email or f"{local_username}@unknown.local",
                local_username=local_username,
            )
            db.session.add(employee)

        employee.name = display_name
        employee.display_name = display_name
        employee.email = email or employee.email
        employee.department = azure_user.department
        employee.designation = azure_user.job_title
        employee.azure_user_id = azure_user.user_id
        if local_username and not employee.local_username:
            employee.local_username = local_username
        return employee

    @staticmethod
    def _get_or_create_placeholder_employee(tenant_id: int, logged_in_user: str):
        clean_user = _user_prefix(logged_in_user)
        employee = Employee.query.filter_by(tenant_id=tenant_id, local_username=clean_user).first()
        if employee:
            return employee

        employee = Employee(
            tenant_id=tenant_id,
            name=clean_user,
            display_name=clean_user,
            email=f"{clean_user}@unknown.local",
            local_username=clean_user,
        )
        db.session.add(employee)
        return employee

    @staticmethod
    def correlate_agent_payload(tenant_id: int, server_id: int, hostname: str, serial_number: str, logged_in_user: str) -> None:
        """
        Called when an agent heartbeat or metrics payload is received.
        Attempts to stitch the identity together and maintain EmployeeDeviceAssignment.
        """
        if not logged_in_user:
            logger.info(
                "identity_correlation_failed",
                extra={
                    "hostname": hostname,
                    "logged_in_user": logged_in_user,
                    "matched_strategy": "missing_logged_in_user",
                    "azure_user_id": None,
                },
            )
            return

        clean_user = _user_prefix(logged_in_user)
        azure_device = IdentityCorrelationService._find_azure_device(tenant_id, hostname)
        azure_user, strategy = IdentityCorrelationService._find_azure_user(
            tenant_id,
            logged_in_user,
            azure_device=azure_device,
        )

        if azure_user:
            employee = IdentityCorrelationService._upsert_employee_from_azure(
                tenant_id,
                azure_user,
                clean_user,
            )
        else:
            employee = IdentityCorrelationService._get_or_create_placeholder_employee(
                tenant_id,
                logged_in_user,
            )

        existing_assignment = EmployeeDeviceAssignment.query.filter_by(
            tenant_id=tenant_id,
            server_id=server_id,
            employee_id=employee.id,
            is_active=True,
        ).first()

        if existing_assignment:
            if azure_device and existing_assignment.azure_device_id != azure_device.id:
                existing_assignment.azure_device_id = azure_device.id
            db.session.commit()
            logger.info(
                "identity_correlation",
                extra={
                    "hostname": hostname,
                    "logged_in_user": logged_in_user,
                    "matched_strategy": f"{strategy}:cached_assignment",
                    "azure_user_id": azure_user.user_id if azure_user else None,
                },
            )
            return

        previous_assignments = EmployeeDeviceAssignment.query.filter_by(
            tenant_id=tenant_id,
            server_id=server_id,
            is_active=True,
        ).all()
        for assignment in previous_assignments:
            assignment.is_active = False
            assignment.unassigned_at = datetime.utcnow()

        new_assignment = EmployeeDeviceAssignment(
            tenant_id=tenant_id,
            employee_id=employee.id,
            server_id=server_id,
            azure_device_id=azure_device.id if azure_device else None,
            assigned_at=datetime.utcnow(),
            assignment_source='agent_heartbeat' if strategy != "hostname_device_owner" else "agent_heartbeat_device_owner",
            is_active=True,
        )
        db.session.add(new_assignment)
        db.session.commit()

        logger.info(
            "identity_correlation",
            extra={
                "hostname": hostname,
                "logged_in_user": logged_in_user,
                "matched_strategy": strategy,
                "azure_user_id": azure_user.user_id if azure_user else None,
            },
        )
        if not azure_user:
            logger.warning(
                "identity_correlation_failed",
                extra={
                    "hostname": hostname,
                    "logged_in_user": logged_in_user,
                    "matched_strategy": "placeholder_employee",
                    "azure_user_id": None,
                },
            )

    @staticmethod
    def resolve_device_ownership(tenant_id: int) -> None:
        """
        Background job to cross-reference Intune/Azure Owners and map them
        to our EmployeeDeviceAssignment if they aren't already mapped by agents.
        """
        owners = AzureDeviceOwner.query.filter_by(tenant_id=tenant_id).all()
        resolved_count = 0
        for owner in owners:
            azure_device = db.session.get(AzureDevice, int(owner.device_id)) if str(owner.device_id).isdigit() else None
            if not azure_device:
                azure_device = AzureDevice.query.filter_by(tenant_id=tenant_id, device_id=owner.device_id).first()

            azure_user = db.session.get(AzureUser, int(owner.user_id)) if str(owner.user_id).isdigit() else None
            if not azure_user:
                azure_user = AzureUser.query.filter_by(tenant_id=tenant_id, user_id=owner.user_id).first()
            if not azure_device or not azure_user:
                logger.warning(
                    "identity_correlation_failed",
                    extra={
                        "hostname": azure_device.display_name if azure_device else None,
                        "logged_in_user": None,
                        "matched_strategy": "stale_device_owner",
                        "azure_user_id": azure_user.user_id if azure_user else None,
                    },
                )
                continue

            clean_user = _user_prefix(azure_user.email or azure_user.employee_id or "")
            employee = IdentityCorrelationService._upsert_employee_from_azure(
                tenant_id,
                azure_user,
                clean_user,
            )

            normalized = normalize_hostname(azure_device.display_name)
            server = Server.query.filter(
                Server.tenant_id == tenant_id,
                or_(
                    func.lower(Server.hostname) == normalized,
                    Server.hostname.ilike(f"{normalized}.%"),
                    Server.hostname.ilike(normalized.replace("-", "_")),
                ),
            ).first()

            existing = EmployeeDeviceAssignment.query.filter_by(
                tenant_id=tenant_id,
                azure_device_id=azure_device.id,
                is_active=True,
            ).first()

            if existing:
                if server and not existing.server_id:
                    existing.server_id = server.id
                if existing.employee_id != employee.id:
                    existing.is_active = False
                    existing.unassigned_at = datetime.utcnow()
                    existing = None

            if not existing:
                db.session.add(EmployeeDeviceAssignment(
                    tenant_id=tenant_id,
                    employee_id=employee.id,
                    server_id=server.id if server else None,
                    azure_device_id=azure_device.id,
                    assigned_at=datetime.utcnow(),
                    assignment_source='intune_sync',
                    is_active=True,
                ))
                resolved_count += 1

            logger.info(
                "identity_correlation",
                extra={
                    "hostname": azure_device.display_name,
                    "logged_in_user": azure_user.email,
                    "matched_strategy": "device_owner_sync",
                    "azure_user_id": azure_user.user_id,
                },
            )

        db.session.commit()
        logger.info("Resolved device ownerships for tenant %s (%s new mappings)", tenant_id, resolved_count)
