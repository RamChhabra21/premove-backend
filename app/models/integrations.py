from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class UserIntegration(Base):
    __tablename__ = "user_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True) # 'slack', 'google', etc.
    external_id = Column(String, nullable=True, index=True) # ID from the provider (e.g. Slack UID)
    credentials = Column(JSONB, nullable=False) # Stores tokens, secrets
    metadata_json = Column("metadata", JSONB, nullable=True) # FCM tokens, flags, etc.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship back to user
    user = relationship("User", back_populates="integrations")

    def __repr__(self):
        return f"<UserIntegration(provider='{self.provider}', user_id='{self.user_id}')>"
