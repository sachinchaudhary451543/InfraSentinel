"""
core/domain_discovery.py – ServerMonitor ISV
==============================================
Completely refactored to use MS Graph via core.azure_graph instead of Get-ADComputer.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from . import azure_graph
    _AZURE_AVAILABLE = True
except Exception as e:
    azure_graph = None  # type: ignore
    _AZURE_AVAILABLE = False
    logging.error(f"azure_graph unavailable: {e}")

logger = logging.getLogger(__name__)

class SystemType(Enum):
    SERVER             = "Server"
    WORKSTATION        = "Workstation"
    VM_HOST            = "VMHost"
    VIRTUAL_MACHINE    = "VirtualMachine"
    DOMAIN_CONTROLLER  = "DomainController"
    UNKNOWN            = "Unknown"

@dataclass
class DiscoveredSystem:
    hostname:       str
    ip_address:     Optional[str]
    os_name:        str
    os_version:     Optional[str]
    system_type:    SystemType
    domain:         str
    ou_path:        str
    mac_address:    Optional[str]
    serial_number:  Optional[str]
    discovered_at:  str
    last_seen:      str
    enabled:        bool
    description:    Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["system_type"] = self.system_type.value
        return data

    def to_sharepoint_item(self, tenant_id: str) -> Dict[str, Any]:
        d = self.to_dict()
        d["TenantId"] = tenant_id
        return d

class DomainDiscoveryEngine:
    def __init__(self, tenant_record: Optional[Any] = None, **kwargs):
        self.tenant_record = tenant_record
        self.systems: List[DiscoveredSystem] = []

    def discover_servers(self, **kwargs) -> List[DiscoveredSystem]:
        return self.run_discovery()

    def run_discovery(self) -> List[DiscoveredSystem]:
        if not _AZURE_AVAILABLE:
            logger.warning("Azure discovery not available.")
            return []

        logger.info("Discovering systems via MS Graph")
        try:
            raw_devices = azure_graph.get_devices(self.tenant_record)
            managed_devices = azure_graph.get_managed_devices(self.tenant_record)

            systems: List[DiscoveredSystem] = []
            now = datetime.utcnow().isoformat()
            
            # Map devices
            for entry in raw_devices:
                os_name = entry.get("operatingSystem") or "Unknown"
                systems.append(DiscoveredSystem(
                    hostname      = entry.get("displayName") or entry.get("id", ""),
                    ip_address    = None,
                    os_name       = os_name,
                    os_version    = None,
                    system_type   = self._classify(os_name, entry.get("displayName", "")),
                    domain        = getattr(self.tenant_record, 'name', 'Azure'),
                    ou_path       = "",
                    mac_address   = None,
                    serial_number = entry.get("id"),
                    discovered_at = now,
                    last_seen     = now,
                    enabled       = True,
                    description   = None,
                ))

            # Add managed devices (Intune) if they are not already included or merge them
            for entry in managed_devices:
                hostname = entry.get("deviceName") or entry.get("id", "")
                ip_addr = entry.get("ipAddress")
                if not any(s.hostname == hostname for s in systems):
                    os_name = entry.get("operatingSystem") or "Unknown"
                    systems.append(DiscoveredSystem(
                        hostname      = hostname,
                        ip_address    = ip_addr,
                        os_name       = os_name,
                        os_version    = entry.get("osVersion"),
                        system_type   = self._classify(os_name, hostname),
                        domain        = getattr(self.tenant_record, 'name', 'Azure'),
                        ou_path       = "",
                        mac_address   = entry.get("macAddress"),
                        serial_number = entry.get("serialNumber"),
                        discovered_at = now,
                        last_seen     = now,
                        enabled       = entry.get("isEncrypted", True),
                        description   = entry.get("userPrincipalName"),
                    ))

            if not systems:
                logger.info("Graph API returned no systems. Falling back to local detection.")
                systems = self._run_local_fallback()

            self.systems = systems
            logger.info(f"Discovered {len(systems)} systems")
            return systems

        except Exception as e:
            logger.error(f"Azure discovery error: {e}. Falling back to local.")
            systems = self._run_local_fallback()
            self.systems = systems
            return systems

    def _run_local_fallback(self) -> List[DiscoveredSystem]:
        """Local fallback using Python sockets when Graph is unavailable."""
        import socket
        import platform
        
        now = datetime.utcnow().isoformat()
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
        except Exception:
            ip = "127.0.0.1"
            
        os_info = f"{platform.system()} {platform.release()}"
        
        return [DiscoveredSystem(
            hostname      = hostname,
            ip_address    = ip,
            os_name       = os_info,
            os_version    = platform.version(),
            system_type   = self._classify(os_info, hostname),
            domain        = getattr(self.tenant_record, 'name', 'Local'),
            ou_path       = "",
            mac_address   = None,
            serial_number = None,
            discovered_at = now,
            last_seen     = now,
            enabled       = True,
            description   = "Auto-discovered local host (fallback)",
        )]

    def _classify(self, os_name: str, hostname: str) -> SystemType:
        os_lower   = (os_name or "").lower()
        host_lower = (hostname or "").lower()

        if "domain controller" in os_lower or host_lower.startswith("dc"):
            return SystemType.DOMAIN_CONTROLLER
        if "server" in os_lower:
            return SystemType.SERVER
        if any(k in host_lower for k in ("vm-", "virt", "hyper")):
            return SystemType.VM_HOST
        if "windows 10" in os_lower or "windows 11" in os_lower or "windows" in os_lower:
            return SystemType.WORKSTATION
        return SystemType.UNKNOWN

    def sync_to_sharepoint(self, site_url: str, access_token: str, tenant_id: str) -> int:
        pass
