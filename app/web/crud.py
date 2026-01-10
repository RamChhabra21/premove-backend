from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from app.models.web_automations import WebAutomation
from app.web.schemas import WebAutomationCreate


def create_web_automation(
    db: Session,
    payload: WebAutomationCreate,
) -> WebAutomation:
    obj = WebAutomation(
        id=uuid4(),
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        goal=payload.goal,
        actions=payload.actions,
    )

    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_web_automation(
    db: Session,
    automation_id: UUID,
) -> WebAutomation | None:
    return (
        db.query(WebAutomation)
        .filter(WebAutomation.id == automation_id)
        .first()
    )


def get_by_workflow_and_node(
    db: Session,
    workflow_id: UUID,
    node_id: int,
) -> WebAutomation | None:
    return (
        db.query(WebAutomation)
        .filter(
            WebAutomation.workflow_id == workflow_id,
            WebAutomation.node_id == node_id,
        )
        .first()
    )
