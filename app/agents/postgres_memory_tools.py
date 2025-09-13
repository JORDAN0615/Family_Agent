"""
PostgreSQL memory tools for agents
"""
from .postgres_tools import search_context, update_context
from .postgres_context import PostgreSQLContext
import logging
from agents import function_tool, RunContextWrapper
from typing import Optional

logger = logging.getLogger(__name__)

@function_tool
async def search_conversation_memory(
    context: RunContextWrapper[PostgreSQLContext]
) -> str:
    """
    搜尋用戶的對話歷史記錄
    
    Returns:
        格式化的對話歷史，如果沒有找到則回傳提示訊息
    """
    logger.info("[SEARCH_CONVERSATION_MEMORY] 工具被調用")
    
    try:
        # 從上下文獲取用戶資訊
        if context.context is None:
            logger.warning("Context is None, cannot search conversation history")
            return "無法搜尋對話歷史：缺少用戶上下文"
        
        user_id = context.context.get_user_id()
        if not user_id:
            logger.warning("User ID not found in context")
            return "無法搜尋對話歷史：缺少用戶ID"
        
        logger.info(f"搜尋用戶 {user_id} 的對話歷史")
        conversation_context = await search_context(user_id)
        
        if conversation_context:
            logger.info(f"找到對話歷史，長度: {len(conversation_context)}")
            return conversation_context
        else:
            logger.info("沒有找到對話歷史")
            return "沒有找到歷史對話記錄"
            
    except Exception as e:
        logger.error(f"搜尋對話歷史失敗: {e}")
        return f"搜尋對話歷史時發生錯誤: {str(e)}"

@function_tool
async def save_conversation_memory(
    context: RunContextWrapper[PostgreSQLContext],
    user_input: str,
    ai_response: str
) -> str:
    """
    儲存對話到 PostgreSQL 資料庫
    
    Args:
        user_input: 用戶輸入內容
        ai_response: AI 回應內容
        
    Returns:
        儲存結果訊息
    """
    logger.info("[SAVE_CONVERSATION_MEMORY] 工具被調用")
    logger.info(f"用戶輸入: {user_input[:100]}...")
    logger.info(f"AI 回應: {ai_response[:100]}...")
    
    try:
        # 從上下文獲取用戶資訊
        if context.context is None:
            logger.warning("Context is None, cannot save conversation")
            return "無法儲存對話：缺少用戶上下文"
        
        user_id = context.context.get_user_id()
        group_id = context.context.get_group_id()
        
        if not user_id:
            logger.warning("User ID not found in context")
            return "無法儲存對話：缺少用戶ID"
        
        logger.info(f"儲存對話 - 用戶: {user_id}, 群組: {group_id}")
        success = await update_context(user_id, group_id, user_input, ai_response)
        
        if success:
            logger.info("對話儲存成功")
            return "對話已成功儲存到資料庫"
        else:
            logger.error("對話儲存失敗")
            return "對話儲存失敗"
            
    except Exception as e:
        logger.error(f"儲存對話失敗: {e}")
        return f"儲存對話時發生錯誤: {str(e)}"