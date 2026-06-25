"""
Audit Logger - Records all write operations for debugging and accountability.

Purpose:
- Provides complete change history for debugging issues
- Enables accountability by tracking who changed what and when
- Supports audit compliance requirements

Architecture:
- Structured logging to audit_log.json on GitHub data branch
- Automatic logging of all write operations via json_store integration
- Queryable audit log with filtering capabilities
- Batching to reduce GitHub API calls (flushes every N entries or T seconds)

Usage:
- Automatically called by json_store.py on write operations
- Can be manually queried via GET /api/audit-logs endpoint
- Supports filtering by entity type, user, date range

Environment Variables:
- AUDIT_LOG_ENABLED: Enable/disable audit logging (default: true)
- AUDIT_LOG_RETENTION_DAYS: How long to keep audit logs (default: 365)
- AUDIT_LOG_BATCH_SIZE: Number of entries to buffer before flush (default: 10)
- AUDIT_LOG_FLUSH_INTERVAL_SECONDS: Time between auto-flushes (default: 60)
"""

import os
import json
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import json_store


AUDIT_LOG_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365"))
AUDIT_LOG_BATCH_SIZE = int(os.getenv("AUDIT_LOG_BATCH_SIZE", "10"))
AUDIT_LOG_FLUSH_INTERVAL_SECONDS = int(os.getenv("AUDIT_LOG_FLUSH_INTERVAL_SECONDS", "60"))

# In-memory buffer for batched audit log entries
_audit_buffer: List[Dict] = []
_buffer_lock = threading.RLock()
_last_flush_time = time.time()

# Lock for audit log read-modify-write operations (prevents race conditions)
_audit_write_lock = threading.Lock()


def log_write_operation(
    entity_type: str,
    operation: str,  # "create", "update", "delete"
    entity_id: Optional[str],
    user_id: Optional[str],
    changes: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Log a write operation to the audit log (batched).
    
    Args:
        entity_type: Type of entity (e.g., "employee", "schedule")
        operation: Type of operation ("create", "update", "delete")
        entity_id: ID of the entity being modified
        user_id: ID of the user performing the operation
        changes: Dictionary of changes made (for updates)
        metadata: Additional metadata (e.g., request_id, ip_address)
    
    Returns:
        True if log was buffered successfully, False otherwise
    """
    if not AUDIT_LOG_ENABLED:
        return True
    
    try:
        # Create log entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "entity_type": entity_type,
            "operation": operation,
            "entity_id": entity_id,
            "user_id": user_id,
            "changes": changes,
            "metadata": metadata or {}
        }
        
        # Add to buffer
        with _buffer_lock:
            _audit_buffer.append(entry)
            
            # Check if we should flush
            should_flush = (
                len(_audit_buffer) >= AUDIT_LOG_BATCH_SIZE or
                (time.time() - _last_flush_time) >= AUDIT_LOG_FLUSH_INTERVAL_SECONDS
            )
            
            if should_flush:
                return _flush_buffer()
        
        return True
    except Exception as e:
        print(f"[AUDIT] Error buffering audit log entry: {e}")
        return False


def _flush_buffer() -> bool:
    """
    Flush the audit log buffer to GitHub with optimistic locking.
    
    Returns:
        True if flush was successful, False otherwise
    """
    global _last_flush_time
    
    with _buffer_lock:
        if not _audit_buffer:
            return True  # Nothing to flush
        
        entries_to_flush = list(_audit_buffer)
        _audit_buffer.clear()
        _last_flush_time = time.time()
    
    # Use lock to prevent race conditions on read-modify-write
    with _audit_write_lock:
        try:
            # Load existing audit log
            audit_log = json_store._read_json_file("audit_log.json")
            if audit_log is None:
                audit_log = []
            
            # Add buffered entries
            audit_log.extend(entries_to_flush)
            
            # Prune old entries based on retention policy
            audit_log = _prune_old_entries(audit_log)
            
            # Write back to GitHub (with optimistic locking via json_store)
            result = json_store._write_json_file("audit_log.json", audit_log)
            
            if result:
                print(f"[AUDIT] Flushed {len(entries_to_flush)} audit log entries")
            else:
                # If write failed (likely due to conflict), put entries back in buffer
                with _buffer_lock:
                    _audit_buffer.extend(entries_to_flush)
                    print(f"[AUDIT] Write conflict, re-buffered {len(entries_to_flush)} entries")
            
            return result
        except Exception as e:
            print(f"[AUDIT] Error flushing audit log buffer: {e}")
            # Put entries back in buffer on error
            with _buffer_lock:
                _audit_buffer.extend(entries_to_flush)
            return False


def flush_audit_log() -> bool:
    """
    Manually flush the audit log buffer (for use by API endpoint).
    
    Returns:
        True if flush was successful, False otherwise
    """
    return _flush_buffer()


def _prune_old_entries(audit_log: List[Dict]) -> List[Dict]:
    """
    Remove audit log entries older than retention period.
    
    Args:
        audit_log: List of audit log entries
    
    Returns:
        Pruned audit log
    """
    if AUDIT_LOG_RETENTION_DAYS <= 0:
        return audit_log  # No pruning
    
    cutoff_date = datetime.now().timestamp() - (AUDIT_LOG_RETENTION_DAYS * 24 * 60 * 60)
    
    pruned = []
    for entry in audit_log:
        try:
            timestamp = entry["timestamp"]
            # Handle both string and datetime timestamps
            if isinstance(timestamp, str):
                entry_timestamp = datetime.fromisoformat(timestamp).timestamp()
            elif isinstance(timestamp, datetime):
                entry_timestamp = timestamp.timestamp()
            else:
                # Keep entries with unexpected timestamp types
                pruned.append(entry)
                continue
            
            if entry_timestamp >= cutoff_date:
                pruned.append(entry)
        except (KeyError, ValueError, TypeError):
            # Keep entries with invalid timestamps
            pruned.append(entry)
    
    if len(pruned) < len(audit_log):
        print(f"[AUDIT] Pruned {len(audit_log) - len(pruned)} old entries")
    
    return pruned


def get_audit_logs(
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    operation: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Retrieve audit logs with optional filtering.
    
    Args:
        entity_type: Filter by entity type
        user_id: Filter by user ID
        operation: Filter by operation type
        limit: Maximum number of entries to return
    
    Returns:
        List of audit log entries
    """
    try:
        audit_log = json_store._read_json_file("audit_log.json")
        if audit_log is None:
            return []
        
        # Apply filters
        filtered = audit_log
        if entity_type:
            filtered = [e for e in filtered if e.get("entity_type") == entity_type]
        if user_id:
            filtered = [e for e in filtered if e.get("user_id") == user_id]
        if operation:
            filtered = [e for e in filtered if e.get("operation") == operation]
        
        # Sort by timestamp descending (newest first)
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Apply limit
        return filtered[:limit]
    except Exception as e:
        print(f"[AUDIT] Error retrieving audit logs: {e}")
        return []


def get_audit_log_stats() -> Dict[str, Any]:
    """
    Get statistics about the audit log.
    
    Returns:
        Dictionary with audit log statistics
    """
    try:
        audit_log = json_store._read_json_file("audit_log.json")
        if audit_log is None:
            return {
                "total_entries": 0,
                "by_entity_type": {},
                "by_operation": {},
                "by_user": {}
            }
        
        stats = {
            "total_entries": len(audit_log),
            "by_entity_type": {},
            "by_operation": {},
            "by_user": {}
        }
        
        for entry in audit_log:
            # Count by entity type
            entity_type = entry.get("entity_type", "unknown")
            stats["by_entity_type"][entity_type] = stats["by_entity_type"].get(entity_type, 0) + 1
            
            # Count by operation
            operation = entry.get("operation", "unknown")
            stats["by_operation"][operation] = stats["by_operation"].get(operation, 0) + 1
            
            # Count by user
            user_id = entry.get("user_id", "unknown")
            stats["by_user"][user_id] = stats["by_user"].get(user_id, 0) + 1
        
        return stats
    except Exception as e:
        print(f"[AUDIT] Error getting audit log stats: {e}")
        return {
            "total_entries": 0,
            "by_entity_type": {},
            "by_operation": {},
            "by_user": {}
        }
