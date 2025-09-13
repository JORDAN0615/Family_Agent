from tokenize import group
from .config import line_settings
import logging
import sys
import traceback
from typing import Union
from linebot.v3.webhooks import Event, MessageEvent, JoinEvent, LeaveEvent
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ShowLoadingAnimationRequest,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
)
import asyncio
from linebot.v3.webhooks.models.user_source import UserSource
from linebot.v3.webhooks.models.group_source import GroupSource
from app.agents.simple_qa import SimpleQA

logger = logging.getLogger(__name__)

# LINE Bot 的名稱，用於檢測是否被標記
BOT_NAME = "曾曾有一室Agent_DEV"

# 事件去重機制
_processed_messages = set()
MAX_PROCESSED_MESSAGES = 500


class LineClient:
    def __init__(self):
        """Initialize the LineClient with the LINE SDK settings"""
        logger.info("Initializing LINE client")
        configuration = Configuration(access_token=line_settings.LINE_ACCESS_TOKEN)
        self.async_api_client = AsyncApiClient(configuration)
        self.async_line_bot_api = AsyncMessagingApi(self.async_api_client)
        self.webhook_parser = WebhookParser(line_settings.LINE_CHANNEL_SECRET)
        logger.info("LINE client initialized successfully")

    async def send_line_message(
        self,
        event: Union[MessageEvent, JoinEvent, LeaveEvent],
        reply_message: Union[str, dict],
    ):
        """Send a message to a LINE group"""
        try:
            logger.info(f"Preparing to send message: {type(reply_message)}")
            messages = []
            if isinstance(reply_message, str):
                messages.append(TextMessage(text=reply_message))
                logger.debug(f"Created text message: {reply_message[:50]}...")
            else:
                messages.append(FlexMessage(contents=reply_message))
                logger.debug("Created flex message")

            replay_request = ReplyMessageRequest(
                replyToken=event.reply_token, messages=messages
            )

            if isinstance(event, MessageEvent):
                logger.info(
                    f"Replying to message event from: {event.source.user_id if hasattr(event.source, 'user_id') else 'unknown'}"
                )
                await self.async_line_bot_api.reply_message(replay_request)
                logger.info("Reply sent successfully")
            elif isinstance(event, JoinEvent):
                logger.info("Replying to join event")
                await self.async_line_bot_api.reply_message(replay_request)
                logger.info("Join event reply sent successfully")
            elif isinstance(event, LeaveEvent):
                logger.info("Leave event received - no reply needed")
            else:
                logger.info(f"Unsupported event type: {type(event)}")
        except Exception as e:
            logger.error(f"Error sending LINE message: {e}")
            logger.error(traceback.format_exc())

    def is_bot_mentioned(self, text: str) -> bool:
        """Check if the bot is mentioned in the message"""
        # 檢查消息中是否有 @BOT_NAME 這樣的標記
        return f"@{BOT_NAME}" in text

    def _create_message_id(self, line_event: MessageEvent) -> str:
        """Create unique message ID for deduplication"""
        if hasattr(line_event.message, "id"):
            return f"msg_{line_event.message.id}"
        else:
            # 備用方案：使用訊息內容 + 用戶 ID + 時間
            content = getattr(line_event.message, "text", "unknown")
            user_id = getattr(line_event.source, "user_id", "unknown")
            group_id = getattr(line_event.source, "group_id", "unknown")
            timestamp = getattr(line_event, "timestamp", "unknown")
            return f"backup_{hash(f'{content}_{group_id}_{user_id}_{timestamp}')}"

    async def handle_line_event(self, line_event: Event):
        """Handle a LINE event"""
        try:
            logger.info(f"Handling LINE event: {type(line_event)}")

            if isinstance(line_event, MessageEvent):
                # 檢查是否為重複訊息
                message_id = self._create_message_id(line_event)
                if message_id in _processed_messages:
                    logger.warning(
                        f"Duplicate message detected, skipping: {message_id}"
                    )
                    return

                # 記錄為已處理
                _processed_messages.add(message_id)

                # 限制記憶大小
                if len(_processed_messages) > MAX_PROCESSED_MESSAGES:
                    # 移除最舊的記錄
                    oldest = next(iter(_processed_messages))
                    _processed_messages.remove(oldest)

                logger.info(f"Processing new message: {message_id}")
                if hasattr(line_event, "source") and hasattr(line_event, "message"):
                    source_type = type(line_event.source).__name__
                    message_type = type(line_event.message).__name__
                    logger.info(
                        f"Event source type: {source_type}, message type: {message_type}"
                    )

                    # Fix the condition structure to properly check for text messages from both UserSource and GroupSource
                    if (
                        isinstance(line_event.source, UserSource)
                        or isinstance(line_event.source, GroupSource)
                    ) and hasattr(line_event.message, "text"):
                        # Get appropriate ID based on source type
                        user_id = line_event.source.user_id
                        group_id = (
                            line_event.source.group_id
                            if isinstance(line_event.source, GroupSource)
                            else None
                        )
                        # For group sources, we'll log both the group ID and user ID
                        if group_id:
                            logger.info(
                                f"Processing message from user: {user_id} in group: {group_id}"
                            )

                            # 在群組中，只有當消息提及機器人時才處理
                            if not self.is_bot_mentioned(line_event.message.text):
                                logger.info(
                                    "Bot not mentioned in group message, ignoring"
                                )
                                return
                            logger.info("Bot mentioned in group message, processing")
                        else:
                            logger.info(f"Processing message from user: {user_id}")

                        logger.info(f"Message content: {line_event.message.text}")

                        # Determine the chat ID for loading animation
                        # For GroupSource, use group_id; for UserSource, use user_id
                        chat_id = (
                            line_event.source.group_id
                            if isinstance(line_event.source, GroupSource)
                            else user_id
                        )

                        try:
                            show_loading_animation_request = (
                                ShowLoadingAnimationRequest(
                                    chatId=chat_id, loadingSeconds=40
                                )
                            )
                            await self.async_line_bot_api.show_loading_animation(
                                show_loading_animation_request
                            )
                            logger.info("Loading animation displayed")
                        except Exception as e:
                            logger.warning(f"Could not show loading animation: {e}")

                        if user_id is None:
                            # 處理 user_id 缺失的情境
                            user_id = "default_user"  # 或直接 return 錯誤訊息

                        try:
                            logger.info("Calling SimpleQA agent")
                            reply_message = await SimpleQA().run(
                                question=line_event.message.text,
                                user_id=user_id,
                                group_id=group_id,
                            )
                            logger.info("Got response from SimpleQA agent")
                            await self.send_line_message(line_event, reply_message)
                        except Exception as e:
                            logger.error(f"Error in SimpleQA processing: {e}")
                            logger.error(traceback.format_exc())
                            await self.send_line_message(
                                line_event, "抱歉，處理您的訊息時發生錯誤。"
                            )
            else:
                logger.info(f"Event type not handled: {type(line_event)}")
        except Exception as e:
            logger.error(f"Error handling LINE event: {e}")
            logger.error(traceback.format_exc())

    async def process_events(self, events: list):
        """Process LINE events"""
        logger.info(f"Processing {len(events)} LINE events")
        for i, event in enumerate(events):
            logger.info(f"Processing event {i+1}/{len(events)}: {type(event)}")
            logger.info("=" * 50)
            await self.handle_line_event(event)
        logger.info("All events processed")

    async def process_request(self, signature: str, body):
        """Verify the request signature from LINE"""
        try:
            logger.info(
                f"Processing LINE webhook request: Signature length: {len(signature) if signature else 0}"
            )
            events = self.webhook_parser.parse(body, signature)
            logger.info(f"Parsed {len(events)} events from webhook")
            await self.process_events(events)
        except Exception as e:
            logger.error(f"Error processing LINE webhook: {e}")
            logger.error(traceback.format_exc())
