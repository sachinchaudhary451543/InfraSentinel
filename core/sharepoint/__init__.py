"""
SharePoint Integration Module

Unified interface for all SharePoint operations:
- Client authentication and management
- List schema and creation
- Metrics uploading
- Remote command execution

All SharePoint functionality is consolidated here to avoid duplication
and ensure a single source of truth for list management.
"""

from .client import SharePointClient
from .models import (
    ListType,
    MetricsItem,
    AgentItem,
    CommandItem,
    VmItem,
    DiscoveredSystemItem
)
from .schema import SchemaManager
from .uploader import MetricsUploader
from .commands import CommandExecutor

__all__ = [
    "SharePointClient",
    "SchemaManager",
    "MetricsUploader",
    "CommandExecutor",
    "ListType",
    "MetricsItem",
    "AgentItem",
    "CommandItem",
    "VmItem",
    "DiscoveredSystemItem",
]

__version__ = "1.0.0"
