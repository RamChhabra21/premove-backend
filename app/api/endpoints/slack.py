from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import httpx
import os
from sqlalchemy.orm import Session
from app.core.deps import get_db
from app.core.auth import get_current_db_user
from app.models.users import User
from app.models.integrations import UserIntegration
from app.core.logging_config import logger

router = APIRouter()

class SlackExchangeRequest(BaseModel):
    code: str
    fcm_token: str
    code_verifier: str

@router.get("/callback")
async def slack_callback(code: str = None, state: str = None, error: str = None):
    """
    Slack redirects here after user authorizes.
    """
    if error:
        return {"status": "denied", "error": error}
    return {"status": "ok"}

@router.post("/exchange")
async def slack_exchange(
    body: SlackExchangeRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Exchanges code for Slack token and stores it in UserIntegration.
    """
    user_id = current_user.id # This is now a proper UUID
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": os.getenv("SLACK_CLIENT_ID"),
                    "client_secret": os.getenv("SLACK_CLIENT_SECRET"),
                    "code": body.code,
                    "redirect_uri": os.getenv("SLACK_REDIRECT_URI"),
                    "code_verifier": body.code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.TimeoutException:
        logger.error("Slack oauth.v2.access request timed out")
        raise HTTPException(status_code=504, detail="Request to Slack timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack oauth.v2.access network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Slack")

    data = response.json()
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error", "slack_exchange_failed"))

    slack_user_id = data["authed_user"]["id"]
    slack_token = data["authed_user"]["access_token"]

    logger.debug(f"Received FCM token from app: '{body.fcm_token}'")

    # Save or update the integration
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()

    if not integration:
        integration = UserIntegration(
            user_id=user_id,
            provider="slack",
            external_id=slack_user_id,
            credentials={"access_token": slack_token},
            metadata_json={"fcm_token": body.fcm_token}
        )
        db.add(integration)
    else:
        integration.external_id = slack_user_id
        integration.credentials = {"access_token": slack_token}
        integration.metadata_json = {"fcm_token": body.fcm_token}
    
    try:
        db.commit()
        logger.info(f"Slack connection saved for user {user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save slack connection: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    return {"status": "ok", "slack_user_id": slack_user_id}

@router.post("/events")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    """
    Handles Slack Event Subscriptions.
    """
    # body = await request.body()
    # print("Req : ", body)
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Slack event JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # 1. URL Verification (Slack Setup)
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    
    # 2. Event Callback (Actual events like messages)
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        slack_user_id = event.get("user")
        
        # Find the connection to get the FCM token
        integration = db.query(UserIntegration).filter_by(
            provider="slack",
            external_id=slack_user_id
        ).first()
        
        if integration and integration.metadata_json:
            fcm_token = integration.metadata_json.get("fcm_token")
            if fcm_token:
                from app.utils.fcm import send_fcm_notification
                import json
                logger.info(f"Triggering FCM push for Slack user {slack_user_id}")
                
                send_fcm_notification(
                    token=fcm_token,
                    title="Slack Activity",
                    body=event.get("text", "New Slack event received!"),
                    data={
                        "type": "slack_event",
                        "nodeType": "SLACK_MESSAGE_RECEIVED",
                        "slack_user_id": str(slack_user_id or ""),
                        "event_type": str(event.get("type") or ""),
                        "text": str(event.get("text") or ""),
                        "channel": str(event.get("channel") or ""),
                        "ts": str(event.get("ts") or ""),
                        "channel_type": str(event.get("channel_type") or ""),
                        "client_msg_id": str(event.get("client_msg_id") or ""),
                        "team_id": str(data.get("team_id") or ""),
                        "event_id": str(data.get("event_id") or ""),
                        "event_time": str(data.get("event_time") or ""),
                        "event_json": json.dumps(event)
                    }
                )
    return {"status": "ok"}


def get_slack_token(user_id, db: Session) -> str:
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()
    if not integration or not integration.credentials or "access_token" not in integration.credentials:
        raise HTTPException(
            status_code=400,
            detail="Slack integration not found or missing credentials. Please connect Slack first."
        )
    return integration.credentials["access_token"]


@router.get("/me")
async def get_slack_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fetch the Slack profile of the current authenticated user.
    """
    integration = db.query(UserIntegration).filter_by(
        user_id=current_user.id,
        provider="slack"
    ).first()
    if not integration or not integration.external_id:
        raise HTTPException(
            status_code=400,
            detail="Slack integration not connected."
        )
    return await get_slack_user_info(slack_user_id=integration.external_id, db=db, current_user=current_user)


@router.get("/user")
async def get_slack_user_info(
    slack_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fetch profile details of a specific Slack user.
    """
    token = get_slack_token(current_user.id, db)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://slack.com/api/users.info",
                params={"user": slack_user_id},
                headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.TimeoutException:
        logger.error("Slack users.info request timed out")
        raise HTTPException(status_code=504, detail="Request to Slack timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack users.info network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Slack")
        
    data = response.json()
    if not data.get("ok"):
        error_msg = data.get("error", "unknown_error")
        logger.error(f"Slack users.info API failed: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )
        
    return data.get("user")


@router.get("/channel")
async def get_slack_channel_info(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fetch metadata of a specific Slack channel or conversation.
    """
    token = get_slack_token(current_user.id, db)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://slack.com/api/conversations.info",
                params={"channel": channel_id},
                headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.TimeoutException:
        logger.error("Slack conversations.info request timed out")
        raise HTTPException(status_code=504, detail="Request to Slack timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack conversations.info network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Slack")
        
    data = response.json()
    if not data.get("ok"):
        error_msg = data.get("error", "unknown_error")
        logger.error(f"Slack conversations.info API failed: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )
        
    return data.get("channel")


@router.get("/conversations")
async def list_slack_conversations(
    types: str = "public_channel,private_channel,im,mpim",
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    List Slack conversations (channels, DMs, group DMs) that the authenticated user is in.
    """
    token = get_slack_token(current_user.id, db)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://slack.com/api/conversations.list",
                params={
                    "types": types,
                    "limit": limit,
                    "exclude_members": "true"
                },
                headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.TimeoutException:
        logger.error("Slack conversations.list request timed out")
        raise HTTPException(status_code=504, detail="Request to Slack timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack conversations.list network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Slack")
        
    data = response.json()
    if not data.get("ok"):
        error_msg = data.get("error", "unknown_error")
        logger.error(f"Slack conversations.list API failed: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )
        
    return data.get("channels", [])


@router.get("/users")
async def list_slack_users(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    List all users/members of the connected Slack workspace.
    """
    token = get_slack_token(current_user.id, db)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://slack.com/api/users.list",
                params={"limit": limit},
                headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.TimeoutException:
        logger.error("Slack users.list request timed out")
        raise HTTPException(status_code=504, detail="Request to Slack timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack users.list network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Slack")
        
    data = response.json()
    if not data.get("ok"):
        error_msg = data.get("error", "unknown_error")
        logger.error(f"Slack users.list API failed: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )
        
    return data.get("members", [])