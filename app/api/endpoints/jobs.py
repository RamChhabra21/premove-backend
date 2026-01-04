from fastapi import APIRouter, Depends
from app.jobs.crud import create_job, get_job
from app.jobs.schemas import JobCreate
from app.core.deps import get_db
from uuid import UUID

router = APIRouter()

@router.post("/job")
def create_job_api(job: JobCreate, db=Depends(get_db)):
    job_id = create_job(db,job)
    return {"job_id": job_id, "status": "queued1"}

@router.get("/job/{job_id}")
def get_job_api(job_id: UUID, db=Depends(get_db)):
    job = get_job(db,job_id)
    return job