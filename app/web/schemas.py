# app/schemas/web_automation.py
from pydantic import BaseModel
from uuid import UUID
from typing import Any

class WebAutomationCreate(BaseModel):
    workflow_id: UUID
    node_id: int
    goal: str
    actions: Any  # JSONB content (dict/list)

class WebAutomationResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    node_id: int
    goal: str
    actions: Any
