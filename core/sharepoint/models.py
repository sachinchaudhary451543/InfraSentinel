"""
Data models for SharePoint lists
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from enum import Enum


class ListType(Enum):
    """Types of SharePoint lists used in ServerMonitor"""
    METRICS_SUMMARY = "ServerMetricsSummary"
    METRICS_HISTORY = "ServerMetricsHistory"
    VMS = "ServerVMs"
    INVENTORY = "ServerInventory"
    AGENTS = "RegisteredAgents"
    COMMANDS = "RemoteCommands"
    DISCOVERED = "DiscoveredSystems"
    SERVER_CONTROL = "ServerControl"


@dataclass
class MetricsItem:
    """Server metrics list item"""
    server_name: str
    timestamp: str
    avg_cpu: float
    avg_disk: float
    avg_ram: float
    avg_ssd: float
    total_ram: float
    available_ram: float
    total_ssd: float
    available_ssd: float
    out_of_ram: int = 0
    out_of_ssd: int = 0
    health_status: str = "healthy"
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SharePoint"""
        data = asdict(self)
        # Convert field names to SharePoint format
        data['ServerName'] = data.pop('server_name')
        data['Timestamp'] = data.pop('timestamp')
        data['AvgCPU'] = data.pop('avg_cpu')
        data['AvgDisk'] = data.pop('avg_disk')
        data['AvgRAM'] = data.pop('avg_ram')
        data['AvgSSD'] = data.pop('avg_ssd')
        data['TotalRAM'] = data.pop('total_ram')
        data['AvailableRAM'] = data.pop('available_ram')
        data['TotalSSD'] = data.pop('total_ssd')
        data['AvailableSSD'] = data.pop('available_ssd')
        data['OutOfRAM'] = data.pop('out_of_ram')
        data['OutOfSSD'] = data.pop('out_of_ssd')
        data['HealthStatus'] = data.pop('health_status')
        data['Error'] = data.pop('error')
        return data


@dataclass
class AgentItem:
    """Registered agent list item"""
    agent_id: str
    server_name: str
    ip_address: str
    status: str
    last_heartbeat: str
    version: Optional[str] = None
    platform: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SharePoint"""
        data = asdict(self)
        data['AgentID'] = data.pop('agent_id')
        data['ServerName'] = data.pop('server_name')
        data['IPAddress'] = data.pop('ip_address')
        data['Status'] = data.pop('status')
        data['LastHeartbeat'] = data.pop('last_heartbeat')
        if 'version' in data:
            data['Version'] = data.pop('version')
        if 'platform' in data:
            data['Platform'] = data.pop('platform')
        return data


@dataclass
class CommandItem:
    """Remote command execution list item"""
    command_id: str
    server_name: str
    command: str
    status: str
    output: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SharePoint"""
        data = asdict(self)
        data['CommandID'] = data.pop('command_id')
        data['ServerName'] = data.pop('server_name')
        data['Command'] = data.pop('command')
        data['Status'] = data.pop('status')
        data['Output'] = data.pop('output')
        data['Timestamp'] = data.pop('timestamp')
        data['Error'] = data.pop('error')
        return data


@dataclass
class VmItem:
    """VM system list item"""
    host_server: str
    vm_name: str
    state: str
    cpu_usage: float
    memory_assigned: float
    uptime: str
    path: str
    host_ip: str
    host_os: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SharePoint"""
        data = asdict(self)
        data['HostServer'] = data.pop('host_server')
        data['VMName'] = data.pop('vm_name')
        data['State'] = data.pop('state')
        data['CPUUsage'] = data.pop('cpu_usage')
        data['MemoryAssigned'] = data.pop('memory_assigned')
        data['Uptime'] = data.pop('uptime')
        data['Path'] = data.pop('path')
        data['HostIP'] = data.pop('host_ip')
        data['HostOS'] = data.pop('host_os')
        return data


@dataclass
class DiscoveredSystemItem:
    """Discovered system list item"""
    hostname: str
    ip_address: str
    os_name: str
    os_version: Optional[str]
    system_type: str
    domain: str
    mac_address: Optional[str]
    discovered_at: str
    source: str = "ActiveDirectory"
    status: str = "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SharePoint"""
        data = asdict(self)
        data['Hostname'] = data.pop('hostname')
        data['IPAddress'] = data.pop('ip_address')
        data['OSName'] = data.pop('os_name')
        data['OSVersion'] = data.pop('os_version')
        data['SystemType'] = data.pop('system_type')
        data['Domain'] = data.pop('domain')
        data['MACAddress'] = data.pop('mac_address')
        data['DiscoveredAt'] = data.pop('discovered_at')
        data['Source'] = data.pop('source')
        data['Status'] = data.pop('status')
        return data


class SchemaDefinition:
    """SharePoint list schema definitions"""
    
    # Metrics Summary list schema
    METRICS_SUMMARY_SCHEMA = {
        "ServerMetricsSummary": [
            {"name": "ServerName", "type": "Text", "required": True},
            {"name": "Timestamp", "type": "DateTime", "required": True},
            {"name": "AvgCPU", "type": "Number"},
            {"name": "AvgDisk", "type": "Number"},
            {"name": "AvgRAM", "type": "Number"},
            {"name": "AvgSSD", "type": "Number"},
            {"name": "TotalRAM", "type": "Number"},
            {"name": "AvailableRAM", "type": "Number"},
            {"name": "TotalSSD", "type": "Number"},
            {"name": "AvailableSSD", "type": "Number"},
            {"name": "OutOfRAM", "type": "Number"},
            {"name": "OutOfSSD", "type": "Number"},
            {"name": "HealthStatus", "type": "Text"},
            {"name": "Error", "type": "Text"},
        ]
    }
    
    # Metrics History list schema
    METRICS_HISTORY_SCHEMA = {
        "ServerMetricsHistory": [
            {"name": "ServerName", "type": "Text", "required": True},
            {"name": "Timestamp", "type": "DateTime", "required": True},
            {"name": "AvgCPU", "type": "Number"},
            {"name": "AvgDisk", "type": "Number"},
            {"name": "AvgRAM", "type": "Number"},
            {"name": "AvgSSD", "type": "Number"},
            {"name": "TotalRAM", "type": "Number"},
            {"name": "AvailableRAM", "type": "Number"},
            {"name": "TotalSSD", "type": "Number"},
            {"name": "AvailableSSD", "type": "Number"},
            {"name": "OutOfRAM", "type": "Number"},
            {"name": "OutOfSSD", "type": "Number"},
            {"name": "HealthStatus", "type": "Text"},
            {"name": "Error", "type": "Text"},
        ]
    }
    
    # VMs list schema
    VMS_SCHEMA = {
        "ServerVMs": [
            {"name": "HostServer", "type": "Text", "required": True},
            {"name": "VMName", "type": "Text", "required": True},
            {"name": "State", "type": "Text"},
            {"name": "CPUUsage", "type": "Number"},
            {"name": "MemoryAssigned", "type": "Number"},
            {"name": "Uptime", "type": "Text"},
            {"name": "Path", "type": "Text"},
            {"name": "HostIP", "type": "Text"},
            {"name": "HostOS", "type": "Text"},
        ]
    }
    
    # Agents list schema
    AGENTS_SCHEMA = {
        "RegisteredAgents": [
            {"name": "AgentID", "type": "Text", "required": True},
            {"name": "ServerName", "type": "Text", "required": True},
            {"name": "IPAddress", "type": "Text"},
            {"name": "Status", "type": "Text"},
            {"name": "LastHeartbeat", "type": "DateTime"},
            {"name": "Version", "type": "Text"},
            {"name": "Platform", "type": "Text"},
        ]
    }
    
    # Commands list schema
    COMMANDS_SCHEMA = {
        "RemoteCommands": [
            {"name": "CommandID", "type": "Text", "required": True},
            {"name": "ServerName", "type": "Text", "required": True},
            {"name": "Command", "type": "Text", "required": True},
            {"name": "Status", "type": "Text"},
            {"name": "Output", "type": "Text"},
            {"name": "Timestamp", "type": "DateTime"},
            {"name": "Error", "type": "Text"},
        ]
    }
