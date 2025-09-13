import logging
import traceback
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from linebot.v3.messaging import (
    AsyncMessagingApi,
    TextMessage,
    Configuration,
    PushMessageRequest,
)
from linebot.v3.exceptions import InvalidSignatureError
from ..services.line.client import LineClient
from ..services.line.config import line_settings

router = APIRouter(prefix="/line", tags=["line"])
line_client = LineClient()
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle LINE webhook events"""
    logger.info("====== LINE Webhook Request Received ======")

    # 記錄標頭資訊，可能有助於調試
    headers = {k: v for k, v in request.headers.items()}
    logger.info(f"Headers: {headers}")

    # Get original request content
    body_bytes = await request.body()
    body = body_bytes.decode()
    signature = request.headers.get("X-Line-Signature", "")

    # log the request body
    logger.info(f"Request body length: {len(body)}")
    if len(body) < 1000:  # 只記錄短請求的完整內容
        logger.info(f"Request body: {body}")
    else:
        logger.info(f"Request body (truncated): {body[:500]}...")

    logger.info(f"X-Line-Signature: {signature}")

    try:
        # Process LINE events
        logger.info("Processing LINE webhook events")

        background_tasks.add_task(line_client.process_request, signature, body)
        logger.info("LINE webhook processing started in background")
        return {"status": "received"}

    except InvalidSignatureError:
        logger.error("Invalid LINE signature")
        return {"status": "error", "message": "Invalid signature"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": "Processing failed"}


@router.post("/push")
async def push_message(message: str, group_id: str | None = None):
    """Push a message to a LINE group"""
    logger.info(f"Push message request: {message}")

    try:
        # 獲取允許的群組列表
        allowed_groups = line_settings.allowed_groups

        # 如果沒有指定group_id，使用第一個允許的群組
        if not group_id:
            if not allowed_groups:
                raise HTTPException(
                    status_code=400,
                    detail="No allowed groups configured. Please set ALLOWED_GROUP_IDS in environment variables.",
                )
            group_id = allowed_groups[0]
            logger.info(f"Using default group: {group_id}")

        # 檢查群組是否在允許列表中
        if allowed_groups and group_id not in allowed_groups:
            raise HTTPException(
                status_code=403,
                detail=f"Group {group_id} is not in allowed groups list: {allowed_groups}",
            )

        # Create configuration
        logger.info("Creating LINE API configuration")
        configuration = Configuration(access_token=line_settings.LINE_ACCESS_TOKEN)
        async_api = AsyncMessagingApi(configuration)

        logger.info(f"Sending message to group: {group_id}")

        # Create push message request
        request = PushMessageRequest(
            to=group_id,
            messages=[TextMessage(text=message)],
            notificationDisabled=None,
            customAggregationUnits=None,
        )

        # Send push message
        logger.info("Sending push message...")
        await async_api.push_message(request)
        logger.info("Push message sent successfully")

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error sending push message: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error sending push message: {str(e)}"
        )
