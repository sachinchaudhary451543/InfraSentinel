"""
SharePoint Client - Unified authentication and API access
"""

import logging
from typing import Optional
from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.client_credential import ClientCredential
from office365.runtime.auth.user_credential import UserCredential

logger = logging.getLogger(__name__)


class SharePointClient:
    """
    Unified SharePoint API client with authentication handling.
    
    Provides single interface for all SharePoint operations:
    - List management
    - Item CRUD
    - Batch operations
    """
    
    def __init__(
        self,
        site_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        """
        Initialize SharePoint client.
        
        Args:
            site_url: SharePoint site URL (https://tenant.sharepoint.com/sites/sitename)
            username: Username for basic auth (optional)
            password: Password for basic auth (optional)
            client_id: Client ID for OAuth (optional)
            client_secret: Client secret for OAuth (optional)
        """
        self.site_url = site_url
        self.ctx = None
        
        # Determine auth method and authenticate
        if client_id and client_secret:
            self._authenticate_oauth(site_url, client_id, client_secret)
        elif username and password:
            self._authenticate_basic(site_url, username, password)
        else:
            logger.warning("No authentication credentials provided")
            self.ctx = ClientContext(site_url)
    
    def _authenticate_oauth(self, site_url: str, client_id: str, client_secret: str):
        """Authenticate using OAuth 2.0 (app-only)"""
        try:
            cred = ClientCredential(client_id, client_secret)
            self.ctx = ClientContext(site_url)  # OAuth handled via credential context
            self.ctx.auth_context = cred  # type: ignore
            logger.info(f"OAuth authentication successful for {site_url}")
        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise
    
    def _authenticate_basic(self, site_url: str, username: str, password: str):
        """Authenticate using basic auth (username/password)"""
        try:
            self.ctx = ClientContext(site_url).with_credentials(
                UserCredential(username, password)
            )
            logger.info(f"Basic authentication successful for {site_url}")
        except Exception as e:
            logger.error(f"Basic authentication failed: {e}")
            raise
    
    def list_exists(self, list_title: str) -> bool:
        """
        Check if list exists.
        
        Args:
            list_title: Name of the list
            
        Returns:
            True if list exists, False otherwise
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return False
            sp_list = self.ctx.web.lists.get_by_title(list_title)
            sp_list.get().execute_query()
            return True
        except Exception as e:
            logger.debug(f"List '{list_title}' not found: {e}")
            return False
    
    def get_list(self, list_title: str):
        """
        Get reference to list.
        
        Args:
            list_title: Name of the list
            
        Returns:
            List object or None if not found
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return None
            sp_list = self.ctx.web.lists.get_by_title(list_title)
            sp_list.get().execute_query()
            return sp_list
        except Exception as e:
            logger.error(f"Failed to get list '{list_title}': {e}")
            return None
    
    def create_list(self, list_title: str, description: str = "") -> object:
        """
        Create new list.
        
        Args:
            list_title: Name for the new list
            description: List description
            
        Returns:
            Created list object or None if failed
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return None
            from office365.sharepoint.lists.creation_information import ListCreationInformation
            
            list_info = ListCreationInformation()
            list_info.Title = list_title
            list_info.Description = description
            list_info.BaseTemplate = 100  # Generic list
            
            sp_list = self.ctx.web.lists.add(list_info)
            self.ctx.execute_query()
            logger.info(f"Created list '{list_title}'")
            return sp_list
        except Exception as e:
            logger.error(f"Failed to create list '{list_title}': {e}")
            return None
    
    def ensure_list(self, list_title: str, description: str = "") -> object:
        """
        Create list if not exists.
        
        Args:
            list_title: Name of the list
            description: List description (used if creating)
            
        Returns:
            List object
        """
        if self.list_exists(list_title):
            return self.get_list(list_title)
        else:
            return self.create_list(list_title, description)
    
    def add_item(self, list_title: str, **properties) -> object:
        """
        Add item to list.
        
        Args:
            list_title: Name of the list
            **properties: Item properties (key-value pairs)
            
        Returns:
            Created item or None if failed
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return None
            sp_list = self.get_list(list_title)
            if not sp_list:
                logger.error(f"List '{list_title}' not found")
                return None
            
            item = sp_list.add_item(properties)
            self.ctx.execute_query()
            logger.debug(f"Added item to '{list_title}': {properties}")
            return item
        except Exception as e:
            logger.error(f"Failed to add item to '{list_title}': {e}")
            return None
    
    def update_item(self, list_title: str, item_id: int, **properties) -> bool:
        """
        Update list item.
        
        Args:
            list_title: Name of the list
            item_id: ID of the item to update
            **properties: Updated properties
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return False
            sp_list = self.get_list(list_title)
            if not sp_list:
                logger.error(f"List '{list_title}' not found")
                return False
            
            item = sp_list.get_item_by_id(item_id)
            item.set_property("Title", properties.get("Title", ""))
            for key, value in properties.items():
                if key != "Title":
                    item.set_property(key, value)
            self.ctx.execute_query()
            logger.debug(f"Updated item {item_id} in '{list_title}'")
            return True
        except Exception as e:
            logger.error(f"Failed to update item {item_id} in '{list_title}': {e}")
            return False
    
    def delete_item(self, list_title: str, item_id: int) -> bool:
        """
        Delete list item.
        
        Args:
            list_title: Name of the list
            item_id: ID of the item to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return False
            sp_list = self.get_list(list_title)
            if not sp_list:
                logger.error(f"List '{list_title}' not found")
                return False
            
            item = sp_list.get_item_by_id(item_id)
            item.delete_object()
            self.ctx.execute_query()
            logger.debug(f"Deleted item {item_id} from '{list_title}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete item {item_id} from '{list_title}': {e}")
            return False
    
    def get_items(self, list_title: str, filter_str: Optional[str] = None, **kwargs) -> list:
        """
        Get items from list with optional filtering.
        
        Args:
            list_title: Name of the list
            filter_str: OData filter string (optional)
            **kwargs: Additional options
            
        Returns:
            List of items or empty list if failed
        """
        try:
            if not self.ctx:
                logger.error("SharePoint context not initialized")
                return []
            sp_list = self.get_list(list_title)
            if not sp_list:
                logger.error(f"List '{list_title}' not found")
                return []
            
            # Build query
            query = sp_list.items
            if filter_str:
                query = query.filter(filter_str)
            if 'top' in kwargs:
                query = query.top(kwargs['top'])
            if 'select' in kwargs:
                query = query.select(kwargs['select'])
            
            items = query.get().execute_query()
            logger.debug(f"Retrieved {len(items)} items from '{list_title}'")
            return list(items) if items else []
        except Exception as e:
            logger.error(f"Failed to get items from '{list_title}': {e}")
            return []
    
    def batch_add_items(self, list_title: str, items: list) -> bool:
        """
        Add multiple items to list in batch.
        
        Args:
            list_title: Name of the list
            items: List of item dictionaries
            
        Returns:
            True if all successful, False if any failed
        """
        try:
            sp_list = self.get_list(list_title)
            if not sp_list:
                logger.error(f"List '{list_title}' not found")
                return False
            
            for item_props in items:
                sp_list.add_item(item_props)
            
            if self.ctx:
                self.ctx.execute_query()
            logger.info(f"Batch added {len(items)} items to '{list_title}'")
            return True
        except Exception as e:
            logger.error(f"Batch add failed for '{list_title}': {e}")
            return False
