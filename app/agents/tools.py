import requests
import json
import urllib.parse
from firecrawl import FirecrawlApp
from app.services.line.config import agent_settings
from agents import (
    Agent,
    ItemHelpers,
    MessageOutputItem,
    RunContextWrapper,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    TResponseInputItem,
    function_tool,
    result,
)
from mem0 import AsyncMemoryClient
from pydantic import BaseModel
 
mem0client = AsyncMemoryClient(api_key=agent_settings.Mem0_API_Key)
firecrawl = FirecrawlApp(api_key=agent_settings.FIRECRAWL_API_KEY)
googleApiKey = agent_settings.Google_API_Key

class Mem0Context(BaseModel):
    user_id: str | None = None


@function_tool
def summarize_url(url: str) -> str:
    """
    使用 Firecrawl 抓取網址內容並提供摘要

    Args:
        url: 要摘要的網址

    Returns:
      網站內容的摘要文字
    """
    try:
        # 爬取網站
        response = firecrawl.scrape_url(
            url, formats=["markdown"], only_main_content=True
        )
        if response and hasattr(response, "markdown") and response.markdown:
            content = response.markdown
            if len(content) > 1000:
                content = content[:1000] + "..."

            return f"網站內容摘要：\n{content}"
        else:
            return "無法抓取網站內容"

    except Exception as e:
        return f"抓取網站時發生錯誤：{str(e)}"


@function_tool
def search_places_tool(query: str, location: str = "台灣") -> str:
    """
    使用 Google Places API 搜尋詳細餐廳資訊

    Args:
        query: 餐廳名稱或搜尋關鍵字
        location: 搜尋地點，預設為台灣

    Returns:
        詳細餐廳資訊
    """
    try:
        api_key = googleApiKey
        if not api_key or api_key == "your_google_places_api_key_here":
            return "⚠️ Google Places API Key 尚未設定\n請在 .env 檔案中設定 GOOGLE_PLACES_API_KEY"
        
        url = "https://places.googleapis.com/v1/places:searchText"

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.location,places.priceLevel"
        }

        payload = {
            "textQuery": f"{query} restaurant {location}",
            "maxResultCount": 5
        }
    
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if 'places' in data and len(data['places']) > 0:
                result = f"🍽️ 搜尋結果：{query} @ {location}\n\n"
                for i, place in enumerate(data['places'], 1):
                    name = place.get('displayName', {}).get('text', 'N/A')
                    address = place.get('formattedAddress', 'N/A')
                    rating = place.get('rating', 'N/A')
                    price_level = place.get('priceLevel', 'N/A')
                    
                    # 創建 Google Maps 搜尋連結
                    search_query = f"{name}"
                    encoded_query = urllib.parse.quote(search_query)
                    maps_url = f"https://www.google.com/maps/search/{encoded_query}"

                    result += f"{i}. 📍 {name}\n"
                    result += f"   地址：{address}\n"
                    result += f"   評分：⭐ {rating}\n"
                    result += f"   價位：{price_level}\n"
                    result += f"   🗺️ Google Maps: {maps_url}\n\n"
            
                return result
            else:
                return f"❌ 沒有找到相關餐廳：{query} @ {location}"
        else:
            error_msg = f"API 請求失敗：HTTP {response.status_code}"
            if response.text:
                error_msg += f"\n錯誤訊息：{response.text}"
            return error_msg

    except Exception as e:
        return f"❌ 使用 Google Places API 時發生錯誤：{str(e)}"



# 簡單的記憶儲存
_memory_storage = []


@function_tool
def save_group_message(message: str, sender: str = "未知用戶") -> str:
    """
    儲存群組訊息到記憶中

    Args:
        message: 要儲存的訊息內容
        sender: 傳送者名稱

    Returns:
        儲存結果確認
    """
    try:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memory_item = {"timestamp": timestamp, "sender": sender, "message": message}

        _memory_storage.append(memory_item)

        # 限制記憶數量（最多保留 50 條）
        if len(_memory_storage) > 50:
            _memory_storage.pop(0)

        return f"✅ 已儲存訊息到記憶中\n傳送者：{sender}\n時間：{timestamp}"

    except Exception as e:
        return f"儲存訊息時發生錯誤：{str(e)}"


@function_tool
def search_group_memory(query: str = "") -> str:
    """
    搜尋群組訊息記憶

    Args:
        query: 搜尋關鍵字，留空則顯示最近訊息

    Returns:
        符合條件的訊息記錄
    """
    try:
        if not _memory_storage:
            return "📝 目前沒有儲存任何群組訊息記憶"

        if query:
            # 搜尋包含關鍵字的訊息
            matching_messages = [
                item
                for item in _memory_storage
                if query.lower() in item["message"].lower()
                or query.lower() in item["sender"].lower()
            ]

            if not matching_messages:
                return f'🔍 搜尋 "{query}" 沒有找到相關訊息'

            result = f'🔍 搜尋結果 "{query}" ({len(matching_messages)} 條)：\n\n'
            for item in matching_messages[-10:]:  # 最多顯示 10 條
                result += f"[{item['timestamp']}] {item['sender']}: {item['message']}\n"

            return result
        else:
            # 顯示最近的訊息
            recent_messages = _memory_storage[-10:]  # 最近 10 條
            result = f"📝 最近的群組訊息 ({len(recent_messages)} 條)：\n\n"
            for item in recent_messages:
                result += f"[{item['timestamp']}] {item['sender']}: {item['message']}\n"

            return result

    except Exception as e:
        return f"搜尋記憶時發生錯誤：{str(e)}"


# def _search_places_raw(query: str, location: str = "台灣") -> str:
#     """原始搜尋函數，用於測試"""
#     try:
#         api_key = googleApiKey
#         url = "https://places.googleapis.com/v1/places:searchText"

#         headers = {
#             "Content-Type": "application/json",
#             "X-Goog-Api-Key": api_key,
#             "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.location"
#         }

#         payload = {
#             "textQuery": f"{query} {location}",
#             "maxResultCount": 5
#         }

#         response = requests.post(url, headers=headers, json=payload)
        
#         if response.status_code == 200:
#             data = response.json()
#             if 'places' in data and len(data['places']) > 0:
#                 result = f"🍽️ 搜尋結果：{query} @ {location}\n\n"
#                 for i, place in enumerate(data['places'], 1):
#                     name = place.get('displayName', {}).get('text', 'N/A')
#                     address = place.get('formattedAddress', 'N/A')
#                     rating = place.get('rating', 'N/A')
#                     price_level = place.get('priceLevel', 'N/A')
                    
#                     # 創建 Google Maps 搜尋連結
#                     search_query = f"{name}"
#                     encoded_query = urllib.parse.quote(search_query)
#                     maps_url = f"https://www.google.com/maps/search/{encoded_query}"

#                     result += f"{i}. 📍 {name}\n"
#                     result += f"   🗺️ 連結：{maps_url}\n"
#                     result += f"   地址：{address}\n"
#                     result += f"   評分：⭐ {rating}\n"
#                 return result
#             else:
#                 return f"❌ 沒有找到相關餐廳：{query} @ {location}"
#         else:
#             return f"API 請求失敗：{response.status_code} - {response.text}"

#     except Exception as e:
#         return f"搜尋時發生錯誤：{str(e)}"


# if __name__ == "__main__":
#     # 測試用
#     print("測試 Google Places API...")
#     result = _search_places_raw('拉麵', '大安區')
#     print(f"結果:\n{result}")