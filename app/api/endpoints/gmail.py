from starlette.responses import RedirectResponse
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import httpx
import os
import base64
import json
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
from app.core.deps import get_db
from app.core.auth import get_current_db_user
from app.models.users import User
from app.models.integrations import UserIntegration
from app.core.logging_config import logger
from app.redis_client import redis_client

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
    google_user_id = None
    google_email = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Primary: Try Gmail profile API (most reliable since Gmail scope is authorized)
            profile_response = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_response.status_code == 200:
                profile_data = profile_response.json()
                google_email = profile_data.get("emailAddress")
                google_user_id = google_email
    except Exception as e:
        logger.warning(f"Failed to fetch email via Gmail profile API: {e}")

    # 2. Fallback: Try Google userinfo API
    if not google_email:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_response.status_code == 200:
                    userinfo_data = userinfo_response.json()
                    google_email = userinfo_data.get("email")
                    google_user_id = userinfo_data.get("id") or google_email
        except Exception as e:
            logger.error(f"Fallback Google userinfo fetch failed: {e}")

    if not google_email:
        raise HTTPException(
            status_code=400,
            detail="Failed to retrieve Google email address. Ensure proper scopes are authorized."
        )

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
        topic_name = (
            f"projects/{os.getenv('GOOGLE_PROJECT_ID')}/topics/"
            f"{os.getenv('GMAIL_PUBSUB_TOPIC')}"
        )

        logger.info(f"Using Gmail watch topic: {topic_name}")

        watch_response = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/watch",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            json={
                "topicName": topic_name,
            },
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
    integration.metadata_json = dict(metadata)

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

async def refresh_google_token(integration: UserIntegration, db: Session) -> str:
    credentials = integration.credentials or {}
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Google refresh token not found. Please reconnect Gmail."
        )
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    
    data = response.json()
    if response.status_code != 200 or "error" in data:
        logger.error(f"Google token refresh failed: {data}")
        raise HTTPException(status_code=401, detail="Google credentials expired")
        
    new_access_token = data.get("access_token")
    new_credentials = dict(credentials)
    new_credentials["access_token"] = new_access_token
    if "refresh_token" in data:
        new_credentials["refresh_token"] = data["refresh_token"]
        
    integration.credentials = new_credentials
    db.commit()
    return new_access_token


async def call_gmail_api_with_retry(
    db: Session,
    integration: UserIntegration,
    url: str,
    method: str = "GET",
    params: dict = None,
    json_data: dict = None,
):
    credentials = integration.credentials or {}
    access_token = credentials.get("access_token")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, params=params, json=json_data)
            elif method == "PUT":
                response = await client.put(url, headers=headers, params=params, json=json_data)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
        except httpx.RequestError as e:
            logger.error(f"Gmail API network error calling {url}: {e}")
            raise HTTPException(status_code=502, detail="Network error calling Google API")

    if response.status_code == 401:
        logger.info(f"Google access token expired for user {integration.user_id}, refreshing...")
        try:
            new_access_token = await refresh_google_token(integration, db)
        except Exception as e:
            logger.error(f"Failed to refresh Google token for user {integration.user_id}: {e}")
            raise HTTPException(status_code=401, detail="Google credentials expired")
        
        # Retry request
        headers = {"Authorization": f"Bearer {new_access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, params=params, json=json_data)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, params=params, json=json_data)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)
            except httpx.RequestError as e:
                logger.error(f"Gmail API retry network error calling {url}: {e}")
                raise HTTPException(status_code=502, detail="Network error calling Google API on retry")

    return response


async def renew_watch_if_needed(db: Session, integration: UserIntegration) -> bool:
    """
    Checks if the Gmail watch is close to expiring (less than 2 days remaining)
    and renews it if necessary.
    """
    import time
    metadata = integration.metadata_json or {}
    watch_expiration = metadata.get("watch_expiration")
    
    # If no expiration or within 2 days (172800 seconds) of expiring
    # watch_expiration is in milliseconds since epoch
    now_ms = int(time.time() * 1000)
    buffer_ms = 2 * 24 * 60 * 60 * 1000  # 2 days
    
    if not watch_expiration or (int(watch_expiration) - now_ms < buffer_ms):
        logger.info(f"Gmail watch for {metadata.get('email')} is expiring soon or missing. Renewing...")
        credentials = integration.credentials or {}
        access_token = credentials.get("access_token")
        if not access_token:
            return False
            
        topic_name = (
            f"projects/{os.getenv('GOOGLE_PROJECT_ID')}/topics/"
            f"{os.getenv('GMAIL_PUBSUB_TOPIC')}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                watch_response = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/watch",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"topicName": topic_name},
                )
                if watch_response.status_code == 200:
                    watch_data = watch_response.json()
                    metadata["history_id"] = watch_data["historyId"]
                    metadata["watch_expiration"] = watch_data["expiration"]
                    integration.metadata_json = dict(metadata)
                    db.commit()
                    logger.info(f"Successfully renewed Gmail watch for {metadata.get('email')}")
                    return True
                else:
                    logger.error(f"Failed to renew watch: {watch_response.json()}")
        except Exception as e:
            logger.error(f"Error renewing watch: {e}")
    return False


def get_gmail_integration(user_id, db: Session) -> UserIntegration:
    integration = db.query(UserIntegration).filter_by(
        user_id=user_id,
        provider="gmail"
    ).first()
    if not integration or not integration.credentials or "access_token" not in integration.credentials:
        raise HTTPException(
            status_code=400,
            detail="Gmail integration not found or missing credentials. Please connect Gmail first."
        )
    return integration


def parse_gmail_metadata(message_detail: dict):
    headers = message_detail.get("payload", {}).get("headers", [])
    
    subject = "No Subject"
    sender = "Unknown Sender"
    
    for h in headers:
        name = h.get("name", "").lower()
        if name == "subject":
            subject = h.get("value", "No Subject")
        elif name == "from":
            sender = h.get("value", "Unknown Sender")
            
    from_name = sender
    from_email = sender
    if "<" in sender and ">" in sender:
        parts = sender.split("<")
        from_name = parts[0].strip()
        from_email = parts[1].replace(">", "").strip()
        
    return {
        "message_id": message_detail.get("id"),
        "thread_id": message_detail.get("threadId"),
        "sender": from_email,
        "sender_name": from_name,
        "subject": subject,
        "snippet": message_detail.get("snippet", ""),
        "labels": message_detail.get("labelIds", []),
    }


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives Gmail Pub/Sub push notifications.
    Decodes the payload to extract the email and historyId,
    then fetches the changes and triggers an FCM push.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Gmail webhook JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    logger.info(f"Received Gmail Pub/Sub notification: {body}")
    
    if not body or "message" not in body or "data" not in body["message"]:
        logger.warning(f"Unknown Gmail webhook structure: {body}")
        return {"status": "ok"}

    # --- Idempotency check via Redis ---
    pubsub_message_id = body["message"].get("messageId")
    if pubsub_message_id:
        redis_key = f"gmail:processed:{pubsub_message_id}"
        # SET NX = set only if key does not exist; returns True if set, None if already existed
        already_processed = not redis_client.set(redis_key, "1", nx=True, ex=1800)
        if already_processed:
            logger.info(f"Duplicate Gmail Pub/Sub message {pubsub_message_id}, skipping.")
            return {"status": "ok"}
        
    try:
        encoded_data = body["message"]["data"]
        # Add padding if needed
        missing_padding = len(encoded_data) % 4
        if missing_padding:
            encoded_data += '=' * (4 - missing_padding)
        decoded_bytes = base64.b64decode(encoded_data)
        decoded_str = decoded_bytes.decode("utf-8")
        message_data = json.loads(decoded_str)
    except Exception as e:
        logger.error(f"Failed to decode Pub/Sub data: {e}")
        return {"status": "ok"}
        
    email = message_data.get("emailAddress")
    history_id = message_data.get("historyId")
    
    if not email or not history_id:
        logger.warning(f"Missing email or historyId in decoded payload: {message_data}")
        return {"status": "ok"}
        
    # Find user integration matching this email
    integration = db.query(UserIntegration).filter(
        UserIntegration.provider == "gmail",
        UserIntegration.metadata_json["email"].astext == email
    ).first()
    
    if not integration:
        logger.warning(f"No integration found for Gmail user {email}")
        return {"status": "ok"}
        
    metadata = integration.metadata_json or {}
    last_history_id = metadata.get("history_id")
    fcm_token = metadata.get("fcm_token")
    
    if not fcm_token:
        logger.warning(f"No FCM token found for Gmail user {email}, skipping push.")
        metadata["history_id"] = history_id
        integration.metadata_json = dict(metadata)
        db.commit()
        return {"status": "ok"}
        
    # Try to renew the watch in the background if it's expiring soon
    await renew_watch_if_needed(db, integration)

    messages_to_push = []
    history_success = False
    
    # 1. Attempt to call history.list if we have a last_history_id
    if last_history_id:
        history_url = "https://gmail.googleapis.com/gmail/v1/users/me/history"
        try:
            history_response = await call_gmail_api_with_retry(
                db=db,
                integration=integration,
                url=history_url,
                method="GET",
                params={
                    "startHistoryId": str(last_history_id),
                    "historyTypes": "messageAdded"
                }
            )
            if history_response.status_code == 200:
                history_success = True
                history_data = history_response.json()
                for entry in history_data.get("history", []):
                    for added in entry.get("messagesAdded", []):
                        msg = added.get("message")
                        if msg and msg.get("id") not in [m["id"] for m in messages_to_push]:
                            messages_to_push.append(msg)
            else:
                logger.warning(
                    f"History list failed with status {history_response.status_code} "
                    f"for user {email}, falling back to list messages"
                )
        except Exception as e:
            logger.error(f"Error fetching Gmail history for user {email}: {e}")
            
    # 2. Fallback: fetch the latest message list only if history list failed or was not available
    if not history_success and not messages_to_push:
        list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
        try:
            list_response = await call_gmail_api_with_retry(
                db=db,
                integration=integration,
                url=list_url,
                method="GET",
                params={"maxResults": 5}
            )
            if list_response.status_code == 200:
                list_data = list_response.json()
                messages_to_push = list_data.get("messages", [])
        except Exception as e:
            logger.error(f"Error fetching latest Gmail message list for user {email}: {e}")
            
    # 3. Process messages and trigger FCM push
    from app.utils.fcm import send_fcm_notification
    
    for message in messages_to_push[:5]:
        msg_id = message["id"]

        # --- Per-message dedup: skip if this Gmail message was already pushed ---
        msg_redis_key = f"gmail:msg:{msg_id}"
        already_pushed = not redis_client.set(msg_redis_key, "1", nx=True, ex=86400)  # 24h TTL
        if already_pushed:
            logger.info(f"Gmail message {msg_id} already pushed, skipping FCM.")
            continue

        msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
        try:
            msg_response = await call_gmail_api_with_retry(
                db=db,
                integration=integration,
                url=msg_url,
                method="GET",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]}
            )
            if msg_response.status_code == 200:
                msg_detail = msg_response.json()
                parsed = parse_gmail_metadata(msg_detail)
                
                logger.info(f"Triggering FCM push for Gmail user {email}, message {msg_id}")
                send_fcm_notification(
                    token=fcm_token,
                    title="Gmail Activity",
                    body=f"{parsed['sender_name']}: {parsed['subject']}",
                    data={
                        "type": "gmail_event",
                        "nodeType": "GMAIL_MESSAGE_RECEIVED",
                        "email": email,
                        "message_id": parsed["message_id"],
                        "thread_id": parsed["thread_id"],
                        "sender": parsed["sender"],
                        "sender_name": parsed["sender_name"],
                        "subject": parsed["subject"],
                        "snippet": parsed["snippet"],
                        "labels": json.dumps(parsed["labels"]),
                        "history_id": str(history_id)
                    }
                )
            else:
                # Release the Redis key so it can be retried on next webhook
                redis_client.delete(msg_redis_key)
        except Exception as e:
            logger.error(f"Error processing message {msg_id} for push: {e}")
            # Release the Redis key so it can be retried on next webhook
            redis_client.delete(msg_redis_key)

    # 4. Save the new historyId only AFTER successful processing
    metadata["history_id"] = history_id
    integration.metadata_json = dict(metadata)
    try:
        db.commit()
        logger.info(f"Saved history_id={history_id} for Gmail user {email} after processing.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save final history_id for {email}: {e}")

    return {"status": "ok"}


@router.get("/messages/{message_id}")
async def get_message_details(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fetch details of a specific message.
    """
    integration = get_gmail_integration(current_user.id, db)
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    response = await call_gmail_api_with_retry(
        db=db,
        integration=integration,
        url=url,
        method="GET"
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json().get("error", {}).get("message", "Failed to fetch message details")
        )
    return response.json()


@router.get("/threads/{thread_id}")
async def get_thread_details(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fetch conversation thread details.
    """
    integration = get_gmail_integration(current_user.id, db)
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}"
    response = await call_gmail_api_with_retry(
        db=db,
        integration=integration,
        url=url,
        method="GET"
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json().get("error", {}).get("message", "Failed to fetch thread details")
        )
    return response.json()


class ModifyLabelsRequest(BaseModel):
    addLabelIds: list[str] = []
    removeLabelIds: list[str] = []


@router.post("/messages/{message_id}/labels")
async def modify_message_labels(
    message_id: str,
    body: ModifyLabelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Add or remove labels from a specific message.
    """
    integration = get_gmail_integration(current_user.id, db)
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
    response = await call_gmail_api_with_retry(
        db=db,
        integration=integration,
        url=url,
        method="POST",
        json_data={
            "addLabelIds": body.addLabelIds,
            "removeLabelIds": body.removeLabelIds
        }
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json().get("error", {}).get("message", "Failed to modify message labels")
        )
    return response.json()


@router.delete("/messages/{message_id}")
async def trash_message(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Move a specific message to the trash.
    """
    integration = get_gmail_integration(current_user.id, db)
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash"
    response = await call_gmail_api_with_retry(
        db=db,
        integration=integration,
        url=url,
        method="POST"
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json().get("error", {}).get("message", "Failed to trash message")
        )
    return response.json()


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    threadId: str = None


@router.post("/messages/send")
async def send_email(
    body: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Send an email or reply to an existing thread.
    """
    integration = get_gmail_integration(current_user.id, db)
    
    # Build MIME message
    mime_msg = MIMEText(body.body)
    mime_msg["to"] = body.to
    mime_msg["subject"] = body.subject
    
    # Convert to base64url encoded string
    raw_bytes = mime_msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    
    json_data = {
        "raw": raw_b64
    }
    if body.threadId:
        json_data["threadId"] = body.threadId
        
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    response = await call_gmail_api_with_retry(
        db=db,
        integration=integration,
        url=url,
        method="POST",
        json_data=json_data
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json().get("error", {}).get("message", "Failed to send email")
        )
    return response.json()

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
