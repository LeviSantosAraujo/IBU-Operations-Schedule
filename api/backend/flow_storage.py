"""Flow storage for monitoring dashboard flow diagram.

Tracks API calls, database operations, GitHub operations, and cache operations.
Stores last 10 flow chains within 5-minute time window.
"""

import threading
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from collections import deque
import uuid


class FlowEntry:
    """Single operation in a flow chain."""
    
    def __init__(self, operation_type: str, name: str, parent_id: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.parent_id = parent_id
        self.operation_type = operation_type  # 'api', 'database', 'github', 'cache'
        self.name = name  # endpoint name, file name, operation name
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.duration_ms: Optional[float] = None
        self.status: str = "pending"  # 'pending', 'success', 'error'
        self.metadata: Dict = {}  # Additional details (status code, bytes, etc.)
    
    def complete(self, status: str = "success", metadata: Optional[Dict] = None):
        """Mark operation as complete."""
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status
        if metadata:
            self.metadata.update(metadata)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "operation_type": self.operation_type,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "metadata": self.metadata
        }


class FlowChain:
    """A chain of related operations (e.g., one API request and its nested operations)."""
    
    def __init__(self, root_operation: FlowEntry):
        self.id = root_operation.id
        self.root_operation = root_operation
        self.operations: Dict[str, FlowEntry] = {root_operation.id: root_operation}
        self.start_time = root_operation.start_time
        self.end_time: Optional[datetime] = None
    
    def add_operation(self, operation: FlowEntry):
        """Add a nested operation to the chain."""
        self.operations[operation.id] = operation
        if operation.parent_id not in self.operations:
            # Orphan operation - attach to root
            operation.parent_id = self.root_operation.id
    
    def complete(self):
        """Mark the entire chain as complete."""
        self.end_time = datetime.now(timezone.utc)
    
    def is_complete(self) -> bool:
        """Check if all operations in the chain are complete."""
        return all(op.status != "pending" for op in self.operations.values())
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "operations": [op.to_dict() for op in self.operations.values()]
        }


class FlowStorage:
    """Thread-safe flow storage with time-based filtering."""
    
    def __init__(self, max_chains: int = 10, time_window_minutes: int = 5):
        self.max_chains = max_chains
        self.time_window = timedelta(minutes=time_window_minutes)
        self.chains: Dict[str, FlowChain] = {}
        self.lock = threading.Lock()
    
    def start_chain(self, operation_type: str, name: str) -> FlowChain:
        """Start a new flow chain."""
        root_op = FlowEntry(operation_type, name)
        chain = FlowChain(root_op)
        
        with self.lock:
            self.chains[chain.id] = chain
            self._cleanup_old_chains()
        
        return chain
    
    def add_operation(self, chain_id: str, operation_type: str, name: str, parent_id: Optional[str] = None) -> Optional[FlowEntry]:
        """Add an operation to an existing chain."""
        with self.lock:
            if chain_id not in self.chains:
                return None
            
            chain = self.chains[chain_id]
            if parent_id and parent_id not in chain.operations:
                parent_id = chain.root_operation.id
            
            operation = FlowEntry(operation_type, name, parent_id)
            chain.add_operation(operation)
            return operation
    
    def complete_operation(self, chain_id: str, operation_id: str, status: str = "success", metadata: Optional[Dict] = None):
        """Mark an operation as complete."""
        with self.lock:
            if chain_id in self.chains and operation_id in self.chains[chain_id].operations:
                self.chains[chain_id].operations[operation_id].complete(status, metadata)
                
                # Check if chain is now complete
                if self.chains[chain_id].is_complete():
                    self.chains[chain_id].complete()
    
    def complete_chain(self, chain_id: str, status: str = "success", metadata: Optional[Dict] = None):
        """Mark the root operation of a chain as complete."""
        with self.lock:
            if chain_id in self.chains:
                self.chains[chain_id].root_operation.complete(status, metadata)
                self.chains[chain_id].complete()
    
    def get_recent_chains(self, limit: Optional[int] = None) -> List[Dict]:
        """Get recent flow chains within time window."""
        with self.lock:
            self._cleanup_old_chains()
            
            chains = list(self.chains.values())
            # Sort by start time, most recent first
            chains.sort(key=lambda c: c.start_time, reverse=True)
            
            if limit:
                chains = chains[:limit]
            
            return [chain.to_dict() for chain in chains]
    
    def _cleanup_old_chains(self):
        """Remove chains outside the time window or exceeding max count."""
        cutoff = datetime.now(timezone.utc) - self.time_window
        
        # Remove chains outside time window
        self.chains = {
            k: v for k, v in self.chains.items()
            if v.start_time > cutoff
        }
        
        # Remove oldest chains if exceeding max
        if len(self.chains) > self.max_chains:
            sorted_chains = sorted(self.chains.items(), key=lambda x: x[1].start_time)
            for chain_id, _ in sorted_chains[:len(self.chains) - self.max_chains]:
                del self.chains[chain_id]


# Global instance
_flow_storage: Optional[FlowStorage] = None


def get_flow_storage() -> FlowStorage:
    """Get global flow storage instance."""
    global _flow_storage
    if _flow_storage is None:
        _flow_storage = FlowStorage()
    return _flow_storage
