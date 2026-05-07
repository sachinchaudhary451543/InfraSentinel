"""
Metrics Uploader - Upload server metrics to SharePoint
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from .client import SharePointClient
from .models import MetricsItem, ListType

logger = logging.getLogger(__name__)


class MetricsUploader:
    """Upload metrics to SharePoint lists"""
    
    def __init__(self, client: SharePointClient):
        """
        Initialize metrics uploader.
        
        Args:
            client: SharePointClient instance
        """
        self.client = client
        self.summary_list = ListType.METRICS_SUMMARY.value
        self.history_list = ListType.METRICS_HISTORY.value
    
    def upload_metrics(self, metrics: List[MetricsItem]) -> bool:
        """
        Upload batch of metrics.
        
        Args:
            metrics: List of MetricsItem objects
            
        Returns:
            True if successful
        """
        if not metrics:
            logger.warning("No metrics to upload")
            return False
        
        try:
            logger.info(f"Uploading {len(metrics)} metrics items")
            
            # Batch add to summary list
            summary_items = [m.to_dict() for m in metrics]
            self.client.batch_add_items(self.summary_list, summary_items)
            
            # Also add to history
            history_items = [m.to_dict() for m in metrics]
            self.client.batch_add_items(self.history_list, history_items)
            
            logger.info(f"✓ Successfully uploaded {len(metrics)} metrics")
            return True
        except Exception as e:
            logger.error(f"Failed to upload metrics: {e}")
            return False
    
    def upload_server_metrics(
        self,
        server_name: str,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        total_ram: float = 0,
        available_ram: float = 0,
        total_ssd: float = 0,
        available_ssd: float = 0,
        health_status: str = "healthy",
        error: Optional[str] = None
    ) -> bool:
        """
        Upload single server metrics.
        
        Args:
            server_name: Name of the server
            cpu_percent: CPU usage percentage
            memory_percent: Memory usage percentage
            disk_percent: Disk usage percentage
            total_ram: Total RAM in GB
            available_ram: Available RAM in GB
            total_ssd: Total SSD in GB
            available_ssd: Available SSD in GB
            health_status: Health status (healthy, warning, critical)
            error: Optional error message
            
        Returns:
            True if successful
        """
        try:
            timestamp = datetime.now().isoformat()
            out_of_ram = 1 if available_ram < 1 else 0
            out_of_ssd = 1 if available_ssd < 1 else 0
            
            metric = MetricsItem(
                server_name=server_name,
                timestamp=timestamp,
                avg_cpu=cpu_percent,
                avg_disk=disk_percent,
                avg_ram=memory_percent,
                avg_ssd=disk_percent,  # Using same as disk for SSD
                total_ram=total_ram,
                available_ram=available_ram,
                total_ssd=total_ssd,
                available_ssd=available_ssd,
                out_of_ram=out_of_ram,
                out_of_ssd=out_of_ssd,
                health_status=health_status,
                error=error
            )
            
            return self.upload_metrics([metric])
        except Exception as e:
            logger.error(f"Failed to upload metrics for '{server_name}': {e}")
            return False
    
    def get_latest_metrics(
        self,
        server_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get latest metrics for a server.
        
        Args:
            server_name: Name of the server
            limit: Maximum number of records to return
            
        Returns:
            List of metric items
        """
        try:
            filter_str = f"ServerName eq '{server_name}'"
            items = self.client.get_items(
                self.history_list,
                filter_str=filter_str,
                top=limit,
                select=['ServerName', 'Timestamp', 'AvgCPU', 'AvgDisk', 'AvgRAM', 'HealthStatus']
            )
            logger.debug(f"Retrieved {len(items)} metrics for '{server_name}'")
            return items
        except Exception as e:
            logger.error(f"Failed to get metrics for '{server_name}': {e}")
            return []
    
    def get_current_status(self, server_name: str) -> Optional[Dict[str, Any]]:
        """
        Get current status for a server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Latest metric or None if not found
        """
        try:
            items = self.get_latest_metrics(server_name, limit=1)
            return items[0] if items else None
        except Exception as e:
            logger.error(f"Failed to get status for '{server_name}': {e}")
            return None
