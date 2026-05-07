"""
Deployment Manager - Software and update deployment system

Manages centralized software deployment to multiple systems
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DeploymentStatus(Enum):
    """Deployment lifecycle status"""
    CREATED = "Created"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    ROLLED_BACK = "RolledBack"


@dataclass
class DeploymentJob:
    """Represents a deployment job"""
    job_id: str
    software_name: str
    software_version: str
    installer_url: str
    installer_type: str  # msi, exe, ps1
    silent_args: str
    target_systems: List[str]
    status: DeploymentStatus = DeploymentStatus.CREATED
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_by: str = ""
    description: str = ""
    max_parallel: int = 5
    retry_on_failure: bool = True
    rollback_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['status'] = self.status.value
        return data


@dataclass
class DeploymentSystemStatus:
    """Status of deployment on a single system"""
    system_name: str
    job_id: str
    status: str  # pending, in_progress, success, failed
    exit_code: int = 0
    error_message: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempts: int = 0


class DeploymentManager:
    """
    Manage software and update deployment to systems
    """
    
    def __init__(self, storage_dir: str = "./data/deployments"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        self.jobs: Dict[str, DeploymentJob] = {}
        self.job_results: Dict[str, List[DeploymentSystemStatus]] = {}
    
    def create_deployment(
        self,
        software_name: str,
        software_version: str,
        installer_url: str,
        installer_type: str,
        silent_args: str,
        target_systems: List[str],
        description: str = "",
        created_by: str = "admin"
    ) -> str:
        """
        Create a new deployment job
        
        Args:
            software_name: Name of software
            software_version: Version to deploy
            installer_url: URL or path to installer
            installer_type: msi, exe, or ps1
            silent_args: Silent installation arguments
            target_systems: List of systems to deploy to
            description: Job description
            created_by: User creating job
            
        Returns:
            Job ID
        """
        import secrets
        job_id = f"deploy_{software_name}_{secrets.token_hex(8)}"
        
        job = DeploymentJob(
            job_id=job_id,
            software_name=software_name,
            software_version=software_version,
            installer_url=installer_url,
            installer_type=installer_type,
            silent_args=silent_args,
            target_systems=target_systems,
            created_at=datetime.utcnow().isoformat(),
            created_by=created_by,
            description=description
        )
        
        self.jobs[job_id] = job
        self.job_results[job_id] = [
            DeploymentSystemStatus(
                system_name=sys_name,
                job_id=job_id,
                status="pending"
            )
            for sys_name in target_systems
        ]
        
        self._persist_job(job)
        logger.info(f"Created deployment job {job_id} for {len(target_systems)} systems")
        
        return job_id
    
    def update_system_status(
        self,
        job_id: str,
        system_name: str,
        status: str,
        exit_code: int = 0,
        error_message: str = ""
    ) -> bool:
        """Update deployment status for a specific system"""
        if job_id not in self.job_results:
            logger.error(f"Job {job_id} not found")
            return False
        
        results = self.job_results[job_id]
        for result in results:
            if result.system_name == system_name:
                result.status = status
                result.exit_code = exit_code
                result.error_message = error_message
                
                if status == "in_progress":
                    result.started_at = datetime.utcnow().isoformat()
                    result.attempts += 1
                elif status in ("success", "failed"):
                    result.completed_at = datetime.utcnow().isoformat()
                
                return True
        
        return False
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get overall status of deployment job"""
        if job_id not in self.jobs:
            return {"error": "Job not found"}
        
        job = self.jobs[job_id]
        results = self.job_results.get(job_id, [])
        
        completed = sum(1 for r in results if r.status in ("success", "failed"))
        successful = sum(1 for r in results if r.status == "success")
        failed = sum(1 for r in results if r.status == "failed")
        pending = sum(1 for r in results if r.status == "pending")
        in_progress = sum(1 for r in results if r.status == "in_progress")
        
        # Update job status
        if completed == len(results):
            if failed == 0:
                job.status = DeploymentStatus.COMPLETED
            else:
                job.status = DeploymentStatus.FAILED
            job.completed_at = datetime.utcnow().isoformat()
        elif in_progress > 0:
            job.status = DeploymentStatus.IN_PROGRESS
            if not job.started_at:
                job.started_at = datetime.utcnow().isoformat()
        
        return {
            "job_id": job_id,
            "software": f"{job.software_name} v{job.software_version}",
            "status": job.status.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "progress": {
                "total": len(results),
                "completed": completed,
                "successful": successful,
                "failed": failed,
                "pending": pending,
                "in_progress": in_progress,
                "completion_percentage": int((completed / len(results) * 100)) if results else 0
            },
            "system_results": [asdict(r) for r in results]
        }
    
    def get_pending_deployments(self) -> List[DeploymentJob]:
        """Get all pending deployments"""
        return [
            job for job in self.jobs.values()
            if job.status in (DeploymentStatus.CREATED, DeploymentStatus.IN_PROGRESS)
        ]
    
    def _persist_job(self, job: DeploymentJob) -> bool:
        """Save job to storage"""
        try:
            filepath = os.path.join(self.storage_dir, f"{job.job_id}.json")
            with open(filepath, 'w') as f:
                json.dump(job.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to persist job: {e}")
            return False
    
    def list_deployments(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent deployments"""
        deployments = []
        for job_id, _ in sorted(
            self.jobs.items(),
            key=lambda x: x[1].created_at,
            reverse=True
        )[:limit]:
            deployments.append(self.get_job_status(job_id))
        return deployments
