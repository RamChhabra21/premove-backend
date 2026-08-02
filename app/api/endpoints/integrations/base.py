from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.integrations import UserIntegration


class BaseIntegration(ABC):
    """
    Abstract Base Class for all 3rd-party SaaS integrations (Slack, Gmail, etc.).
    Enforces a standard contract for authentication, token management, and status checks.
    """
    provider_name: str  # e.g. "slack", "gmail"

    @abstractmethod
    async def exchange_code(self, code: str, user_id: str, db: Session, **kwargs) -> UserIntegration:
        """Exchanges OAuth code for access/refresh tokens and persists them in DB."""
        pass

    @abstractmethod
    async def refresh_token(self, integration: UserIntegration, db: Session) -> str:
        """Refreshes access token using the stored refresh_token and updates DB."""
        pass

    @abstractmethod
    async def get_token(self, user_id: str, db: Session, force_refresh: bool = False) -> str:
        """Returns a valid access token, performing proactive auto-refresh if expired."""
        pass

    @abstractmethod
    async def get_status(self, user_id: str, db: Session) -> Dict[str, Any]:
        """Returns connection status for this provider (connected, external_id, updated_at)."""
        pass
