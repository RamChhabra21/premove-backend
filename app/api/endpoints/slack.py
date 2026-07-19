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
from app.redis_client import redis_client

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
    refresh_token = data["authed_user"].get("refresh_token")
    expires_in = data["authed_user"].get("expires_in")

    logger.info(f"Received Slack OAuth code exchange request for user {user_id}. FCM token starts with: '{body.fcm_token[:8]}...'")

    # Save or update the integration
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()

    import time
    existing_creds = integration.credentials or {} if integration else {}
    slack_credentials = {
        "access_token": slack_token,
    }
    if refresh_token:
        slack_credentials["refresh_token"] = refresh_token
    elif "refresh_token" in existing_creds:
        slack_credentials["refresh_token"] = existing_creds["refresh_token"]

    if expires_in:
        slack_credentials["expires_at"] = time.time() + expires_in

    if not integration:
        logger.info(f"Creating new slack integration for user {user_id} with slack_user_id {slack_user_id}")
        integration = UserIntegration(
            user_id=user_id,
            provider="slack",
            external_id=slack_user_id,
            credentials=slack_credentials,
            metadata_json={"fcm_token": body.fcm_token}
        )
        db.add(integration)
    else:
        logger.info(f"Updating existing slack integration for user {user_id} with slack_user_id {slack_user_id}")
        integration.external_id = slack_user_id
        integration.credentials = slack_credentials
        integration.metadata_json = {"fcm_token": body.fcm_token}
    
    try:
        db.commit()
        logger.info(f"Slack connection saved successfully for user {user_id} with slack_user_id {slack_user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save slack connection for user {user_id}: {e}")
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
        logger.info(f"Received Slack webhook. Event type: {data.get('type')}, event_id: {data.get('event_id')}")
    except Exception as e:
        logger.error(f"Failed to parse Slack event JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # 1. URL Verification (Slack Setup)
    if data.get("type") == "url_verification":
        challenge = data.get("challenge")
        logger.info("Slack url_verification event received. Returning challenge.")
        return {"challenge": challenge}
    
    # 2. Event Callback (Actual events like messages)
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        slack_user_id = event.get("user")
        event_type = event.get("type")
        event_id = data.get("event_id")

        logger.info(f"Processing Slack event_callback: event_type={event_type}, event_id={event_id}, user={slack_user_id}")
        logger.debug(f"Slack event details: {event}")

        # --- Idempotency check via Redis ---
        if event_id:
            redis_key = f"slack:processed:{event_id}"
            try:
                # SET NX = set only if key does not exist; returns True if set, None if already existed
                already_processed = not redis_client.set(redis_key, "1", nx=True, ex=1800)
                if already_processed:
                    logger.info(f"Duplicate Slack event {event_id}, skipping.")
                    return {"status": "ok"}
            except Exception as re:
                logger.error(f"Redis error during idempotency check for event {event_id}: {re}. Proceeding anyway.")
        
        if not slack_user_id:
            logger.warning(f"No user ID found in Slack event callback. Event keys: {list(event.keys())}")
            return {"status": "ok"}

        # Find the connection to get the FCM token
        logger.info(f"Searching database for UserIntegration: provider='slack', external_id='{slack_user_id}'")
        integration = db.query(UserIntegration).filter_by(
            provider="slack",
            external_id=slack_user_id
        ).first()
        
        if not integration:
            logger.warning(f"No active Slack UserIntegration found for external_id (slack_user_id): '{slack_user_id}'")
            return {"status": "ok"}
            
        if not integration.metadata_json:
            logger.warning(f"Slack integration found for user {slack_user_id}, but metadata_json is empty/None.")
            return {"status": "ok"}
            
        fcm_token = integration.metadata_json.get("fcm_token")
        if not fcm_token:
            logger.warning(f"Slack integration found for user {slack_user_id}, but no 'fcm_token' found in metadata_json. Keys: {list(integration.metadata_json.keys())}")
            return {"status": "ok"}
            
        from app.utils.fcm import send_fcm_notification
        import json
        logger.info(f"Triggering FCM push for Slack user {slack_user_id}. FCM token starts with: '{fcm_token[:8]}...'")
        
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
    else:
        logger.info(f"Received unhandled Slack event type: {data.get('type')}")
        
    return {"status": "ok"}


async def refresh_slack_token(integration: UserIntegration, db: Session) -> str:
    credentials = integration.credentials or {}
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Slack refresh token not found. Please reconnect Slack."
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": os.getenv("SLACK_CLIENT_ID"),
                    "client_secret": os.getenv("SLACK_CLIENT_SECRET"),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.TimeoutException:
        logger.error("Slack token refresh request timed out")
        raise HTTPException(status_code=504, detail="Slack token refresh timed out")
    except httpx.RequestError as e:
        logger.error(f"Slack token refresh network error: {e}")
        raise HTTPException(status_code=502, detail="Network error refreshing Slack token")

    data = response.json()
    if not data.get("ok"):
        logger.error(f"Slack token refresh failed: {data}")
        raise HTTPException(status_code=401, detail=f"Slack credentials expired: {data.get('error')}")

    authed_user = data.get("authed_user", {})
    new_access_token = authed_user.get("access_token")
    new_refresh_token = authed_user.get("refresh_token")
    expires_in = authed_user.get("expires_in")

    new_credentials = dict(credentials)
    new_credentials["access_token"] = new_access_token
    if new_refresh_token:
        new_credentials["refresh_token"] = new_refresh_token
    if expires_in:
        import time
        new_credentials["expires_at"] = time.time() + expires_in

    integration.credentials = new_credentials
    db.commit()
    return new_access_token


async def get_slack_token(user_id, db: Session) -> str:
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()
    if not integration or not integration.credentials or "access_token" not in integration.credentials:
        raise HTTPException(
            status_code=400,
            detail="Slack integration not found or missing credentials. Please connect Slack first."
        )

    credentials = integration.credentials or {}
    expires_at = credentials.get("expires_at")
    refresh_token = credentials.get("refresh_token")

    import time
    # Proactively refresh token if it's expiring in less than 5 minutes (300 seconds)
    if refresh_token and expires_at and (expires_at - time.time() < 300):
        logger.info(f"Slack access token for user {user_id} is expiring soon/expired. Refreshing...")
        try:
            return await refresh_slack_token(integration, db)
        except Exception as e:
            logger.error(f"Failed to automatically refresh Slack token for user {user_id}: {e}")
            # Fallback to current token to avoid failing immediately if Slack API is temporarily down
            return credentials["access_token"]

    return credentials["access_token"]


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
    token = await get_slack_token(current_user.id, db)
    
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
    token = await get_slack_token(current_user.id, db)
    
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
    token = await get_slack_token(current_user.id, db)
    
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
    token = await get_slack_token(current_user.id, db)
    
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