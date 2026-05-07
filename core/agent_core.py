"""
Agent Core - Enhanced agent architecture with offline support

Features:
- Heartbeat mechanism
- Offline detection & buffering
- Plugin-based collectors
- Status reporting
"""

import os
import json
import logging
import sqlite3
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import queue

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    """Agent operational status"""
    agent_id: str
    is_online: bool
    last_heartbeat: str
    last_error: Optional[str] = None
    uptime_seconds: int = 0
    version: str = "2.0.0"
    collectors_active: Dict[str, bool] = field(default_factory=dict)


class OfflineBuffer:
    """SQLite-backed queue for offline metric storage"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize offline buffer database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS offline_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    data TEXT NOT NULL,
                    synced INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_synced ON offline_buffer(synced)")
            conn.commit()
    
    def add(self, data: Dict[str, Any]) -> bool:
        """Queue data for offline storage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO offline_buffer (timestamp, data) VALUES (?, ?)",
                    (datetime.utcnow().isoformat(), json.dumps(data))
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add to offline buffer: {e}")
            return False
    
    def get_unsynced(self, limit: int = 100) -> list:
        """Retrieve unsynced data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute(
                    "SELECT id, data FROM offline_buffer WHERE synced = 0 LIMIT ?",
                    (limit,)
                )
                return [(row['id'], json.loads(row['data'])) for row in c.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unsynced data: {e}")
            return []
    
    def mark_synced(self, record_ids: list) -> bool:
        """Mark records as synced"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                placeholders = ','.join('?' * len(record_ids))
                c.execute(
                    f"UPDATE offline_buffer SET synced = 1 WHERE id IN ({placeholders})",
                    record_ids
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark synced: {e}")
            return False
    
    def cleanup_old(self, days: int = 7) -> int:
        """Remove old synced records"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                cutoff = datetime.utcnow() - timedelta(days=days)
                c.execute(
                    "DELETE FROM offline_buffer WHERE synced = 1 AND created_at < ?",
                    (cutoff.isoformat(),)
                )
                conn.commit()
                return c.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup: {e}")
            return 0


class MetricsCollector:
    """Base class for metric collectors"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.last_error = None
    
    def collect(self) -> Optional[Dict[str, Any]]:
        """Collect metrics - override in subclasses"""
        raise NotImplementedError
    
    def health_check(self) -> bool:
        """Check collector health"""
        try:
            self.collect()
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Collector {self.name} health check failed: {e}")
            return False


class AgentCore:
    """
    Enhanced agent with offline support, heartbeat, and plugin architecture
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialize agent core
        
        Args:
            agent_id: Unique agent identifier
            config: Configuration dictionary
        """
        self.agent_id = agent_id
        self.config = config
        self.start_time = time.time()
        
        # Initialize offline buffer
        buffer_db = os.path.join(
            config.get('agent', {}).get('buffer_dir', './data/agent_buffer'),
            f"{agent_id}_buffer.db"
        )
        self.offline_buffer = OfflineBuffer(buffer_db)
        
        # Collectors registry
        self.collectors: Dict[str, MetricsCollector] = {}
        
        # Status
        self.status = AgentStatus(
            agent_id=agent_id,
            is_online=True,
            last_heartbeat=datetime.utcnow().isoformat()
        )
        
        # Control queue for remote commands
        self.control_queue: queue.Queue = queue.Queue()
        
        # Heartbeat thread
        self.heartbeat_thread = None
        self.should_run = True
    
    def register_collector(self, collector: MetricsCollector) -> None:
        """Register a metrics collector"""
        self.collectors[collector.name] = collector
        self.status.collectors_active[collector.name] = collector.enabled
        logger.info(f"Registered collector: {collector.name}")
    
    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect metrics from all registered collectors"""
        metrics = {
            "agent_id": self.agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "collectors": {}
        }
        
        for name, collector in self.collectors.items():
            if not collector.enabled:
                continue
            
            try:
                data = collector.collect()
                if data:
                    metrics["collectors"][name] = data
            except Exception as e:
                logger.error(f"Collector {name} failed: {e}")
                metrics["collectors"][name] = {"error": str(e)}
        
        return metrics
    
    def start_heartbeat(self, interval: int = 300, callback: Optional[Callable] = None):
        """
        Start heartbeat thread
        
        Args:
            interval: Heartbeat interval in seconds
            callback: Optional callback function for heartbeat
        """
        def heartbeat_loop():
            while self.should_run:
                try:
                    self.status.last_heartbeat = datetime.utcnow().isoformat()
                    self.status.uptime_seconds = int(time.time() - self.start_time)
                    
                    if callback:
                        callback(self.status)
                    
                    logger.debug(f"Heartbeat sent - uptime: {self.status.uptime_seconds}s")
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")
                    time.sleep(interval)
        
        self.heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name="AgentHeartbeat"
        )
        self.heartbeat_thread.start()
        logger.info(f"Heartbeat started with interval {interval}s")
    
    def stop(self):
        """Gracefully stop agent"""
        self.should_run = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        logger.info("Agent stopped")
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get complete agent status"""
        return {
            "agent_id": self.agent_id,
            "is_online": self.status.is_online,
            "last_heartbeat": self.status.last_heartbeat,
            "uptime_seconds": self.status.uptime_seconds,
            "version": self.status.version,
            "collectors": self.status.collectors_active,
            "offline_buffer_size": self._get_buffer_size(),
        }
    
    def _get_buffer_size(self) -> int:
        """Get number of unsynced records in buffer"""
        unsynced = self.offline_buffer.get_unsynced(limit=999999)
        return len(unsynced)
    
    def sync_offline_data(self, sync_callback: Callable) -> Dict[str, Any]:
        """
        Sync buffered offline data
        
        Args:
            sync_callback: Function to call for each data point
            
        Returns:
            Sync results
        """
        results = {
            "synced": 0,
            "failed": 0,
            "errors": []
        }
        
        unsynced = self.offline_buffer.get_unsynced()
        synced_ids = []
        
        for record_id, data in unsynced:
            try:
                sync_callback(data)
                synced_ids.append(record_id)
                results["synced"] += 1
            except Exception as e:
                logger.error(f"Failed to sync record {record_id}: {e}")
                results["failed"] += 1
                results["errors"].append(str(e))
        
        if synced_ids:
            self.offline_buffer.mark_synced(synced_ids)
        
        return results
