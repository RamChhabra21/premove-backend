from pydantic import BaseModel
from uuid import UUID
from app.models.jobs import WorkflowTypeEnum

class JobCreate(BaseModel):  
    workflow_id: UUID     
    goal: str        
    node_id: str
    workflow_type: WorkflowTypeEnum

class JobResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    goal: str
    status: str