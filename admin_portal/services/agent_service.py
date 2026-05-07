"""
Agent Service
Handles agent management and connectivity
"""

import logging
from admin_portal.models import db, AgentKey
from sqlalchemy import desc
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent operations"""
    
    @staticmethod
    def get_all_agent_keys(tenant_id):
        """Get all agent keys for a tenant"""
        try:
            return AgentKey.query.filter_by(tenant_id=tenant_id).all()
        except Exception as e:
            logger.error(f"Error fetching agent keys: {e}")
            return []
    
    @staticmethod
    def get_agent_key(key_id, tenant_id):
        """Get agent key by ID with authorization"""
        try:
            return AgentKey.query.filter_by(
                id=key_id,
                tenant_id=tenant_id
            ).first()
        except Exception as e:
            logger.error(f"Error fetching agent key: {e}")
            return None
    
    @staticmethod
    def create_agent_key(tenant_id, description=None, is_active=True):
        """Create a new agent key"""
        try:
            import uuid
            key_string = str(uuid.uuid4())
            
            agent_key = AgentKey(
                key=key_string,
                tenant_id=tenant_id,
                description=description or f"Agent Key {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                is_active=is_active
            )
            db.session.add(agent_key)
            db.session.commit()
            logger.info(f"Agent key created for tenant {tenant_id}")
            return agent_key
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating agent key: {e}")
            return None
    
    @staticmethod
    def revoke_agent_key(key_id, tenant_id):
        """Revoke (deactivate) an agent key"""
        try:
            agent_key = AgentKey.query.filter_by(
                id=key_id,
                tenant_id=tenant_id
            ).first()
            
            if not agent_key:
                return False
            
            agent_key.is_active = False
            db.session.commit()
            logger.info(f"Agent key {key_id} revoked")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error revoking agent key: {e}")
            return False
    
    @staticmethod
    def verify_agent_key(key_string):
        """Verify if an agent key is valid and active"""
        try:
            agent_key = AgentKey.query.filter_by(
                key=key_string,
                is_active=True
            ).first()
            return agent_key is not None
        except Exception as e:
            logger.error(f"Error verifying agent key: {e}")
            return False
    
    @staticmethod
    def get_agent_key_count(tenant_id):
        """Get count of agent keys for a tenant"""
        try:
            return AgentKey.query.filter_by(tenant_id=tenant_id).count()
        except Exception as e:
            logger.error(f"Error counting agent keys: {e}")
            return 0
    
    @staticmethod
    def get_active_agent_count(tenant_id):
        """Get count of active agent keys for a tenant"""
        try:
            return AgentKey.query.filter_by(
                tenant_id=tenant_id,
                is_active=True
            ).count()
        except Exception as e:
            logger.error(f"Error counting active agent keys: {e}")
            return 0
    
    @staticmethod
    def update_agent_key_description(key_id, tenant_id, description):
        """Update agent key description"""
        try:
            agent_key = AgentKey.query.filter_by(
                id=key_id,
                tenant_id=tenant_id
            ).first()
            
            if not agent_key:
                return False
            
            agent_key.description = description
            db.session.commit()
            logger.info(f"Agent key {key_id} description updated")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating agent key description: {e}")
            return False
