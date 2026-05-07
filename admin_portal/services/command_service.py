"""
Command Service
Handles command queuing and execution logic
"""

import logging
from admin_portal.models import db, RemoteCommand
from sqlalchemy import desc, and_
from datetime import datetime

logger = logging.getLogger(__name__)


class CommandService:
    """Service for command operations"""
    
    @staticmethod
    def create_command(server_id, command, parameters=None, tenant_id=None):
        """Create a new command"""
        try:
            cmd = RemoteCommand(
                server_id=server_id,
                tenant_id=tenant_id,
                command=command,
                parameters=parameters,
                status='pending',
                created_at=datetime.utcnow()
            )
            db.session.add(cmd)
            db.session.commit()
            logger.info(f"Command created: {command} for server {server_id}")
            return cmd
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating command: {e}")
            return None
    
    @staticmethod
    def get_command(command_id):
        """Get command by ID"""
        try:
            return RemoteCommand.query.filter_by(id=command_id).first()
        except Exception as e:
            logger.error(f"Error fetching command {command_id}: {e}")
            return None
    
    @staticmethod
    def get_command_history(server_id, limit=50):
        """Get command history for a system"""
        try:
            return RemoteCommand.query.filter_by(
                server_id=server_id
            ).order_by(desc(RemoteCommand.created_at)).limit(limit).all()
        except Exception as e:
            logger.error(f"Error fetching command history: {e}")
            return []
    
    @staticmethod
    def get_pending_commands(server_id):
        """Get pending commands for a system"""
        try:
            return RemoteCommand.query.filter(
                RemoteCommand.server_id == server_id,
                RemoteCommand.status == 'pending'
            ).order_by(RemoteCommand.created_at).all()
        except Exception as e:
            logger.error(f"Error fetching pending commands: {e}")
            return []
    
    @staticmethod
    def update_command_status(command_id, status, output=None, error=None):
        """Update command status and output"""
        try:
            cmd = RemoteCommand.query.filter_by(id=command_id).first()
            if not cmd:
                return False
            
            cmd.status = status
            if output:
                cmd.output = output
            if error:
                cmd.error = error
            if status in ['completed', 'failed']:
                cmd.executed_at = datetime.utcnow()
            
            db.session.commit()
            logger.debug(f"Command {command_id} status updated to {status}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating command status: {e}")
            return False
    
    @staticmethod
    def cancel_command(command_id):
        """Cancel a pending command"""
        try:
            cmd = RemoteCommand.query.filter_by(id=command_id).first()
            if not cmd:
                return False
            
            if cmd.status == 'pending':
                cmd.status = 'cancelled'
                db.session.commit()
                logger.info(f"Command {command_id} cancelled")
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling command: {e}")
            return False
    
    @staticmethod
    def get_command_count(server_id, status=None):
        """Get command count for a system"""
        try:
            query = RemoteCommand.query.filter_by(server_id=server_id)
            if status:
                query = query.filter_by(status=status)
            return query.count()
        except Exception as e:
            logger.error(f"Error counting commands: {e}")
            return 0
    
    @staticmethod
    def get_pending_command_count(tenant_id=None):
        """Get total pending command count"""
        try:
            query = RemoteCommand.query.filter_by(status='pending')
            if tenant_id:
                query = query.filter_by(tenant_id=tenant_id)
            return query.count()
        except Exception as e:
            logger.error(f"Error counting pending commands: {e}")
            return 0
    
    @staticmethod
    def cleanup_old_commands(days=60):
        """Delete completed commands older than specified days"""
        try:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            deleted = db.session.query(RemoteCommand).filter(
                and_(
                    RemoteCommand.status.in_(['completed', 'failed', 'cancelled']),
                    RemoteCommand.created_at < cutoff_time
                )
            ).delete()
            db.session.commit()
            logger.info(f"Deleted {deleted} old command records")
            return deleted
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cleaning up old commands: {e}")
            return 0
