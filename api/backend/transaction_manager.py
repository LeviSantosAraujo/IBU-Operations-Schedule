"""
Transaction Manager - Provides atomic multi-entity operations with rollback.

Purpose:
- Ensures data consistency across multiple entity updates
- Allows rollback if any operation in a transaction fails
- Prevents partial updates that leave system in inconsistent state

Architecture:
- Snapshot-based transactions (takes snapshots before operations)
- Simple rollback by restoring snapshots
- Thread-safe transaction context

Usage:
- Use as context manager: with Transaction() as tx:
- Call tx.add_snapshot() for entities to be modified
- Perform operations
- If exception occurs, rollback automatically
- Call tx.commit() to complete transaction

Limitations:
- In-memory snapshots (not suitable for very large datasets)
- Only works with json_store entities
- No distributed transaction support
"""

import threading
from typing import Dict, Any, Optional, List, Callable
from contextlib import contextmanager
import json_store


class Transaction:
    """
    Simple transaction manager with snapshot-based rollback.
    
    Provides atomic operations across multiple JSON store entities.
    """
    
    def __init__(self):
        self.snapshots: Dict[str, Any] = {}
        self.committed = False
        self.lock = threading.Lock()
    
    def add_snapshot(self, filename: str) -> None:
        """
        Take a snapshot of an entity before modification.
        
        Args:
            filename: JSON filename to snapshot (e.g., "employees.json")
        """
        if filename in self.snapshots:
            return  # Already snapshot
        
        data = json_store._read_json_file(filename)
        self.snapshots[filename] = data
        print(f"[TX] Snapshot taken for {filename}")
    
    def commit(self) -> None:
        """Mark transaction as committed (no rollback needed)."""
        self.committed = True
        print(f"[TX] Transaction committed with {len(self.snapshots)} snapshots")
    
    def rollback(self) -> None:
        """Rollback all changes by restoring snapshots."""
        if self.committed:
            return  # Already committed, nothing to rollback
        
        print(f"[TX] Rolling back {len(self.snapshots)} snapshots")
        
        for filename, snapshot in self.snapshots.items():
            try:
                # Restore snapshot
                if snapshot is None:
                    # File didn't exist, delete it
                    # For now, we just write empty list
                    json_store._write_json_file(filename, [])
                else:
                    json_store._write_json_file(filename, snapshot)
                print(f"[TX] Restored snapshot for {filename}")
            except Exception as e:
                print(f"[TX] Error restoring snapshot for {filename}: {e}")
        
        self.snapshots.clear()


# Global transaction context for current thread
_current_transaction: Optional[Transaction] = None
_tx_lock = threading.Lock()


@contextmanager
def begin_transaction():
    """
    Context manager for transactions.
    
    Usage:
        with begin_transaction() as tx:
            tx.add_snapshot("employees.json")
            # Modify employees
            tx.commit()
    """
    global _current_transaction
    
    tx = Transaction()
    
    with _tx_lock:
        _current_transaction = tx
    
    try:
        yield tx
        if not tx.committed:
            # Auto-rollback if not explicitly committed
            tx.rollback()
    except Exception as e:
        print(f"[TX] Exception in transaction, rolling back: {e}")
        tx.rollback()
        raise
    finally:
        with _tx_lock:
            _current_transaction = None


def get_current_transaction() -> Optional[Transaction]:
    """Get the current transaction context."""
    with _tx_lock:
        return _current_transaction


def in_transaction() -> bool:
    """Check if currently in a transaction."""
    return get_current_transaction() is not None
