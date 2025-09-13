import asyncio
from agents import (
    Agent,
    Runner,
    RunConfig,
    set_tracing_disabled,
    OpenAIChatCompletionsModel,
)
import logging
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



class SimpleQA:
    def __init__(self):
        self.gemini_model = OpenAIChatCompletionsModel(
            model="gemini-2.5-pro",
            openai_client=gemini_client,
        )

        # self.local_model = OpenAIChatCompletionsModel(
        #     model="gpt-oss:20b",
        #     openai_client=local_client,
        # )

        # 不在 __init__ 中初始化 agents，因為需要 async context
        self.triage_agent = None
    
    async def create_agents_with_mcp(self, server):
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
            model=self.gemini_model,
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
            model=self.gemini_model,
            tools=[summarize_url, search_conversation_memory, save_conversation_memory],
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
            model=self.gemini_model,
            tools=[search_places_tool, search_conversation_memory, save_conversation_memory],
        )

        memory_agent = Agent(
            name="Memory Management Agent",
            instructions="""
                你是一個專業的記憶管理專家代理，名字叫做 曾曾有一室Agent

                核心職責
                你的專長是協助用戶管理群組對話記憶，使用記憶工具進行記憶操作。

                工具使用
                - 使用 search_conversation_memory 搜尋 PostgreSQL 中的對話歷史
                - 使用 save_conversation_memory 儲存對話到 PostgreSQL
                - 使用 add_to_memory 儲存重要資訊到 Mem0（備用）
                - 使用 search_memory 搜尋 Mem0 記憶（備用）

                記憶策略（PostgreSQL 優先）
                - 優先使用 PostgreSQL 作為對話記憶來源
                - 自動搜尋使用者的對話歷史提供上下文
                - 重要的長期記憶可存儲到 Mem0

                職責邊界
                - 專門處理群組記憶和對話歷史管理
                - 不處理網站內容摘要
                - 不處理餐廳推薦和地點搜尋
            """,
            model=self.gemini_model,
            tools=[search_conversation_memory, save_conversation_memory],
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
            model=self.gemini_model,
            handoffs=[summarize_agent, foodie_agent, memory_agent, browser_agent],
            tools=[search_conversation_memory, save_conversation_memory],
        )
        
        print(f"成功創建 triage_agent 與 {len(self.triage_agent.handoffs)} 個子 agents")
        
        # 回傳這個入口 agent
        return self.triage_agent

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
        async with MCPServerStdio(
            name="Playwright MCP server",
            params={"command": "npx", "args": ["-y", "@playwright/mcp"]},
            client_session_timeout_seconds=30,
        ) as server:
            try:
                print(f"開始處理問題: {question[:50]}...")
                logger.info(f"開始處理問題: {question[:50]}...")
                
                # 如果 agents 還沒創建，先創建它們
                if self.triage_agent is None:
                    print(f"首次運行，創建 agents...")
                    await self.create_agents_with_mcp(server)
                
                print(f"啟動 triage_agent 進行任務分派")
                logger.info(f"啟動 triage_agent 進行任務分派")

                # 1. 搜尋對話歷史上下文
                print(f"搜尋對話歷史上下文: user_id={user_id}")
                conversation_context = ""
                if user_id:
                    try:
                        conversation_context = await search_context(user_id)
                        print(f"找到上下文長度: {len(conversation_context)}")
                    except Exception as e:
                        print(f"搜尋上下文失敗: {e}")
                        logger.error(f"搜尋上下文失敗: {e}")

                # 2. 創建 PostgreSQL Context（完全替換 Mem0Context）
                print(f"創建 PostgreSQL Context: user_id={user_id}, group_id={group_id}")
                context = PostgreSQLContext(user_id=user_id, group_id=group_id)

                # 3. 將對話歷史加入到輸入中
                enhanced_question = question
                if conversation_context:
                    enhanced_question = f"{conversation_context}\n\n新問題: {question}"

                print(f"開始執行 Runner.run...")
                result = await Runner.run(
                    self.triage_agent,
                    input=enhanced_question,  # 使用包含歷史的問題
                    context=context,  # 使用正確的 Context 物件
                    max_turns=30,
                )

                
                logger.info(f"最後調用：{result.last_agent.name}")
                logger.info(f"任務完成，最終輸出: {result.final_output[:100]}...")
                
                # 4. 儲存對話記錄到 PostgreSQL
                if user_id and result.final_output:
                    try:
                        success = await update_context(
                            user_id=user_id,
                            group_id=group_id,
                            user_input=question,  # 儲存原始問題，不包含上下文
                            ai_response=result.final_output
                        )
                        print(f"對話記錄儲存結果: {success}")
                    except Exception as e:
                        print(f"儲存對話記錄失敗: {e}")
                        logger.error(f"儲存對話記錄失敗: {e}")
                
                return result.final_output

            except RateLimitError as e:
                print(f"遇到 RateLimitError: {e}")
                logger.error(f"RateLimitError: {e}")
                return "抱歉，AI 服務暫時無法使用，請稍後再試。就像《鋼之鍊金術師》中的等價交換法則一樣，我們需要補充能量才能繼續為您服務！\n\n來自... [鋼之鍊金術師]"
            except Exception as e:
                print(f"執行錯誤: {e}")
                print(f"錯誤類型: {type(e)}")
                logger.error(f"執行錯誤: {e}", exc_info=True)
                return f"處理您的問題時遇到了困難，就像《Re:Zero》中的昴一樣，讓我們重新開始吧！\n\n來自... [Re:Zero]\n\n錯誤詳情: {str(e)}"

    async def run_streaming(self, question: str, user_id: str = None, group_id: str = None
    ) -> str:
        """
        Run the agent with streaming response.

        Args:
            question (str): The question to ask the agent.

        Yields:
            str: Partial responses as they are generated.
        """

        # 創建 Mem0Context
        print(f"創建 Mem0Context: user_id={user_id}, group_id={group_id}")
        context = Mem0Context(user_id=user_id, group_id=group_id)
        try:
            result = Runner.run_streamed(
                self.triage_agent,
                input=question,
                context=context,
            )

            # 使用 stream_events 來獲取事件流
            async for event in result.stream_events():
                # 過濾出文字增量事件
                if event.type == "raw_response_event" and hasattr(event, "data"):
                    if (
                        hasattr(event.data, "type")
                        and event.data.type == "response.output_text.delta"
                    ):
                        if hasattr(event.data, "delta"):
                            yield event.data.delta

        except RateLimitError:
            yield "抱歉，AI 服務暫時無法使用，請稍後再試。就像《鋼之鍊金術師》中的等價交換法則一樣，我們需要補充能量才能繼續為您服務！\n\n來自... [鋼之鍊金術師]"
        except Exception as e:
            print(f"Streaming 錯誤詳情: {e}")
            print(f"錯誤類型: {type(e)}")
            logger.error(f"Streaming 錯誤詳情: {e}", exc_info=True)
            yield f"處理您的問題時遇到了困難，就像《Re:Zero》中的昴一樣，讓我們重新開始吧！\n\n來自... [Re:Zero]"


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
