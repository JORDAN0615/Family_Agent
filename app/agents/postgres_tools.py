import asyncio
import asyncpg
import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ConversationRecord:
    id: Optional[int]
    user_id: str
    group_id: Optional[str]
    content: str
    role: str  # 'user' or 'ai'
    timestamp: datetime

class PostgreSQLTools:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
    
    async def initialize(self):
        """Create connection pool and tables"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60,
            )
            logger.info("PostgreSQL connection pool created")
            
            await self.create_table()
            logger.info("Database table setup completed")
            
        except Exception as e:
            logger.error(f"PostgreSQL initialization failed: {e}")
            raise
    
    async def create_table(self):
        """Create conversation history table"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS conversation_history (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            group_id VARCHAR(100),
            content TEXT NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'ai')),
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_user_timestamp ON conversation_history (user_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_group_timestamp ON conversation_history (group_id, timestamp DESC);
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(create_table_sql)
            logger.info("conversation_history table ready")
    
    async def search_conversation_history(
        self, 
        user_id: str, 
        limit: int = 6
    ) -> List[ConversationRecord]:
        """Search user conversation history"""
        try:
            search_sql = """
            (
                SELECT id, user_id, group_id, content, role, timestamp
                FROM conversation_history 
                WHERE user_id = $1 AND role = 'user'
                ORDER BY timestamp DESC 
                LIMIT $2
            )
            UNION ALL
            (
                SELECT id, user_id, group_id, content, role, timestamp
                FROM conversation_history 
                WHERE user_id = $1 AND role = 'ai'
                ORDER BY timestamp DESC 
                LIMIT $2
            )
            ORDER BY timestamp DESC
            LIMIT $3
            """
            
            user_limit = limit // 2
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(search_sql, user_id, user_limit, limit)
                
                conversations = []
                for row in rows:
                    conversations.append(ConversationRecord(
                        id=row['id'],
                        user_id=row['user_id'],
                        group_id=row['group_id'],
                        content=row['content'],
                        role=row['role'],
                        timestamp=row['timestamp']
                    ))
                
                logger.info(f"Found {len(conversations)} records for user {user_id}")
                return conversations
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def update_conversation_history(
        self,
        user_id: str,
        group_id: Optional[str],
        user_input: str,
        ai_response: str
    ) -> bool:
        """Insert user input and AI response"""
        try:
            insert_sql = """
            INSERT INTO conversation_history (user_id, group_id, content, role)
            VALUES ($1, $2, $3, $4)
            """
            
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(insert_sql, user_id, group_id, user_input, 'user')
                    await conn.execute(insert_sql, user_id, group_id, ai_response, 'ai')
                    
                logger.info(f"Conversation saved for user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            return False
    
    async def format_context_for_agent(
        self, 
        conversations: List[ConversationRecord]
    ) -> str:
        """Format conversations for agent context"""
        if not conversations:
            return ""
        
        context_parts = ["=== Conversation History ==="]
        
        # Sort by timestamp (old to new)
        sorted_conversations = sorted(conversations, key=lambda x: x.timestamp)
        
        for conv in sorted_conversations:
            role_label = "User" if conv.role == "user" else "Assistant"
            timestamp_str = conv.timestamp.strftime("%Y-%m-%d %H:%M")
            context_parts.append(f"{role_label} ({timestamp_str}): {conv.content}")
        
        context_parts.append("=== End of History ===")
        
        return "\n".join(context_parts)
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection closed")

# Global instance
postgres_tools = None

async def get_postgres_tools() -> PostgreSQLTools:
    """Get PostgreSQL tools instance (singleton)"""
    global postgres_tools
    
    if postgres_tools is None:
        database_url = os.getenv("DATABASE_URL", "postgres://user:password@localhost:5432/defaultdb")
        postgres_tools = PostgreSQLTools(database_url)
        await postgres_tools.initialize()
    
    return postgres_tools

# Convenience functions
async def search_context(user_id: str) -> str:
    """Search and format user conversation context"""
    tools = await get_postgres_tools()
    conversations = await tools.search_conversation_history(user_id)
    return await tools.format_context_for_agent(conversations)

async def update_context(
    user_id: str,
    group_id: Optional[str],
    user_input: str,
    ai_response: str
) -> bool:
    """Update conversation context"""
    tools = await get_postgres_tools()
    return await tools.update_conversation_history(user_id, group_id, user_input, ai_response)


if __name__ == "__main__":
    async def test_postgres_tools():
        """Test PostgreSQL tools"""
        try:
            print("Starting PostgreSQL test...")
            
            # Test search (should be empty)
            context = await search_context("test_user")
            print(f"Initial context: {context}")
            
            # Test insert
            success = await update_context(
                "Ubbc0af30b6869c08c7dbfedb1a6946a7",
                "None",
                "Hello, Jordan testing",
                "Hello! I am your Family_assistant, ready to help!"
            )
            print(f"Insert result: {success}")
            
            # Search again
            context = await search_context("Ubbc0af30b6869c08c7dbfedb1a6946a7")
            print(f"Context after insert: {context}")
            
            print("PostgreSQL test completed!")
            
        except Exception as e:
            print(f"Test failed: {e}")
        finally:
            if postgres_tools:
                await postgres_tools.close()
    
    asyncio.run(test_postgres_tools())