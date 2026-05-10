from fastapi import APIRouter, Depends
from app.core.auth import get_current_user, get_current_db_user
from app.models.users import User

router = APIRouter()

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_db_user)):
    """
    Returns the user profile from the database, after verifying the Firebase token.
    If it's the first login, a new user record is created automatically.
    """
    return current_user

@router.get("/token_info")
async def read_token_info(payload: dict = Depends(get_current_user)):
    """
    Returns all claims in the decoded Firebase ID token.
    Useful for debugging what's coming from the mobile app.
    """
    return payload
