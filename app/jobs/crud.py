from app.models.jobs import Job
from app.jobs.schemas import JobCreate, JobResponse
from uuid6 import uuid7
from sqlalchemy.orm import Session
from uuid import UUID
from app.tasks.tasks import process_job


def create_job(db: Session, job_dto: JobCreate) -> str:
    new_job = Job(
        id=uuid7(),
        workflow_id=job_dto.workflow_id,
        goal=job_dto.goal,
        node_id=job_dto.node_id,
        workflow_type=job_dto.workflow_type.value
    )
    job_log = Job
    db.add(new_job)      
    db.commit()         
    db.refresh(new_job) 

    return str(new_job.id)

def get_job(db: Session, job_id: UUID):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return
    return job 