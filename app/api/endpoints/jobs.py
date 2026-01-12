from fastapi import APIRouter, Depends
from app.jobs.crud import create_job, get_job
from app.jobs.schemas import JobCreate
from app.core.deps import get_db
from app.tasks.tasks import process_job
from uuid import UUID

router = APIRouter()

@router.post("/job")
def create_job_api(job: JobCreate, db=Depends(get_db)):
    print("Received job creation request:", job)
    job_id = create_job(db,job)
    # push to the queue using celery here 
    process_job.delay(job_id)
    return {"job_id": job_id, "status": "queued1"}

@router.get("/job/{job_id}")
def get_job_api(job_id: UUID, db=Depends(get_db)):
    job = get_job(db,job_id)
    return job