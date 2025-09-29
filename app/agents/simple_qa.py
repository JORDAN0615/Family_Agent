import asyncio
from agents import (
    Agent,
    Runner,
    RunConfig,
    set_tracing_disabled,
    OpenAIChatCompletionsModel,
)
from agents import RunHooks
import logging
import asyncpg
from openai import AsyncOpenAI, RateLimitError
from .tools import (
    summarize_url,
    search_places_tool,
)
# from .memory_tools import (
#     add_to_memory,
#     search_memory,
#     Mem0Context,
# )
from .postgres_tools import (
    search_context,
    update_context,
)
from .postgres_memory_tools import (
    search_conversation_memory,
    save_conversation_memory,
)
from .postgres_context import PostgreSQLContext
from app.services.line.config import agent_settings
from agents.mcp import MCPServerStdio
from agents.run_context import RunContextWrapper

# 啟用 OpenAI 追蹤以便調試
# set_tracing_disabled(False)
# 設置looger
logger = logging.getLogger(__name__)

# 設置 Gemini client
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
gemini_client = AsyncOpenAI(
    base_url=GEMINI_BASE_URL, api_key=agent_settings.GEMINI_API_KEY
)
local_client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="dummy")
openai_client = AsyncOpenAI(api_key=agent_settings.OPENAI_API_KEY)


# Task Plan Logging Hooks
class TaskPlanLoggingHooks(RunHooks):
    """用於追蹤 Agent 執行流程的 Hooks"""
    
    async def on_agent_start(self, context, agent):
        logger.info(f"Agent 啟動: {agent.name}")
    
    async def on_handoff(self, context, from_agent, to_agent):
        logger.info(f"Agent 切換: {from_agent.name} → {to_agent.name}")
    
    async def on_tool_start(self, context, agent, tool):
        tool_name = getattr(tool, 'name', str(tool))
        logger.info(f"工具呼叫開始: {agent.name} → {tool_name}")
    
    async def on_tool_end(self, context, agent, tool, result):
        tool_name = getattr(tool, 'name', str(tool))
        result_preview = result[:100] + "..." if len(result) > 100 else result
        logger.info(f"工具呼叫完成: {tool_name}")
    
    async def on_llm_start(self, context, agent, system_prompt, input_items):
        logger.info(f"LLM 開始: {agent.name}")
    
    async def on_llm_end(self, context, agent, response):
        logger.info(f"LLM 完成: {agent.name}")


class SimpleQA:
    def __init__(self):
        # 延遲初始化，避免在導入時建立連線
        self.model = None
        self.triage_agent = None
        self.db_url = agent_settings.DATABASE_URL
        self._initialized = False

    def _init_model(self):
        """延遲初始化模型"""
        if self.model is None:
            self.model = OpenAIChatCompletionsModel(
                model="gemini-2.5-flash",
                openai_client=gemini_client,
            )

    # -------- 上下文記憶系統 -------- #
    
    async def init_memory_db(self):
        """初始化對話記憶資料庫表"""
        conn = await asyncpg.connect(self.db_url)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id SERIAL PRIMARY KEY,
                    user_input TEXT NOT NULL,
                    agent_output TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("對話記憶表初始化完成")
        finally:
            await conn.close()
    
    async def get_context(self) -> str:
        """獲取最近5筆對話作為上下文字串"""
        logger.info(f"[MEMORY] 開始獲取對話記憶，資料庫URL: {self.db_url}")
        conn = await asyncpg.connect(self.db_url)
        try:
            logger.info(f"[MEMORY] 資料庫連線成功，執行查詢...")
            rows = await conn.fetch(
                "SELECT user_input, agent_output FROM conversation_history ORDER BY created_at DESC LIMIT 2"
            )
            logger.info(f"[MEMORY] 查詢完成，找到 {len(rows)} 筆記錄")

            if not rows:
                logger.info(f"[MEMORY] 沒有找到任何對話記錄")
                return ""

            # 詳細記錄每筆資料
            for i, row in enumerate(rows):
                logger.info(f"[MEMORY] 記錄 {i+1}: user_input='{row['user_input'][:50]}...', agent_output='{row['agent_output'][:50]}...'")

            # 組成對話歷史字串
            context_lines = ["=== 最近的對話記錄 ==="]
            for row in reversed(rows):  # 反轉以保持時間順序
                context_lines.append(f"用戶: {row['user_input'][:100]}...")  # 限制用戶輸入長度
                context_lines.append(f"助理: {row['agent_output'][:100]}...")  # 限制助理回應長度
                context_lines.append("---")

            result = "\n".join(context_lines)
            logger.info(f"[MEMORY] 組成的上下文長度: {len(result)} 字符")
            logger.info(f"[MEMORY] 上下文內容預覽: {result[:200]}...")
            return result
        finally:
            await conn.close()
            logger.info(f"[MEMORY] 資料庫連線已關閉")
    
    async def save_conversation(self, user_input: str, agent_output: str):
        """保存對話記錄"""
        conn = await asyncpg.connect(self.db_url)
        try:
            await conn.execute(
                "INSERT INTO conversation_history (user_input, agent_output) VALUES ($1, $2)",
                user_input, agent_output
            )
            logger.info("對話記錄已保存")
        finally:
            await conn.close()

        
    
    async def create_agents(self):
        """創建不依賴 MCP 的 agents"""
        # 確保模型已初始化
        self._init_model()

        # 2. 定義其他專業 agents
        summarize_agent = Agent(
            name="Summarize Agent",
            instructions="""
                你是 曾曾有一室Agent，一個專業的網站內容摘要專家。

                核心任務
                - 專門處理網址內容摘要
                - 使用 summarize_url 工具分析網站內容
                - 自動記憶重要的網站內容和用戶興趣

                執行規則
                - 主動搜尋使用者的對話歷史
                - 分析網站內容並提供有用摘要
                - 儲存重要發現到對話記憶
                - 不處理餐廳推薦和地點搜尋

                職責邊界
                - 專門處理網站內容分析和摘要
                - 不處理餐廳推薦和地點搜尋
                - 不處理瀏覽器操作和預約功能
            """,
            model=self.model,
            tools=[summarize_url],
        )

        foodie_agent = Agent(
            name="restaurant recommend Agent",
            instructions="""
                你是 曾曾有一室Agent，一個專業的餐廳推薦專家，精通台灣各地美食與景點。

                核心能力
                - 餐廳推薦與美食搜尋
                - 地點推薦與旅遊建議
                - Google Maps 地點搜尋與資訊獲取
                - 自動記憶用戶的美食偏好和習慣

                工具使用
                - google_maps_search：搜尋餐廳、景點位置資訊
                - search_conversation_memory：搜尋用戶的對話歷史和偏好
                - save_conversation_memory：儲存重要的美食體驗和偏好

                智能對話處理與記憶管理（PostgreSQL）
                - **記憶使用規則**：
                  * 任務開始時：使用 search_conversation_memory 搜尋用戶的美食偏好和歷史
                  * 推薦時考慮：歷史偏好 + 當前需求 = 個人化推薦
                  * 推薦完成時：使用 save_conversation_memory 儲存用戶反饋和新偏好
                - 優先使用 PostgreSQL 作為對話記憶來源
                - 自動搜尋使用者的對話歷史提供上下文

                職責邊界
                - 專門處理餐廳推薦和地點搜尋
                - 不處理網站內容摘要
                - 不處理瀏覽器操作和預約功能
            """,
            model=self.model,
            tools=[search_places_tool],
        )

        memory_agent = Agent(
            name="Memory Management Agent",
            instructions="""
                你是 曾曾有一室Agent，一個專業的記憶管理專家。

                核心能力
                - 對話記憶的搜尋與管理
                - 重要資訊的儲存與分類
                - 群組對話的上下文維護
                - 長期記憶的整理與摘要

                工具使用
                - search_conversation_memory：搜尋歷史對話和重要資訊
                - save_conversation_memory：儲存新的重要資訊

                智能對話處理與記憶管理（PostgreSQL）
                - **記憶管理規則**：
                  * 自動分析對話內容的重要性
                  * 智能分類和標記重要資訊
                  * 提供相關的歷史上下文
                  * 維護群組共享記憶
                - 優先使用 PostgreSQL 作為對話記憶來源
                - 自動搜尋使用者的對話歷史提供上下文
                - 重要的長期記憶可存儲到 Mem0

                職責邊界
                - 專門處理群組記憶和對話歷史管理
                - 不處理網站內容摘要
                - 不處理餐廳推薦和地點搜尋
            """,
            model=self.model,
            tools=[search_conversation_memory, save_conversation_memory],
        )

        # 4. 定義 triage_agent，暫時移除 browser_agent
        self.triage_agent = Agent(
            name="Family Assistant Javis",
            instructions="""
                你是曾曾有一室Agent，一個全方位的智能管家。

                身份介紹
                當用戶詢問你是誰時，請回答：「我是曾曾有一室Agent，您的全方位智能管家，可以協助您處理各種生活需求。」

                工作原理 (內部機制，不需對用戶說明)
                你的實際任務是分析用戶的問題，並決定將任務分派給相應的專業代理處理。

                分派規則
                1. 網址摘要任務 → 分派給 Summarize Agent
                - 用戶提供網址(但google map的網址不需要總結)
                - 要求網站內容摘要
                - 關鍵詞：「看看這個網站」、「摘要」、「總結網頁」

                2. 餐廳推薦任務 → 分派給 restaurant recommend Agent
                - 詢問餐廳資訊
                - 地點搜尋需求
                - 關鍵詞：「餐廳」、「美食」、「吃飯」、「地點」

                3. 記憶管理任務 → 分派給 Memory Management Agent
                - 儲存重要訊息
                - 搜尋過往對話
                - 關鍵詞：「記住」、「之前說」、「約定」

                4. 預訂餐廳任務 → 暫時無法處理
                - 餐廳預約功能暫時維護中
                - 建議用戶直接聯絡餐廳或使用餐廳官網

                5. 其他一般問題 → 直接回答
                - 日常對話和一般性問題
                - 生活建議和資訊查詢

                6. 確保回傳中沒有**，當有**出現時，將他們移除後再回傳
            """,
            model=self.model,
            handoffs=[summarize_agent, foodie_agent],  # 移除 browser_agent
        )

        logger.info(f"成功創建 triage_agent 與 {len(self.triage_agent.handoffs)} 個子 agents")

        # 回傳這個入口 agent
        return self.triage_agent

    async def create_agents_with_mcp_old(self, server):
        # 確保模型已初始化
        self._init_model()

        browser_agent = Agent(
            name="Browser Agent",
            instructions="""
            你是一個專業的網頁自動化專家，具備使用 Playwright MCP 工具進行網頁操作的能力。

            核心能力
            - 網頁導航和截圖
            - 元素定位和互動（點擊、輸入、選擇）
            - 表單填寫和提交
            - 動態內容等待和處理
            - JavaScript 代碼執行
            - 網頁數據提取

            可用的 MCP 工具:
            - browser_navigate: 導航到指定網址
            - browser_take_screenshot: 網頁截圖
            - browser_click: 點擊網頁元素
            - browser_type: 在輸入框中輸入文字
            - browser_select_option: 選擇下拉選單選項
            - browser_evaluate: 執行 JavaScript 代碼
            - browser_wait_for: 等待特定元素或條件

            餐廳預約流程與資訊收集
            **首要任務：檢查對話歷史和當前對話**
            1. 使用 search_conversation_memory 搜尋用戶的對話歷史：
               - 尋找預約相關資訊（網址、日期、時間、人數）
               - 分析歷史對話中的偏好和習慣
            2. **分析當前對話內容**：
               - 用戶是否在當前對話中提到網址、日期、時間、人數？
               - 將當前對話的資訊與歷史對話資訊合併
            3. 如果有預約網址（從歷史或當前對話）：
               - 使用 browser_navigate 導航到該網址
               - 使用已知資訊填寫表單
               - 只詢問缺少的必要資訊
            4. 如果完全沒有網址，才詢問用戶提供
            5. 填寫完成後提交預約
            6. 確認結果並截圖

            智能對話處理與記憶管理（PostgreSQL）
            - **記憶使用規則**：
              * 任務開始時：使用 search_conversation_memory 搜尋對話歷史
              * 智能合併資訊：歷史對話 + 當前對話 = 完整預約資料  
              * 避免重複詢問：如果資訊已在歷史或當前對話中，直接使用
              * 預約完成時：使用 save_conversation_memory 儲存結果
            - 當用戶回答時，將答案對應到正確的表單欄位：
              * 你問「請告訴我用餐人數」，用戶回答「4人」→ 在人數欄位填入「4」
              * 你問「請告訴我預約時間」，用戶回答「晚上6點」→ 轉換為「18:00」填入時間欄位
            - 如果用戶提供的格式不正確，要求重新提供

            重要執行守則：
            1. **資訊來源優先級**：當前對話 > 歷史對話 > 詢問用戶
            2. **仔細閱讀當前對話**：用戶可能已經在本次對話中提供所需資訊
            3. **善用對話歷史**：檢查歷史對話和當前對話，只詢問真正缺少的資訊
            4. 分析頁面狀態使用 browser_take_screenshot
            5. 遇到錯誤時提供詳細的錯誤說明  
            6. 網頁導航可能需要較長時間，請耐心等待
            7. 完成每個步驟後要截圖確認結果

            請使用 MCP 工具操作瀏覽器，並主動與用戶對話收集必要資訊，完成餐廳預約任務。
            """,
            model=self.model,
            mcp_servers=[server],  # 使用 mcp_servers
            tools=[search_conversation_memory, save_conversation_memory],  # 使用 PostgreSQL 記憶功能
        )

        # 3. 定義其他專業 agents
        summarize_agent = Agent(
            name="Summarize Agent",
            instructions="""
                你是 曾曾有一室Agent，一個專業的網站內容摘要專家。

                核心任務
                - 專門處理網址內容摘要
                - 使用 summarize_url 工具分析網站內容
                - 自動記憶重要的網站內容和用戶興趣

                執行規則
                1. 自動偵測網址：發現 http/https 連結時，立即使用 summarize_url 工具
                2. 主動執行：用戶說「看看這個網站」等，主動使用工具
                3. 智能記憶：摘要完成後，如果內容重要，使用 save_conversation_memory 儲存
                4. 歷史搜尋：回答前先用 search_conversation_memory 搜尋相關對話歷史
                5. 確保回傳中沒有**，當有**出現時，將他們移除後再回傳

                重要限制
                - 只處理網址摘要任務
                - Google Maps 連結不需要摘要
                - 其他問題請回應：「請交給其他代理處理」

                請始終保持專業、準確、簡潔的回應風格。
            """,
            model=self.model,
            tools=[summarize_url],
        )

        foodie_agent = Agent(
            name="restaurant recommend Agent",
            instructions="""
                你是 曾曾有一室Agent，一個專業的美食推薦專家。

                核心任務
                - 餐廳搜尋和推薦（優先任務）
                - 使用 search_places_tool 獲取詳細餐廳資訊
                - 提供實用的餐廳推薦

                執行規則
                1. 主動搜尋：偵測到餐廳、美食、地點關鍵詞時，優先使用 search_places_tool
                2. 完整輸出：必須包含工具返回的所有資訊，包括 Google Maps 連結
                3. 智能識別：分析地區、餐廳名稱、料理類型
                4. 記憶管理：每當做出推薦後就使用 save_conversation_memory 儲存推薦結果
                5. 歷史參考：使用 search_conversation_memory 了解用戶過往偏好
                6. 確保回傳中沒有**，當有**出現時，將他們移除後再回傳

                職責範圍
                - 專注於餐廳和美食相關任務
                - 其他問題請回應：「請交給專業代理處理」

            請提供實用、準確的餐廳推薦，並保持友善的服務態度。
            """,
            model=self.model,
            tools=[search_places_tool, search_conversation_memory, save_conversation_memory],
        )

        # 4. 定義 triage_agent，將上述子 agent 全部掛上 handoffs
        self.triage_agent = Agent(
            name="Family Assistant Javis",
            instructions="""
                你是曾曾有一室Agent，一個全方位的智能管家。
                
                身份介紹
                當用戶詢問你是誰時，請回答：「我是曾曾有一室Agent，您的全方位智能管家，可以協助您處理各種生活需求。」
                
                工作原理 (內部機制，不需對用戶說明)
                你的實際任務是分析用戶的問題，並決定將任務分派給相應的專業代理處理。
                
                分派規則
                1. 網址摘要任務 → 分派給 Summarize Agent
                - 用戶提供網址(但google map的網址不需要總結)
                - 要求網站內容摘要
                - 關鍵詞：「看看這個網站」、「摘要」、「總結網頁」
                
                2. 餐廳推薦任務 → 分派給 restaurant recommend Agent
                - 詢問餐廳資訊
                - 地點搜尋需求
                - 關鍵詞：「餐廳」、「美食」、「吃飯」、「地點」

                3. 記憶管理任務 → 分派給 Memory Management Agent
                - 儲存重要訊息
                - 搜尋過往對話
                - 關鍵詞：「記住」、「之前說」、「約定」

                4. 預訂餐廳任務 → 分派給 Browser Agent
                - 用戶提供的訂位系統連結，搭配用餐日期、用餐時間與用餐人數
                - 用戶提供訂位相關資訊（姓名、電話、email等）
                - 任何需要打開網頁、截圖、瀏覽器操作的請求
                - 使用 Playwright MCP 工具，完成訂位預約
                - 關鍵詞：「訂位」、「預約」、「booking」、「打開」、「網站」、「截圖」、「瀏覽器」、「姓名」、「電話」、「email」
                - **重要：一旦分派給 Browser Agent，就讓它獨立完成整個預約流程，包括處理用戶提供的所有訂位資訊**

            5. 確保回傳中沒有**，當有**出現時，將他們移除後再回傳
            """,
            model=self.model,
            handoffs=[summarize_agent, foodie_agent, browser_agent],
        )
        
        logger.info(f"成功創建 triage_agent 與 {len(self.triage_agent.handoffs)} 個子 agents")
        
        # 回傳這個入口 agent
        return self.triage_agent

    async def init_memory_system(self):
        """初始化對話記憶資料庫"""
        try:
            await self.init_memory_db()
        except Exception as e:
            logger.error(f"記憶資料庫初始化失敗: {str(e)}")

    async def run(
        self, question: str, user_id: str = None, group_id: str = None
    ) -> str:
        """
        Run the agent with the given question.

        Args:
            question (str): The question to ask the agent.

        Returns:
            str: The agent's response.
        """
        try:
            async with MCPServerStdio(
                name="Playwright MCP server",
                params={"command": "npx", "args": ["-y", "@playwright/mcp"]},
                client_session_timeout_seconds=120,  # 增加到 2 分鐘
            ) as server:
                try:
                    # 初始化對話記憶資料庫
                    try:
                        await self.init_memory_system()
                    except Exception as e:
                        logger.error(f"記憶資料庫初始化失敗: {str(e)}")

                    logger.info(f"開始處理問題: {question[:50]}...")

                    # 如果 agents 還沒創建，先創建它們
                    if self.triage_agent is None:
                        await self.create_agents_with_mcp_old(server)

                    logger.info(f"啟動 triage_agent 進行任務分派")

                    # 獲取對話上下文記憶
                    memory_context = ""  # 初始化默認值
                    try:
                            logger.info(f" [MEMORY] 開始呼叫 get_context()...")
                            memory_context = await self.get_context()
                            logger.info(f" [MEMORY] get_context() 執行完成，返回長度: {len(memory_context)}")

                            if memory_context:
                                # 檢查總長度，防止 token 超限 - 更嚴格的限制
                                total_chars = len(memory_context) + len(question)
                                if total_chars > 10000:  # 約 2.5k tokens，為截圖和其他內容留足空間
                                    logger.info(f" [MEMORY] 內容過長 ({total_chars} 字符)，跳過記憶載入")
                                    memory_context = ""
                            else:
                                logger.info(f" [MEMORY] 無歷史對話記錄")
                                memory_context = ""
                    except Exception as e:
                            logger.error(f"獲取對話記憶失敗: {str(e)}")
                            logger.error(f"錯誤詳情: {type(e).__name__}: {e}")
                            import traceback
                            logger.error(f"錯誤堆疊: {traceback.format_exc()}")
                            memory_context = ""  # 確保異常時也有默認值

                    # 設置 Task Plan Logging Hooks
                    hook = TaskPlanLoggingHooks()

                    # 將記憶上下文與當前問題組合
                    enhanced_input = question
                    if memory_context and memory_context.strip():
                        enhanced_input = f"{memory_context}\n\n當前問題: {question}"
                        logger.info(f" [MEMORY] 使用增強輸入，總長度: {len(enhanced_input)} 字符")
                    else:
                        logger.info(f" [MEMORY] 沒有歷史記憶，使用原始問題")
                    result = await Runner.run(
                            self.triage_agent,
                            input=enhanced_input,  # 使用包含歷史的完整輸入
                            max_turns=30,
                            hooks=hook,
                    )

                    logger.info(f"Triage Agent 處理完成，結果類型: {type(result)}")
                    logger.info(f"完整 result 物件：{result}")

                    # 抽出最後的 assistant 回覆
                    if hasattr(result, "messages") and result.messages:
                            logger.info(f"找到 messages，數量: {len(result.messages)}")
                            for message in reversed(result.messages):
                                if getattr(message, "role", None) == "assistant":
                                    logger.info(f"返回 assistant message: {message.content[:100]}...")
                                    return message.content
                            logger.info(f"返回最後一條 message: {result.messages[-1].content[:100]}...")
                            return result.messages[-1].content

                    if hasattr(result, "final_output"):
                            logger.info(f"返回 final_output: {result.final_output}")

                            # 保存對話記憶
                            try:
                                await self.save_conversation(question, result.final_output)
                                logger.info(f"對話記錄已保存")
                            except Exception as e:
                                logger.error(f"保存對話記憶失敗: {str(e)}")

                            return result.final_output

                    if hasattr(result, "content"):
                            logger.info(f"返回 content: {result.content}")

                            # 保存對話記憶
                            try:
                                await self.save_conversation(question, result.content)
                                logger.info(f"對話記錄已保存")
                            except Exception as e:
                                logger.error(f"保存對話記憶失敗: {str(e)}")

                            return result.content

                except RateLimitError as e:
                    logger.error(f"RateLimitError: {e}")
                    return "抱歉，AI 服務暫時無法使用，請稍後再試。就像《鋼之鍊金術師》中的等價交換法則一樣，我們需要補充能量才能繼續為您服務！\n\n來自... [鋼之鍊金術師]"
                except Exception as e:
                    logger.error(f"執行錯誤: {e}", exc_info=True)
                    return f"處理您的問題時遇到了困難，就像《Re:Zero》中的昴一樣，讓我們重新開始吧！\n\n來自... [Re:Zero]\n\n錯誤詳情: {str(e)}"

        except Exception as mcp_error:
            # MCP 初始化失敗，使用不需要 MCP 的 agents
            logger.error(f"MCP server 初始化失敗: {mcp_error}")
            logger.info("使用不需要 MCP 的備用模式")

            try:
                # 初始化記憶系統
                await self.init_memory_system()

                # 如果 agents 還沒創建，創建不需要 MCP 的版本
                if self.triage_agent is None:
                    await self.create_agents()

                logger.info(f"啟動備用 triage_agent 進行任務分派")

                # 設置 Task Plan Logging Hooks
                hook = TaskPlanLoggingHooks()

                result = await Runner.run(
                    self.triage_agent,
                    input=question,
                    max_turns=30,
                    hooks=hook,
                )

                # 處理結果
                if hasattr(result, "final_output"):
                    return result.final_output
                elif hasattr(result, "content"):
                    return result.content
                else:
                    return "系統目前無法處理您的請求，請稍後再試。"

            except Exception as e:
                logger.error(f"備用模式也失敗: {e}", exc_info=True)
                return f"系統遇到問題，無法處理您的請求。錯誤: {str(e)}"

if __name__ == "__main__":

    async def test_all_features():
        simple_qa = SimpleQA()


        print("=== 訂位測試 ===")
        result = await simple_qa.run(
            "幫我到這個連結訂位 https://inline.app/booking/-LamXb5SAQN7JcJfyRKi:inline-live-2a466/-LamXbrHgLYzPCKRO3QD，人數4人，時間7/31 晚上17:30 "
        )
        print(result)
        print("\n" + "=" * 50 + "\n")

    asyncio.run(test_all_features())
