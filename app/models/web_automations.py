# app/models/web_automation.py
import uuid
from sqlalchemy import Column, String, Integer, JSON, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base 

class WebAutomation(Base):
    __tablename__ = "web_automations"
    __table_args__ = (
        UniqueConstraint("workflow_id", "node_id", name="workflow_node_unique"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    node_id = Column(Integer, nullable=False)
    goal = Column(String, nullable=False)
    actions = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
