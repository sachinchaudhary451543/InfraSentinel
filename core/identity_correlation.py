"""
Identity Correlation Engine
Resolves mapping between PowerShell Agents (Server), Azure/Intune Devices (AzureDevice),
and Employees (AzureUser / Employee).
"""

from datetime import datetime
from sqlalchemy import or_
import logging

from web.models import db, EmployeeDeviceAssignment, Employee, Server, AzureDevice, AzureUser

logger = logging.getLogger(__name__)


def normalize_hostname(hostname: str) -> str:
    """Normalize hostname for consistent matching across services."""
    if not hostname:
        return ""
    return hostname.lower().strip()


class IdentityCorrelationService:
    
    @staticmethod
    def correlate_agent_payload(tenant_id: int, server_id: int, hostname: str, serial_number: str, logged_in_user: str) -> None:
        """
        Called when an agent heartbeat or metrics payload is received.
        Attempts to stitch the identity together and maintain EmployeeDeviceAssignment.
        """
        if not logged_in_user:
            return
        
        # 1. Find or resolve the Employee
        # The logged_in_user might be DOMAIN\username, username, or email
        clean_user = logged_in_user.split("\\")[-1].lower() if "\\" in logged_in_user else logged_in_user.lower()
        
        # Skip system or background accounts
        if clean_user in ('system', 'local system', 'network service', 'local service', 'administrator', 'admin'):
            return
        
        # Try to find Employee
        employee = Employee.query.filter_by(tenant_id=tenant_id, local_username=clean_user).first()
        if not employee:
            # Check if there's an AzureUser we can map to
            azure_user = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                or_(
                    AzureUser.email.ilike(f"{clean_user}%"),
                    AzureUser.employee_id.ilike(f"{clean_user}%")
                )
            ).first()
            
            if azure_user:
                # Create Employee record from AzureUser
                employee = Employee(
                    tenant_id=tenant_id,
                    name=azure_user.display_name or clean_user,
                    email=azure_user.email,
                    local_username=clean_user,
                    department=azure_user.department,
                    designation=azure_user.job_title
                )
                db.session.add(employee)
                db.session.commit()
            else:
                # Create a placeholder employee
                employee = Employee(
                    tenant_id=tenant_id,
                    name=clean_user,
                    email=f"{clean_user}@unknown.local",
                    local_username=clean_user
                )
                db.session.add(employee)
                db.session.commit()
        
        # 2. Find AzureDevice (optional, best effort mapping by hostname)
        azure_device = AzureDevice.query.filter(
            AzureDevice.tenant_id == tenant_id,
            AzureDevice.display_name.ilike(hostname)
        ).first()

        # 3. Resolve Assignment
        # Check if an active assignment already exists for this server + employee
        existing_assignment = EmployeeDeviceAssignment.query.filter_by(
            tenant_id=tenant_id,
            server_id=server_id,
            employee_id=employee.id,
            is_active=True
        ).first()

        if existing_assignment:
            # Update azure_device_id if we just found it and didn't have it
            if azure_device and not existing_assignment.azure_device_id:
                existing_assignment.azure_device_id = azure_device.id
                db.session.commit()
            return
            
        # If we got here, this is a new assignment or ownership changed
        # Deactivate previous active assignments for this server
        previous_assignments = EmployeeDeviceAssignment.query.filter_by(
            tenant_id=tenant_id,
            server_id=server_id,
            is_active=True
        ).all()
        
        for pa in previous_assignments:
            pa.is_active = False
            pa.unassigned_at = datetime.utcnow()
            
        # Create new assignment
        new_assignment = EmployeeDeviceAssignment(
            tenant_id=tenant_id,
            employee_id=employee.id,
            server_id=server_id,
            azure_device_id=azure_device.id if azure_device else None,
            assigned_at=datetime.utcnow(),
            assignment_source='agent_heartbeat',
            is_active=True
        )
        db.session.add(new_assignment)
        db.session.commit()
        
        logger.info(f"Correlated Device Assignment: Server {server_id} -> Employee {employee.id} ({clean_user})")

    @staticmethod
    def resolve_device_ownership(tenant_id: int) -> None:
        """
        Background job to cross-reference Intune/Azure Owners and map them
        to our EmployeeDeviceAssignment if they aren't already mapped by agents.
        """
        from web.models import AzureDeviceOwner, AzureUser
        
        # Get all device owners for this tenant
        owners = AzureDeviceOwner.query.filter_by(tenant_id=tenant_id).all()
        for owner in owners:
            azure_device = AzureDevice.query.get(owner.device_id)
            azure_user = AzureUser.query.get(owner.user_id)
            if not azure_device or not azure_user:
                continue
                
            # Try to match an employee
            clean_user = azure_user.email.split('@')[0].lower() if azure_user.email else ""
            employee = Employee.query.filter(
                Employee.tenant_id == tenant_id,
                or_(
                    Employee.email == azure_user.email,
                    Employee.local_username == clean_user
                )
            ).first()
            
            if not employee:
                employee = Employee(
                    tenant_id=tenant_id,
                    name=azure_user.display_name or clean_user,
                    email=azure_user.email or f"{clean_user}@unknown.local",
                    local_username=clean_user,
                    department=azure_user.department,
                    designation=azure_user.job_title
                )
                db.session.add(employee)
                db.session.commit()
                
            # Try to match a Server (Agent) by hostname matching device name
            server = Server.query.filter(
                Server.tenant_id == tenant_id,
                Server.hostname.ilike(azure_device.display_name)
            ).first()
            
            # Check existing active assignment
            existing = EmployeeDeviceAssignment.query.filter_by(
                tenant_id=tenant_id,
                azure_device_id=azure_device.id,
                is_active=True
            ).first()
            
            if existing:
                # If existing is missing server but we found it
                if server and not existing.server_id:
                    existing.server_id = server.id
                    db.session.commit()
                # If ownership changed
                if existing.employee_id != employee.id:
                    existing.is_active = False
                    existing.unassigned_at = datetime.utcnow()
                    
                    new_assignment = EmployeeDeviceAssignment(
                        tenant_id=tenant_id,
                        employee_id=employee.id,
                        server_id=server.id if server else None,
                        azure_device_id=azure_device.id,
                        assigned_at=datetime.utcnow(),
                        assignment_source='intune_sync',
                        is_active=True
                    )
                    db.session.add(new_assignment)
                    db.session.commit()
            else:
                # Create new assignment
                new_assignment = EmployeeDeviceAssignment(
                    tenant_id=tenant_id,
                    employee_id=employee.id,
                    server_id=server.id if server else None,
                    azure_device_id=azure_device.id,
                    assigned_at=datetime.utcnow(),
                    assignment_source='intune_sync',
                    is_active=True
                )
                db.session.add(new_assignment)
                db.session.commit()
        
        logger.info(f"Resolved device ownerships for tenant {tenant_id}")
