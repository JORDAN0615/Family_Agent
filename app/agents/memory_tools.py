"""
使用 Mem0 的記憶管理工具 - 基於官方 agentic tool 範例
適用於家庭助手多agent系統，支援LINE群組和個人記憶
"""
import logging
from typing import Optional
from pydantic import BaseModel
from agents import function_tool, RunContextWrapper
from mem0 import AsyncMemoryClient
from app.services.line.config import agent_settings

logger = logging.getLogger(__name__)

# 初始化 Mem0 客戶端
mem0_client = AsyncMemoryClient(api_key=agent_settings.Mem0_API_Key)


class Mem0Context(BaseModel):
    """記憶上下文，包含用戶識別資訊"""
    user_id: str | None = None
    group_id: str | None = None
    category: str = "general"  # preference, plan, fact, general


@function_tool
async def add_to_memory(
    context: RunContextWrapper[Mem0Context],
    content: str,
    category: str = "general",
) -> str:
    """
    添加記憶到長期記憶系統
    
    Args:
        content: 要記住的內容，比如重要約定、偏好、計劃等
        category: 記憶分類 (preference/plan/fact/general)
    
    Returns:
        記憶保存結果的描述
    """
    logger.info(f"[ADD_TO_MEMORY] 工具被調用")
    logger.info(f"[ADD_TO_MEMORY] 內容: {content}")
    logger.info(f"[ADD_TO_MEMORY] 分類: {category}")
    
    try:
        # 從上下文獲取用戶資訊
        if context.context is None:
            logger.warning(f"⚠️ [ADD_TO_MEMORY] Context is None, using default values")
            user_id = "default_user"
            group_id = None
        else:
            user_id = context.context.user_id or "default_user"
            group_id = context.context.group_id
        
        logger.info(f"[ADD_TO_MEMORY] 用戶ID: {user_id}")
        logger.info(f"[ADD_TO_MEMORY] 群組ID: {group_id}")
        
        # 構建記憶標識符
        memory_user_id = f"user_{user_id}"
        if group_id:
            memory_user_id = f"group_{group_id}_user_{user_id}"
        
        # 準備訊息格式
        messages = [{"role": "user", "content": content}]
        
        # 構建元數據
        metadata = {
            "category": category,
            "source": "family_agent",
            "user_id": user_id,
        }
        
        if group_id:
            metadata["group_id"] = group_id
        
        logger.info(f"🔗 [ADD_TO_MEMORY] 記憶標識符: {memory_user_id}")
        logger.info(f"📨 [ADD_TO_MEMORY] 準備發送到 Mem0 API")
        
        # 添加記憶
        await mem0_client.add(messages, user_id=memory_user_id, metadata=metadata)
        
        logger.info(f"✅ [ADD_TO_MEMORY] 成功保存到 Mem0")
        
        # 根據分類返回不同的確認訊息
        category_emoji = {
            "preference": "❤️",
            "plan": "📅",
            "fact": "📝",
            "general": "💭"
        }
        
        emoji = category_emoji.get(category, "💭")
        
        logger.info(f"Successfully added memory for user {user_id}: {content[:50]}...")
        return f"{emoji} 已成功記住：{content}\n\n這個記憶已保存到您的記憶庫中，我在未來的對話中會記得這個資訊。"
        
    except Exception as e:
        logger.error(f"[ADD_TO_MEMORY] 錯誤: {e}")
        logger.error(f"[ADD_TO_MEMORY] 錯誤類型: {type(e)}")
        return f"記憶保存時發生錯誤：{str(e)}"


@function_tool
async def search_memory(
    context: RunContextWrapper[Mem0Context],
    query: str,
    category: Optional[str] = None,
) -> str:
    """
    搜尋相關記憶
    
    Args:
        query: 搜尋關鍵詞，比如「餐廳」、「約定」、「偏好」等
        category: 記憶分類過濾 (preference/plan/fact/general)
    
    Returns:
        搜尋到的相關記憶內容
    """
    logger.info(f"[SEARCH_MEMORY] 工具被調用")
    logger.info(f"[SEARCH_MEMORY] 查詢: {query}")
    logger.info(f"[SEARCH_MEMORY] 分類過濾: {category}")
    
    try:
        # 從上下文獲取用戶資訊
        user_id = context.context.user_id or "default_user"
        group_id = context.context.group_id
        
        logger.info(f"[SEARCH_MEMORY] 用戶ID: {user_id}")
        logger.info(f"[SEARCH_MEMORY] 群組ID: {group_id}")
        
        # 構建記憶標識符
        memory_user_id = f"user_{user_id}"
        if group_id:
            memory_user_id = f"group_{group_id}_user_{user_id}"
        
        # 搜尋記憶
        results = await mem0_client.search(
            query=query,
            user_id=memory_user_id,
            limit=5
        )
        
        if not results:
            return f"沒有找到與「{query}」相關的記憶。\n\n可能是我還沒有記錄過相關資訊，或者您可以嘗試使用不同的關鍵詞搜尋。"
        
        # 過濾分類（如果指定的話）
        if category:
            filtered_results = []
            for result in results:
                result_category = result.get("metadata", {}).get("category", "general")
                if result_category == category:
                    filtered_results.append(result)
            results = filtered_results
        
        if not results:
            return f"沒有找到「{query}」在「{category}」分類中的相關記憶。"
        
        # 格式化搜尋結果
        result_lines = [f"🧠 找到 {len(results)} 個相關記憶：\n"]
        
        for i, memory in enumerate(results, 1):
            content = memory.get("memory", "")
            metadata = memory.get("metadata", {})
            memory_category = metadata.get("category", "general")
            
            category_emoji = {
                "preference": "❤️",
                "plan": "📅",
                "fact": "📝",
                "general": "💭"
            }.get(memory_category, "💭")
            
            result_lines.append(f"{i}. {category_emoji} {content}")
        
        result = "\n".join(result_lines)
        logger.info(f"Found {len(results)} memories for query: {query}")
        return result
        
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return f"搜尋記憶時發生錯誤：{str(e)}"


@function_tool
async def get_all_memory(
    context: RunContextWrapper[Mem0Context],
) -> str:
    """
    獲取用戶所有記憶的摘要
    
    Returns:
        用戶所有記憶的摘要
    """
    logger.info(f"[GET_ALL_MEMORY] 工具被調用")
    
    try:
        # 從上下文獲取用戶資訊
        user_id = context.context.user_id or "default_user"
        group_id = context.context.group_id
        
        logger.info(f"[GET_ALL_MEMORY] 用戶ID: {user_id}")
        logger.info(f"[GET_ALL_MEMORY] 群組ID: {group_id}")
        
        # 構建記憶標識符
        memory_user_id = f"user_{user_id}"
        if group_id:
            memory_user_id = f"group_{group_id}_user_{user_id}"
        
        logger.info(f"[GET_ALL_MEMORY] 記憶標識符: {memory_user_id}")
        logger.info(f"[GET_ALL_MEMORY] 準備發送到 Mem0 API")
        
        # 獲取所有記憶
        memories = await mem0_client.get_all(user_id=memory_user_id)
        
        logger.info(f"[GET_ALL_MEMORY] 獲取記憶數量: {len(memories) if memories else 0}")
        
        if not memories:
            return "📝 目前還沒有記錄任何記憶。\n\n您可以告訴我一些重要的資訊，我會幫您記住。"
        
        # 按分類整理記憶
        categorized = {
            "preference": [],
            "plan": [],
            "fact": [],
            "general": []
        }
        
        for memory in memories:
            content = memory.get("memory", "")
            category = memory.get("metadata", {}).get("category", "general")
            categorized[category].append(content)
        
        # 格式化結果
        result_lines = [f"📚 您的記憶庫摘要 (共 {len(memories)} 條記憶)：\n"]
        
        category_names = {
            "preference": "❤️ 偏好設定",
            "plan": "📅 計劃安排",
            "fact": "📝 重要事實",
            "general": "💭 一般記憶"
        }
        
        for category, category_memories in categorized.items():
            if category_memories:
                result_lines.append(f"\n{category_names[category]}:")
                for memory in category_memories[:3]:  # 只顯示前3個
                    result_lines.append(f"  • {memory}")
                
                if len(category_memories) > 3:
                    result_lines.append(f"  ... 還有 {len(category_memories) - 3} 條記憶")
        
        result = "\n".join(result_lines)
        logger.info(f"✅ [GET_ALL_MEMORY] 成功返回記憶摘要")
        return result
        
    except Exception as e:
        logger.error(f"❌ [GET_ALL_MEMORY] 錯誤: {e}")
        logger.error(f"❌ [GET_ALL_MEMORY] 錯誤類型: {type(e)}")
        return f"❌ 獲取記憶時發生錯誤：{str(e)}"


@function_tool
async def delete_memory(
    context: RunContextWrapper[Mem0Context],
    memory_id: str,
) -> str:
    """
    刪除特定記憶
    
    Args:
        memory_id: 要刪除的記憶ID
    
    Returns:
        刪除結果的描述
    """
    try:
        user_id = context.context.user_id or "default_user"
        
        # 刪除記憶
        await mem0_client.delete(memory_id=memory_id)
        
        logger.info(f"Deleted memory {memory_id} for user {user_id}")
        return f"🗑️ 已成功刪除記憶。"
        
    except Exception as e:
        logger.error(f"Error deleting memory {memory_id}: {e}")
        return f"❌ 刪除記憶時發生錯誤：{str(e)}"


# 為了向後兼容，保留舊的函數名稱
@function_tool
async def save_group_message(
    context: RunContextWrapper[Mem0Context],
    content: str,
    category: str = "general",
) -> str:
    """
    儲存群組訊息到記憶中（向後兼容）
    """
    return await add_to_memory(context, content, category)


@function_tool
async def search_group_memory(
    context: RunContextWrapper[Mem0Context],
    query: str,
    category: Optional[str] = None,
) -> str:
    """
    搜尋群組記憶（向後兼容）
    """
    return await search_memory(context, query, category)