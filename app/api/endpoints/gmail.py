from starlette.responses import RedirectResponse
from fastapi import APIRouter, HTTPException, Depends, Request
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


class GmailExchangeRequest(BaseModel):
    code: str
    fcm_token: str
    code_verifier: str

@router.get("/callback")
async def gmail_callback(code: str, state: str):
    # This URL triggers the Intent Filter in your Android Manifest
    redirect_url = f"premove://gmail?code={code}&state={state}"
    return RedirectResponse(url=redirect_url)

@router.post("/exchange")
async def gmail_exchange(
    body: GmailExchangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Exchanges the OAuth code for Gmail access + refresh tokens and stores them.
    """
    user_id = current_user.id

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "code": body.code,
                    "code_verifier": body.code_verifier,
                    "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.TimeoutException:
        logger.error("Google token exchange request timed out")
        raise HTTPException(status_code=504, detail="Request to Google timed out")
    except httpx.RequestError as e:
        logger.error(f"Google token exchange network error: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway connecting to Google")

    data = response.json()

    if "error" in data:
        logger.error(f"Google token exchange failed: {data}")
        raise HTTPException(status_code=400, detail=data.get("error_description", "gmail_exchange_failed"))

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    # Fetch the Gmail user's profile to get their email / Google ID
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            profile_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as e:
        logger.error(f"Google userinfo fetch failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch Google profile")

    profile = profile_response.json()
    google_user_id = profile.get("id")
    google_email = profile.get("email")

    logger.info(f"Gmail OAuth success for Google user {google_email} (user_id={user_id})")

    # Save or update the integration (same pattern as Slack)
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="gmail"
    ).first()

    if not integration:
        integration = UserIntegration(
            user_id=user_id,
            provider="gmail",
            external_id=google_user_id,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            metadata_json={
                "email": google_email,
                "fcm_token": body.fcm_token,
            },
        )
        db.add(integration)
    else:
        integration.external_id = google_user_id
        integration.credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        integration.metadata_json = {
            "email": google_email,
            "fcm_token": body.fcm_token,
        }

    try:
        db.commit()
        logger.info(f"Gmail integration saved for user {user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save Gmail integration: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        watch_response = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/watch",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            json={
                "topicName": f"projects/{os.getenv('GOOGLE_PROJECT_ID')}/topics/{os.getenv('GMAIL_PUBSUB_TOPIC')}"
            }
        )

    watch_data = watch_response.json()

    if watch_response.status_code != 200:
        logger.error(f"Failed to start Gmail watch: {watch_data}")
        raise HTTPException(
            status_code=500,
            detail="Failed to start Gmail watch",
        )
    
    metadata = integration.metadata_json or {}
    metadata["history_id"] = watch_data["historyId"]
    metadata["watch_expiration"] = watch_data["expiration"]
    integration.metadata_json = metadata

    try:
        db.commit()
        logger.info(
            f"Gmail watch started for user {user_id}. "
            f"history_id={watch_data['historyId']}, "
            f"expiration={watch_data['expiration']}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save Gmail integration: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    return {
        "status": "ok",
        "google_user_id": google_user_id,
        "email": google_email,
    }

@router.post('webhook')
async def webhook(request: Request):
    body = await request.json()
    logger.info(f"Received Gmail Pub/Sub notification: {body}")
    return {"status": "ok"}

@router.get("/me")
async def get_gmail_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Returns the connected Gmail account info for the current user.
    """
    integration = db.query(UserIntegration).filter_by(
        user_id=current_user.id,
        provider="gmail"
    ).first()

    if not integration or not integration.external_id:
        raise HTTPException(status_code=400, detail="Gmail integration not connected.")

    return {
        "google_user_id": integration.external_id,
        "email": integration.metadata_json.get("email") if integration.metadata_json else None,
        "connected": True,
    }
