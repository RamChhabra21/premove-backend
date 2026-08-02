from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import httpx
import os
import time
import json
from typing import Optional
from sqlalchemy.orm import Session
from app.core.deps import get_db
from app.core.auth import get_current_db_user
from app.models.users import User
from app.models.integrations import UserIntegration
from app.core.logging_config import logger
from app.redis_client import redis_client

router = APIRouter()

SLACK_API_BASE = "https://slack.com/api"


class SlackExchangeRequest(BaseModel):
    code: str
    fcm_token: str
    code_verifier: str


@router.get("/callback")
async def slack_callback(code: str = None, state: str = None, error: str = None):
    """Slack redirects here after user authorizes."""
    if error:
        return {"status": "denied", "error": error}
    return {"status": "ok"}


@router.post("/exchange")
async def slack_exchange(
    body: SlackExchangeRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Exchanges code for Slack token and stores it in UserIntegration."""
    user_id = current_user.id
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SLACK_API_BASE}/oauth.v2.access",
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

    logger.info(f"Received Slack OAuth code exchange for user {user_id}. FCM token starts with: '{body.fcm_token[:8]}...'")

    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()

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
        logger.info(f"Creating new slack integration for user {user_id} (slack_user_id: {slack_user_id})")
        integration = UserIntegration(
            user_id=user_id,
            provider="slack",
            external_id=slack_user_id,
            credentials=slack_credentials,
            metadata_json={"fcm_token": body.fcm_token}
        )
        db.add(integration)
    else:
        logger.info(f"Updating existing slack integration for user {user_id} (slack_user_id: {slack_user_id})")
        integration.external_id = slack_user_id
        integration.credentials = slack_credentials
        integration.metadata_json = {"fcm_token": body.fcm_token}
    
    try:
        db.commit()
        logger.info(f"Slack connection saved successfully for user {user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save slack connection for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    return {"status": "ok", "slack_user_id": slack_user_id}


@router.post("/events")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    """Handles Slack Event Subscriptions."""
    try:
        data = await request.json()
        logger.info(f"Received Slack webhook. Event type: {data.get('type')}, event_id: {data.get('event_id')}")
    except Exception as e:
        logger.error(f"Failed to parse Slack event JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # 1. URL Verification
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    
    # 2. Event Callback
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        sender_slack_user_id = event.get("user")
        event_type = event.get("type")
        event_id = data.get("event_id")

        authed_slack_user_id = None
        authorizations = data.get("authorizations", [])
        if authorizations and isinstance(authorizations, list):
            authed_slack_user_id = authorizations[0].get("user_id")
            
        if not authed_slack_user_id:
            authed_users = data.get("authed_users", [])
            if authed_users and isinstance(authed_users, list):
                authed_slack_user_id = authed_users[0]

        if not authed_slack_user_id:
            authed_slack_user_id = sender_slack_user_id

        logger.info(f"Processing Slack event_callback: event_type={event_type}, event_id={event_id}, authed_user={authed_slack_user_id}")

        # Idempotency check via Redis
        if event_id:
            redis_key = f"slack:processed:{event_id}"
            try:
                already_processed = not redis_client.set(redis_key, "1", nx=True, ex=1800)
                if already_processed:
                    logger.info(f"Duplicate Slack event {event_id}, skipping.")
                    return {"status": "ok"}
            except Exception as re:
                logger.error(f"Redis error during idempotency check for event {event_id}: {re}")

        if not authed_slack_user_id:
            return {"status": "ok"}

        integration = db.query(UserIntegration).filter_by(
            provider="slack",
            external_id=authed_slack_user_id
        ).first()
        
        if not integration or not integration.metadata_json:
            return {"status": "ok"}
            
        fcm_token = integration.metadata_json.get("fcm_token")
        if not fcm_token:
            return {"status": "ok"}
            
        from app.utils.fcm import send_fcm_notification
        send_fcm_notification(
            token=fcm_token,
            title="Slack Activity",
            body=event.get("text", "New Slack event received!"),
            data={
                "type": "slack_event",
                "nodeType": "SLACK_MESSAGE_RECEIVED",
                "slack_user_id": str(sender_slack_user_id or ""),
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


# ------------------------------------------------------------------
# Helpers for Auth & Token Refresh Management
# ------------------------------------------------------------------

async def refresh_slack_token(integration: UserIntegration, db: Session) -> str:
    """Refreshes the Slack access_token using the stored refresh_token."""
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
                f"{SLACK_API_BASE}/oauth.v2.access",
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
        raise HTTPException(
            status_code=401,
            detail=f"Slack authentication expired: {data.get('error', 'refresh_failed')}"
        )

    authed_user = data.get("authed_user", {})
    new_access_token = data.get("access_token") or authed_user.get("access_token")
    new_refresh_token = data.get("refresh_token") or authed_user.get("refresh_token")
    expires_in = data.get("expires_in") or authed_user.get("expires_in")

    if not new_access_token:
        logger.error(f"Slack token refresh response missing access_token: {data}")
        raise HTTPException(status_code=401, detail="Slack token refresh returned empty token.")

    new_credentials = dict(credentials)
    new_credentials["access_token"] = new_access_token
    if new_refresh_token:
        new_credentials["refresh_token"] = new_refresh_token
    if expires_in:
        new_credentials["expires_at"] = time.time() + expires_in

    integration.credentials = new_credentials
    db.commit()
    return new_access_token


async def get_slack_token(user_id, db: Session, force_refresh: bool = False) -> str:
    """Returns a valid access_token, refreshing automatically if expired or force_refresh=True."""
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="slack"
    ).first()
    if not integration or not integration.credentials or "access_token" not in integration.credentials:
        raise HTTPException(
            status_code=401,
            detail="Slack integration not connected. Please connect Slack first."
        )

    credentials = integration.credentials
    expires_at = credentials.get("expires_at")
    refresh_token = credentials.get("refresh_token")

    # Proactive refresh if token expires in less than 5 minutes or if force_refresh requested
    is_expiring_soon = refresh_token and expires_at and (expires_at - time.time() < 300)
    
    if force_refresh or is_expiring_soon:
        logger.info(f"Refreshing Slack token for user {user_id} (force_refresh={force_refresh}, expiring_soon={is_expiring_soon})...")
        return await refresh_slack_token(integration, db)

    return credentials["access_token"]


async def call_slack_api(endpoint: str, user_id, db: Session, params: Optional[dict] = None) -> dict:
    """Centralized helper for Slack Web API calls with proactive & reactive token refresh."""
    token = await get_slack_token(user_id, db)

    async def _make_request(access_token: str):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{SLACK_API_BASE}/{endpoint}",
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail=f"Slack API {endpoint} request timed out")
        except httpx.RequestError as e:
            logger.error(f"Slack API {endpoint} network error: {e}")
            raise HTTPException(status_code=502, detail=f"Network error connecting to Slack API {endpoint}")

    data = await _make_request(token)

    # Reactive refresh: if Slack returned token auth error, refresh once & retry
    if not data.get("ok") and data.get("error") in ("token_expired", "invalid_auth", "token_revoked"):
        logger.warning(f"Slack API returned auth error '{data.get('error')}' for user {user_id}. Attempting reactive refresh...")
        try:
            new_token = await get_slack_token(user_id, db, force_refresh=True)
            data = await _make_request(new_token)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Reactive refresh failed for user {user_id}: {e}")
            raise HTTPException(status_code=401, detail="Slack credentials expired. Please reconnect Slack.")

    if not data.get("ok"):
        error_msg = data.get("error", "slack_api_error")
        logger.error(f"Slack API {endpoint} failed: {error_msg}")
        if error_msg in ("token_expired", "invalid_auth", "token_revoked", "account_inactive"):
            raise HTTPException(status_code=401, detail=f"Slack auth error: {error_msg}. Please reconnect.")
        raise HTTPException(status_code=400, detail=error_msg)

    return data


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/status")
async def get_slack_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Fast DB-driven status check for Slack connection."""
    integration = db.query(UserIntegration).filter_by(
        user_id=current_user.id,
        provider="slack"
    ).first()

    has_credentials = bool(
        integration and 
        integration.credentials and 
        ("access_token" in integration.credentials or "refresh_token" in integration.credentials)
    )

    return {
        "connected": has_credentials,
        "status": "connected" if has_credentials else "not_connected",
        "slack_user_id": integration.external_id if (integration and has_credentials) else None
    }


@router.delete("/disconnect")
@router.delete("/")
async def disconnect_slack(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Disconnects and removes Slack integration for the current user."""
    integration = db.query(UserIntegration).filter_by(
        user_id=current_user.id,
        provider="slack"
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration is not connected.")

    try:
        db.delete(integration)
        db.commit()
        logger.info(f"User {current_user.id} disconnected Slack integration.")
        return {"status": "ok", "message": "Successfully disconnected Slack."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to disconnect Slack for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Database error during disconnect")


@router.get("/me")
async def get_slack_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Fetch the Slack profile of the current authenticated user."""
    integration = db.query(UserIntegration).filter_by(
        user_id=current_user.id,
        provider="slack"
    ).first()
    if not integration or not integration.external_id:
        raise HTTPException(status_code=401, detail="Slack integration not connected.")
    
    return await get_slack_user_info(slack_user_id=integration.external_id, db=db, current_user=current_user)


@router.get("/user")
async def get_slack_user_info(
    slack_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Fetch profile details of a specific Slack user."""
    data = await call_slack_api("users.info", current_user.id, db, params={"user": slack_user_id})
    return data.get("user")


@router.get("/channel")
async def get_slack_channel_info(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """Fetch metadata of a specific Slack channel or conversation."""
    data = await call_slack_api("conversations.info", current_user.id, db, params={"channel": channel_id})
    return data.get("channel")


@router.get("/conversations")
async def list_slack_conversations(
    types: str = "public_channel,private_channel,im,mpim",
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """List Slack conversations user is in."""
    data = await call_slack_api(
        "conversations.list",
        current_user.id,
        db,
        params={"types": types, "limit": limit, "exclude_members": "true"}
    )
    return data.get("channels", [])


@router.get("/users")
async def list_slack_users(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """List all users/members of the connected Slack workspace."""
    data = await call_slack_api("users.list", current_user.id, db, params={"limit": limit})
    return data.get("members", [])
