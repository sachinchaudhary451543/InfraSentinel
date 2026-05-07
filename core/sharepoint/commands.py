"""
Remote Command Executor - Execute commands via SharePoint lists
"""

import logging
import uuid
from typing import Optional
from datetime import datetime
from .client import SharePointClient
from .models import CommandItem, ListType

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Execute commands on remote servers via SharePoint"""
    
    def __init__(self, client: SharePointClient):
        """
        Initialize command executor.
        
        Args:
            client: SharePointClient instance
        """
        self.client = client
        self.commands_list = ListType.COMMANDS.value
        self.vms_list = ListType.VMS.value
    
    def queue_command(self, server_name: str, command: str) -> Optional[str]:
        """
        Queue a command for remote execution.
        
        Args:
            server_name: Name of target server
            command: Command to execute
            
        Returns:
            Command ID or None if failed
        """
        try:
            command_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().isoformat()
            
            cmd_item = CommandItem(
                command_id=command_id,
                server_name=server_name,
                command=command,
                status="queued",
                timestamp=timestamp
            )
            
            item = self.client.add_item(self.commands_list, **cmd_item.to_dict())
            if item:
                logger.info(f"Queued command '{command_id}' on '{server_name}'")
                return command_id
            return None
        except Exception as e:
            logger.error(f"Failed to queue command on '{server_name}': {e}")
            return None
    
    def get_command_status(self, command_id: str) -> Optional[str]:
        """
        Get status of queued command.
        
        Args:
            command_id: ID of the command
            
        Returns:
            Status string or None if not found
        """
        try:
            filter_str = f"CommandID eq '{command_id}'"
            items = self.client.get_items(self.commands_list, filter_str=filter_str)
            
            if items:
                return items[0].get('Status')
            return None
        except Exception as e:
            logger.error(f"Failed to get status for command '{command_id}': {e}")
            return None
    
    def get_command_output(self, command_id: str) -> Optional[str]:
        """
        Get output of executed command.
        
        Args:
            command_id: ID of the command
            
        Returns:
            Output string or None if not found
        """
        try:
            filter_str = f"CommandID eq '{command_id}'"
            items = self.client.get_items(self.commands_list, filter_str=filter_str)
            
            if items:
                return items[0].get('Output')
            return None
        except Exception as e:
            logger.error(f"Failed to get output for command '{command_id}': {e}")
            return None
    
    def update_command(
        self,
        command_id: str,
        status: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Update command with execution results.
        
        Args:
            command_id: ID of the command
            status: New status
            output: Command output
            error: Error message
            
        Returns:
            True if successful
        """
        try:
            # Find command by ID
            filter_str = f"CommandID eq '{command_id}'"
            items = self.client.get_items(self.commands_list, filter_str=filter_str)
            
            if not items:
                logger.warning(f"Command '{command_id}' not found")
                return False
            
            item_id = items[0].get('ID')
            
            # Prepare update
            updates = {}
            if status:
                updates['Status'] = status
            if output:
                updates['Output'] = output
            if error:
                updates['Error'] = error
            
            # Update item
            self.client.update_item(self.commands_list, item_id, **updates)
            logger.info(f"Updated command '{command_id}' with status '{status}'")
            return True
        except Exception as e:
            logger.error(f"Failed to update command '{command_id}': {e}")
            return False
    
    def execute_remote_command(self, server_name: str, command: str) -> bool:
        """
        Execute command on remote server.
        
        This is the main method for command execution.
        Queues command and returns immediately (async execution).
        
        Args:
            server_name: Name of target server
            command: Command to execute
            
        Returns:
            True if command queued successfully
        """
        try:
            command_id = self.queue_command(server_name, command)
            return command_id is not None
        except Exception as e:
            logger.error(f"Failed to execute command on '{server_name}': {e}")
            return False
    
    def handle_vm_operations(self, vm_name: str, operation: str) -> bool:
        """
        Execute VM operations (start, stop, restart).
        
        Args:
            vm_name: Name of the virtual machine
            operation: Operation to perform (start, stop, restart)
            
        Returns:
            True if successful
        """
        try:
            if operation not in ['start', 'stop', 'restart']:
                logger.error(f"Invalid VM operation: {operation}")
                return False
            
            # Queue command to host server
            command = f"Hyper-V VM {operation}: {vm_name}"
            
            # Find VM and get host server
            filter_str = f"VMName eq '{vm_name}'"
            vms = self.client.get_items(self.vms_list, filter_str=filter_str)
            
            if not vms:
                logger.warning(f"VM '{vm_name}' not found")
                return False
            
            host_server = vms[0].get('HostServer')
            
            # Queue operation on host
            return self.execute_remote_command(host_server, command)
        except Exception as e:
            logger.error(f"Failed to handle VM operation '{operation}' on '{vm_name}': {e}")
            return False
    
    def get_pending_commands(self, server_name: str) -> list:
        """
        Get all pending commands for a server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            List of pending commands
        """
        try:
            filter_str = f"ServerName eq '{server_name}' and Status eq 'queued'"
            items = self.client.get_items(self.commands_list, filter_str=filter_str)
            logger.debug(f"Found {len(items)} pending commands for '{server_name}'")
            return items
        except Exception as e:
            logger.error(f"Failed to get pending commands for '{server_name}': {e}")
            return []
