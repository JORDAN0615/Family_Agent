"""
PostgreSQL Context for replacing Mem0Context
"""
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PostgreSQLContext:
    """PostgreSQL-based context for agent conversations"""
    
    def __init__(self, user_id: Optional[str] = None, group_id: Optional[str] = None):
        self.user_id = user_id
        self.group_id = group_id
        self.metadata: Dict[str, Any] = {}
        
        logger.info(f"PostgreSQLContext created for user_id={user_id}, group_id={group_id}")
    
    def get_user_id(self) -> Optional[str]:
        """Get user ID"""
        return self.user_id
    
    def get_group_id(self) -> Optional[str]:
        """Get group ID"""
        return self.group_id
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata"""
        return self.metadata.get(key, default)
    
    def __repr__(self) -> str:
        return f"PostgreSQLContext(user_id={self.user_id}, group_id={self.group_id})"