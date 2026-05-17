import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from app.core.logging_config import logger
from app.core.exceptions import InvalidTokenException, TokenExpiredException
from app.core.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.users import User
import json
import os
import jwt
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

# Initialize Firebase Admin SDK
try:
    if not firebase_admin._apps:
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
            cred_dict = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized with service account JSON")
        elif settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            logger.info(f"Firebase Admin SDK initialized with credentials from {settings.FIREBASE_CREDENTIALS_PATH}")
        else:
            # Fallback for verification-only (requires project ID to be set in environment)
            # Or reliance on Application Default Credentials (ADC)
            try:
                options = {"projectId": settings.FIREBASE_PROJECT_ID} if settings.FIREBASE_PROJECT_ID else {}
                firebase_admin.initialize_app(options=options)
                logger.info(f"Firebase Admin SDK initialized with default credentials (Project: {settings.FIREBASE_PROJECT_ID or 'auto-detected'})")
            except Exception as e:
                logger.warning(f"Firebase Admin SDK not initialized: {e}")
except Exception as e:
    logger.error(f"Error initializing Firebase Admin SDK: {e}")

security = HTTPBearer(auto_error=False)

async def get_current_user(request: Request, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """
    FastAPI dependency to verify the Firebase ID token in the request header.
    Internally uses Google's public keys to verify the signature (RS256).
    
    In development mode, if no token is provided, it returns a mock user.
    """
    if not token:
        if settings.ENVIRONMENT == "development":
            logger.info("No authentication token provided; using mock user in development mode")
            return {
                "uid": "dev-user-id",
                "email": "dev@example.com",
                "name": "Development User",
                "picture": None,
                "email_verified": True
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    id_token = token.credentials
    try:
        # Verify the ID token. firebase-admin handles public key fetching & caching.
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except auth.ExpiredIdTokenError:
        raise TokenExpiredException()
    except auth.InvalidIdTokenError:
        raise InvalidTokenException("Invalid Firebase ID token")
    except auth.RevokedIdTokenError:
        raise InvalidTokenException("Firebase ID token has been revoked")
    except Exception as e:
        logger.error(f"Error verifying Firebase token: {e}")
        raise InvalidTokenException(str(e))


async def get_current_db_user(
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Returns the SQLAlchemy User object from the database.
    If the user doesn't exist, it creates a new entry (Auto-registration).
    """
    uid = payload.get("uid")
    if not uid:
        raise InvalidTokenException("UID missing from token")

    # Query by firebase_uid instead of id
    user = db.query(User).filter(User.firebase_uid == uid).first()
    
    if not user:
        # Auto-registration flow
        email = payload.get("email")
        if not email:
            # Fallback or error depending on requirements
            # In some cases email might be missing from token if not verified or social provider issue
            logger.warning(f"Email missing from token for user {uid}")
            
        user = User(
            firebase_uid=uid,
            email=email,
            name=payload.get("name"),
            profile_url=payload.get("picture")
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            logger.info(f"New user registered: {email} ({uid})")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to register user {uid}: {e}")
            # Try to get the user again in case of race condition
            user = db.query(User).filter(User.firebase_uid == uid).first()
            if not user:
                raise HTTPException(status_code=500, detail="Failed to create/fetch user record")
    
    # Update last_seen_at on every successful identification
    try:
        user.last_seen_at = func.now()
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update last_seen_at for user {uid}: {e}")
    
    return user


def get_user_id(payload: dict = Depends(get_current_user)) -> str:
    """
    Returns only the UID from the validated token. Use this if you don't need
    the full User object or DB access.
    """
    return payload.get("uid")


# Custom JWT (Backend issued) helpers - useful for short-lived session optimization
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredException()
    except jwt.PyJWTError:
        raise InvalidTokenException("Invalid backend JWT")
