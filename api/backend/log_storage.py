"""In-memory log storage for monitoring dashboard.

Stores last 200 logs in circular buffer.
Logs are lost on server restart.
"""

import threading
from datetime import datetime
from typing import List, Dict, Optional
from collections import deque


class LogStorage:
    """Thread-safe in-memory log storage with circular buffer."""
    
    def __init__(self, max_logs: int = 200):
        self.max_logs = max_logs
        self.backend_logs = deque(maxlen=max_logs)
        self.frontend_logs = deque(maxlen=max_logs)
        self.lock = threading.Lock()
        self.server_start_time = datetime.now()
    
    def add_backend_log(self, message: str, level: str = "INFO"):
        """Add a backend log entry."""
        with self.lock:
            self.backend_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message
            })
    
    def add_frontend_log(self, message: str, level: str = "ERROR", url: str = "", component: str = ""):
        """Add a frontend log entry."""
        with self.lock:
            self.frontend_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message,
                "url": url,
                "component": component
            })
    
    def get_backend_logs(self, limit: Optional[int] = None) -> List[Dict]:
        """Get backend logs."""
        with self.lock:
            logs = list(self.backend_logs)
            if limit:
                return logs[-limit:]
            return logs
    
    def get_frontend_logs(self, limit: Optional[int] = None) -> List[Dict]:
        """Get frontend logs."""
        with self.lock:
            logs = list(self.frontend_logs)
            if limit:
                return logs[-limit:]
            return logs
    
    def has_errors(self, log_type: str = "backend") -> bool:
        """Check if recent logs contain errors."""
        with self.lock:
            logs = self.backend_logs if log_type == "backend" else self.frontend_logs
            return any(log.get("level") in ["ERROR", "CRITICAL"] for log in logs)
    
    def get_server_start_time(self) -> str:
        """Get server start time."""
        return self.server_start_time.isoformat()


# Global instance
_log_storage: Optional[LogStorage] = None


def get_log_storage() -> LogStorage:
    """Get global log storage instance."""
    global _log_storage
    if _log_storage is None:
        _log_storage = LogStorage()
    return _log_storage
