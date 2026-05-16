from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import httpx
import os

router = APIRouter()

class SlackExchangeRequest(BaseModel):
    code: str
    fcm_token: str
    code_verifier: str

@router.get("/callback")
async def slack_callback(code: str = None, state: str = None, error: str = None):
    """
    Slack redirects here after user authorizes.
    Android app intercepts this via App Links — this just needs to return 200.
    """
    if error:
        return {"status": "denied", "error": error}
    return {"status": "ok"}

@router.post("/exchange")
async def slack_exchange(body: SlackExchangeRequest):
    """
    Android app calls this with the code + PKCE verifier + FCM token.
    We exchange the code with Slack and store the token.
    """
    async with httpx.AsyncClient() as client:
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

    data = response.json()

    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error", "slack_exchange_failed"))

    slack_user_id = data["authed_user"]["id"]
    slack_token = data["authed_user"]["access_token"]

    # TODO: store slack_user_id, slack_token, body.fcm_token in your DB

    return {"status": "ok", "slack_user_id": slack_user_id}