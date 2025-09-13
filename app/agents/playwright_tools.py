from agents import function_tool
from app.services.mcp.mcp_client import get_playwright_client
import logging

logger = logging.getLogger(__name__)

@function_tool
async def playwright_screenshot(url: str, selector: str = None) -> str:
    """
    使用 Playwright 對網頁截圖
    
    Args:
        url: 要截圖的網址
        selector: 可選的 CSS 選擇器，用於截取特定元素
    
    Returns:
        截圖結果描述
    """
    try:
        client = await get_playwright_client()
        args = {"url": url}
        if selector:
            args["selector"] = selector
            
        result = await client.call_tool("browser_take_screenshot", args)
        return f"📸 已對 {url} 截圖完成"
        
    except Exception as e:
        logger.error(f"Playwright 截圖失敗: {e}")
        return f"❌ 截圖失敗: {str(e)}"

@function_tool
async def playwright_navigate(url: str) -> str:
    """
    使用 Playwright 導航到指定網頁
    
    Args:
        url: 要導航的網址
    
    Returns:
        導航結果
    """
    try:
        client = await get_playwright_client()
        result = await client.call_tool("browser_navigate", {"url": url})
        return f"✅ 已成功導航到 {url}"
        
    except Exception as e:
        logger.error(f"Playwright 導航失敗: {e}")
        return f"❌ 導航失敗: {str(e)}"

@function_tool
async def playwright_click(url: str, selector: str) -> str:
    """
    使用 Playwright 點擊網頁元素
    
    Args:
        url: 目標網址
        selector: 要點擊的元素 CSS 選擇器
    
    Returns:
        點擊結果
    """
    try:
        client = await get_playwright_client()
        result = await client.call_tool("browser_click", {
            "selector": selector
        })
        return f"👆 已點擊元素 {selector}"
        
    except Exception as e:
        logger.error(f"Playwright 點擊失敗: {e}")
        return f"❌ 點擊失敗: {str(e)}"

@function_tool
async def playwright_extract_text(url: str, selector: str = None) -> str:
    """
    使用 Playwright 提取網頁文字內容
    
    Args:
        url: 目標網址
        selector: 可選的 CSS 選擇器，提取特定元素的文字
    
    Returns:
        提取的文字內容
    """
    try:
        client = await get_playwright_client()
        args = {"url": url}
        if selector:
            args["selector"] = selector
            
        result = await client.call_tool("browser_evaluate", {
            "function": f"() => document.querySelector('{selector}')?.textContent || document.body.textContent" if selector else "() => document.body.textContent"
        })
        return f"📝 已提取文字內容: {result}"
        
    except Exception as e:
        logger.error(f"Playwright 文字提取失敗: {e}")
        return f"❌ 文字提取失敗: {str(e)}"

# @function_tool
async def restaurant_reservation(
    url: str, 
    party_size: int = 2, 
    date: str = None, 
    time: str = None
) -> str:
    """
    自動化餐廳預約系統
    
    Args:
        url: 餐廳預約網址
        party_size: 用餐人數 (預設2人)
        date: 用餐日期 YYYY-MM-DD 格式 (預設明天)
        time: 偏好時段，如 "19:00", "7:00 PM" (預設自動選擇第一個可用)
    
    Returns:
        預約結果詳情
    """
    try:
        import asyncio
        from datetime import datetime, timedelta
        
        client = await get_playwright_client()
        
        # 步驟 1: 導航並分析頁面
        logger.info(f"🌐 正在訪問預約網站: {url}")
        await client.call_tool("browser_navigate", {"url": url})
        await asyncio.sleep(3)
        
        # 步驟 2: 設定用餐人數
        logger.info(f"👥 設定用餐人數: {party_size}")
        party_success = await client.call_tool("browser_evaluate", {
            "function": f"""
            (() => {{
                // 嘗試各種人數選擇方式
                const methods = [
                    // 方法1: 下拉選單
                    () => {{
                        const selects = document.querySelectorAll('select');
                        for (const select of selects) {{
                            const name = (select.name || select.className || '').toLowerCase();
                            if (name.includes('party') || name.includes('guest') || name.includes('people')) {{
                                select.value = '{party_size}';
                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        return false;
                    }},
                    // 方法2: 數字按鈕
                    () => {{
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {{
                            if (btn.textContent.trim() === '{party_size}' || 
                                btn.getAttribute('data-value') === '{party_size}') {{
                                btn.click();
                                return true;
                            }}
                        }}
                        return false;
                    }},
                    // 方法3: 輸入框
                    () => {{
                        const inputs = document.querySelectorAll('input[type="number"]');
                        for (const input of inputs) {{
                            const name = (input.name || input.className || '').toLowerCase();
                            if (name.includes('party') || name.includes('guest')) {{
                                input.value = '{party_size}';
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        return false;
                    }}
                ];
                
                for (const method of methods) {{
                    if (method()) {{
                        return {{ success: true, method: methods.indexOf(method) + 1 }};
                    }}
                }}
                
                return {{ success: false, method: 0 }};
            }})()
            """
        })
        
        # 步驟 3: 設定日期
        if not date:
            date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"📅 設定用餐日期: {date}")
        date_success = await client.call_tool("browser_evaluate", {
            "function": f"""
            (() => {{
                // 嘗試各種日期設定方式
                const dateInput = document.querySelector('input[type="date"]');
                if (dateInput) {{
                    dateInput.value = '{date}';
                    dateInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return {{ success: true, method: 'date-input' }};
                }}
                
                // 其他日期選擇方式...
                return {{ success: false, method: 'none' }};
            }})()
            """
        })
        
        # 等待頁面更新
        await asyncio.sleep(2)
        
        # 步驟 4: 尋找並選擇時段
        logger.info("⏰ 搜尋可用時段...")
        time_slots_result = await client.call_tool("browser_evaluate", {
            "function": """
            (() => {{
                const timeButtons = Array.from(document.querySelectorAll('button, div, span')).filter(el => {{
                    const text = el.textContent.trim();
                    // 匹配時間格式: 12:00, 7:30 PM, 19:00 等
                    return /\\b\\d{{1,2}}:\\d{{2}}(\\s*(AM|PM))?\\b/i.test(text) && 
                           !el.disabled && 
                           el.style.display !== 'none' &&
                           !el.className.includes('disabled');
                }});
                
                return timeButtons.map(btn => {{
                    const timeMatch = btn.textContent.match(/\\b(\\d{{1,2}}:\\d{{2}}(?:\\s*(?:AM|PM))?)\\b/i);
                    return {{
                        text: btn.textContent.trim(),
                        time: timeMatch ? timeMatch[1] : '',
                        element: btn.tagName,
                        clickable: btn.tagName === 'BUTTON' || btn.onclick !== null,
                        className: btn.className
                    }};
                }}).filter(slot => slot.time);
            }})()
            """
        })
        
        # 提取實際的結果數據
        import json
        time_slots = []
        if hasattr(time_slots_result, 'content') and time_slots_result.content:
            try:
                if isinstance(time_slots_result.content, list) and len(time_slots_result.content) > 0:
                    time_slots = json.loads(time_slots_result.content[0].text)
            except (json.JSONDecodeError, AttributeError):
                time_slots = []
        
        if not time_slots or (isinstance(time_slots, (list, tuple)) and len(time_slots) == 0):
            return "❌ 找不到可用的時段，請檢查日期設定或稍後再試"
        
        # 選擇時段
        selected_slot = time_slots[0]  # 預設選第一個
        if time:  # 如果有指定偏好時間
            for slot in time_slots:
                if time.lower() in slot['time'].lower():
                    selected_slot = slot
                    break
        
        logger.info(f"🎯 選擇時段: {selected_slot['time']}")
        
        # 步驟 5: 點擊選擇的時段
        click_success = await client.call_tool("browser_evaluate", {
            "function": f"""
            (() => {{
                const timeButtons = Array.from(document.querySelectorAll('button, div, span'));
                const targetButton = timeButtons.find(btn => 
                    btn.textContent.includes('{selected_slot["time"]}')
                );
                
                if (targetButton) {{
                    targetButton.click();
                    return {{ success: true, clicked: targetButton.textContent.trim() }};
                }}
                
                return {{ success: false, clicked: null }};
            }})()
            """
        })
        
        await asyncio.sleep(1)
        
        # 步驟 6: 點擊預約按鈕
        logger.info("🎉 執行預約...")
        booking_result = await client.call_tool("browser_evaluate", {
            "function": """
            (() => {{
                const bookingKeywords = ['訂位', '預約', '確認', 'book', 'reserve', 'confirm'];
                const buttons = Array.from(document.querySelectorAll('button'));
                
                for (const keyword of bookingKeywords) {{
                    const btn = buttons.find(b => 
                        b.textContent.toLowerCase().includes(keyword.toLowerCase()) &&
                        !b.disabled
                    );
                    if (btn) {{
                        btn.click();
                        return {{ 
                            success: true, 
                            button: btn.textContent.trim(),
                            keyword: keyword 
                        }};
                    }}
                }}
                
                return {{ success: false, available_buttons: buttons.map(b => b.textContent.trim()).slice(0, 5) }};
            }})()
            """
        })
        
        # 等待結果
        await asyncio.sleep(2)
        
        # 截圖最終結果
        await client.call_tool("browser_take_screenshot", {})
        
        # 組合結果
        result_parts = []
        result_parts.append(f"🍽️ 餐廳預約完成")
        result_parts.append(f"👥 人數: {party_size}人")
        result_parts.append(f"📅 日期: {date}")
        result_parts.append(f"⏰ 時段: {selected_slot['time']}")
        
        if party_success.get('success'):
            result_parts.append("✅ 人數設定成功")
        else:
            result_parts.append("⚠️ 人數設定可能失敗")
            
        if date_success.get('success'):
            result_parts.append("✅ 日期設定成功")
        else:
            result_parts.append("⚠️ 日期設定可能失敗")
            
        if click_success.get('success'):
            result_parts.append("✅ 時段選擇成功")
        else:
            result_parts.append("⚠️ 時段選擇可能失敗")
            
        if booking_result.get('success'):
            result_parts.append(f"🎉 預約按鈕已點擊: {booking_result['button']}")
        else:
            result_parts.append("⚠️ 找不到預約按鈕，可能需要手動完成")
        
        result_parts.append(f"📸 已截圖保存結果")
        
        return "\n".join(result_parts)
        
    except Exception as e:
        logger.error(f"餐廳預約失敗: {e}")
        return f"❌ 預約過程發生錯誤: {str(e)}"