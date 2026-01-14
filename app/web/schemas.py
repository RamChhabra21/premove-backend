# app/schemas/web_automation.py
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Any

class WebAutomationCreate(BaseModel):
    workflow_id: UUID
    node_id: int
    goal: str = Field(..., max_length=1000)
    actions: Any  # JSONB content (dict/list)

class WebAutomationResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    node_id: int
    goal: str = Field(..., max_length=1000)
    actions: Any
