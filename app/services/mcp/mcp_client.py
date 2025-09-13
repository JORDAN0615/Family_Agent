import asyncio
import logging
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class PlaywrightMCPClient:
    """專門用於連接 Playwright MCP server 的客戶端"""
    
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self._connected = False
        
    async def connect_to_playwright_server(self):
        """連接到 Playwright MCP server"""
        try:
            # 設定 Playwright MCP server 參數
            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "@playwright/mcp"],
                env=None
            )
            
            logger.info("正在連接到 Playwright MCP server...")
            
            # 建立通信管道
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            
            # 建立會話
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )
            
            # 初始化
            await self.session.initialize()
            
            # 列出可用工具
            response = await self.session.list_tools()
            tools = response.tools
            tool_names = [tool.name for tool in tools]
            
            logger.info(f"✅ 已連接到 Playwright MCP server，可用工具: {tool_names}")
            self._connected = True
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 連接 Playwright MCP server 失敗: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """調用 Playwright 工具"""
        if not self._connected or not self.session:
            raise Exception("未連接到 Playwright MCP server")
            
        try:
            logger.info(f"🔧 調用 Playwright 工具: {tool_name}")
            result = await self.session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"❌ 工具調用失敗: {tool_name} - {e}")
            raise
    
    async def close(self):
        """關閉連接"""
        if self.exit_stack:
            await self.exit_stack.aclose()
        self._connected = False
        logger.info("🔚 Playwright MCP client 已關閉")
    
    async def __aenter__(self):
        """Context manager 進入"""
        await self.connect_to_playwright_server()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 退出"""
        await self.close()

# 全域實例
_playwright_client: Optional[PlaywrightMCPClient] = None

async def get_playwright_client():
    """獲取或創建 Playwright MCP client"""
    global _playwright_client
    if _playwright_client is None:
        _playwright_client = PlaywrightMCPClient()
        await _playwright_client.connect_to_playwright_server()
    return _playwright_client