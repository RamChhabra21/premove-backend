from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from app.core.deps import get_db
from app.models.web_automations import WebAutomation
from app.web.schemas import WebAutomationCreate, WebAutomationResponse
from app.web.crud import create_web_automation, get_web_automation

router = APIRouter(prefix="/web_automations", tags=["Web Automations"])

@router.post("/", response_model=WebAutomationResponse)
def create_web_automation_endpoint(payload: WebAutomationCreate, db: Session = Depends(get_db)):
    # Optional uniqueness check for workflow_id + node_id
    existing = db.query(WebAutomation).filter_by(
        workflow_id=payload.workflow_id,
        node_id=payload.node_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Workflow + Node combination already exists")

    obj = create_web_automation(db, payload)
    return obj

@router.get("/{automation_id}", response_model=WebAutomationResponse)
def get_web_automation_endpoint(automation_id: UUID, db: Session = Depends(get_db)):
    obj = get_web_automation(db, str(automation_id))
    if not obj:
        raise HTTPException(status_code=404, detail="Web Automation not found")
    return obj