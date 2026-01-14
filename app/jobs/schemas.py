from pydantic import BaseModel, Field
from uuid import UUID
from app.models.jobs import WorkflowTypeEnum

class JobCreate(BaseModel):  
    workflow_id: UUID     
    goal: str = Field(..., max_length=1000)
    node_id: str = Field(..., max_length=100)
    workflow_type: WorkflowTypeEnum

class JobResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    goal: str = Field(..., max_length=1000)
    status: str