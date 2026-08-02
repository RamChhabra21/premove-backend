from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_db_user
from app.models.users import User
from app.models.integrations import UserIntegration
from app.core.logging_config import logger

router = APIRouter()


@router.get("/")
async def list_all_user_integrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user)
):
    """
    Fast DB-driven check returning connection status for all 3rd-party integrations in 1 query.
    """
    integrations = db.query(UserIntegration).filter_by(user_id=current_user.id).all()
    provider_map = {item.provider: item for item in integrations}

    supported_providers = ["slack", "gmail"]
    status_summary = {}

    for provider in supported_providers:
        integration = provider_map.get(provider)
        has_credentials = bool(
            integration and 
            integration.credentials and 
            ("access_token" in integration.credentials or "refresh_token" in integration.credentials)
        )
        status_summary[provider] = {
            "connected": has_credentials,
            "external_id": integration.external_id if (integration and has_credentials) else None,
            "updated_at": integration.updated_at.isoformat() if (integration and has_credentials and integration.updated_at) else None
        }

    return status_summary
