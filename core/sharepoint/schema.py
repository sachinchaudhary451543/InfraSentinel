"""
SharePoint Schema Manager - Single source of truth for list definitions

Ensures all lists and their columns are created and maintained consistently
across the entire application. No duplicate list creation logic anywhere else.
"""

import logging
from typing import List, Dict, Any
from .client import SharePointClient
from .models import ListType, SchemaDefinition

logger = logging.getLogger(__name__)


class SchemaManager:
    """
    Manage SharePoint lists and schema.
    
    This is the SINGLE SOURCE OF TRUTH for list creation and maintenance.
    All list creation must go through this class to avoid duplicates.
    """
    
    def __init__(self, client: SharePointClient):
        """
        Initialize schema manager.
        
        Args:
            client: SharePointClient instance
        """
        self.client = client
    
    def setup_metrics_summary_list(self) -> bool:
        """
        Create/ensure ServerMetricsSummary list.
        
        Returns:
            True if successful
        """
        list_name = ListType.METRICS_SUMMARY.value
        description = "Current server metrics summary"
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, SchemaDefinition.METRICS_SUMMARY_SCHEMA[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_metrics_history_list(self) -> bool:
        """
        Create/ensure ServerMetricsHistory list.
        
        Returns:
            True if successful
        """
        list_name = ListType.METRICS_HISTORY.value
        description = "Historical server metrics"
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, SchemaDefinition.METRICS_HISTORY_SCHEMA[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_vms_list(self) -> bool:
        """
        Create/ensure ServerVMs list.
        
        Returns:
            True if successful
        """
        list_name = ListType.VMS.value
        description = "Virtual machine inventory"
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, SchemaDefinition.VMS_SCHEMA[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_agents_list(self) -> bool:
        """
        Create/ensure RegisteredAgents list.
        
        Returns:
            True if successful
        """
        list_name = ListType.AGENTS.value
        description = "Registered monitoring agents"
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, SchemaDefinition.AGENTS_SCHEMA[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_commands_list(self) -> bool:
        """
        Create/ensure RemoteCommands list.
        
        Returns:
            True if successful
        """
        list_name = ListType.COMMANDS.value
        description = "Remote command execution queue"
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, SchemaDefinition.COMMANDS_SCHEMA[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_discovered_systems_list(self) -> bool:
        """
        Create/ensure DiscoveredSystems list.
        
        Returns:
            True if successful
        """
        list_name = ListType.DISCOVERED.value
        description = "Systems discovered from Active Directory"
        
        schema = {
            list_name: [
                {"name": "Hostname", "type": "Text", "required": True},
                {"name": "IPAddress", "type": "Text"},
                {"name": "OSName", "type": "Text"},
                {"name": "OSVersion", "type": "Text"},
                {"name": "SystemType", "type": "Text"},
                {"name": "Domain", "type": "Text"},
                {"name": "MACAddress", "type": "Text"},
                {"name": "DiscoveredAt", "type": "DateTime"},
                {"name": "Source", "type": "Text"},
                {"name": "Status", "type": "Text"},
            ]
        }
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, schema[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_server_control_list(self) -> bool:
        """
        Create/ensure ServerControl list.
        
        Returns:
            True if successful
        """
        list_name = ListType.SERVER_CONTROL.value
        description = "Agent control and status management"
        
        schema = {
            list_name: [
                {"name": "ServerName", "type": "Text", "required": True},
                {"name": "Status", "type": "Text"},
                {"name": "Action", "type": "Text"},
                {"name": "LastUpdated", "type": "DateTime"},
                {"name": "Reason", "type": "Text"},
            ]
        }
        
        try:
            sp_list = self.client.ensure_list(list_name, description)
            if sp_list:
                self._ensure_columns(sp_list, schema[list_name])
                logger.info(f"Ensured list '{list_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to setup '{list_name}': {e}")
            return False
    
    def setup_all_lists(self) -> bool:
        """
        Create/ensure all required lists.
        
        Returns:
            True if all successful
        """
        logger.info("Setting up all SharePoint lists...")
        
        results = [
            self.setup_metrics_summary_list(),
            self.setup_metrics_history_list(),
            self.setup_vms_list(),
            self.setup_agents_list(),
            self.setup_commands_list(),
            self.setup_discovered_systems_list(),
            self.setup_server_control_list(),
        ]
        
        success = all(results)
        if success:
            logger.info("✓ All SharePoint lists setup successfully")
        else:
            logger.warning("⚠ Some lists failed to setup")
        
        return success
    
    def _ensure_columns(self, sp_list: Any, fields: List[Dict[str, Any]]) -> bool:
        """
        Ensure all required columns exist in list.
        
        This is the SINGLE implementation of column ensure logic.
        No duplication anywhere else.
        
        Args:
            sp_list: SharePoint list object
            fields: List of field definitions
            
        Returns:
            True if successful
        """
        try:
            # Load existing fields
            sp_list.fields.get().execute_query()
            existing_fields = {f.internal_name: f for f in sp_list.fields}
            
            # Add missing fields
            for field_def in fields:
                field_name = field_def.get('name')
                field_type = field_def.get('type', 'Text')
                
                # Skip if field already exists
                if field_name in existing_fields:
                    logger.debug(f"Field '{field_name}' already exists")
                    continue
                
                # Add new field
                try:
                    sp_list.fields.add_field_as_xml(
                        f'<Field Type="{field_type}" DisplayName="{field_name}" Name="{field_name}"/>'
                    )
                    logger.info(f"Added field '{field_name}' to list")
                except Exception as e:
                    logger.warning(f"Failed to add field '{field_name}': {e}")
                    # Don't fail on individual field errors
            
            if self.client.ctx:
                self.client.ctx.execute_query()
            return True
        except Exception as e:
            logger.error(f"Failed to ensure columns: {e}")
            return False
