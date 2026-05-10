from fastapi import APIRouter, Depends, HTTPException
from app.jobs.crud import create_job, get_job
from app.jobs.schemas import JobCreate
from app.core.deps import get_db
from app.tasks.tasks import process_job
from uuid import UUID
from app.core.auth import get_user_id

router = APIRouter()

@router.post("/job")
def create_job_api(job: JobCreate, db=Depends(get_db), user_id: str = Depends(get_user_id)):
    print(f"Received job creation request from user {user_id}: {job}")
    job_id = create_job(db, job, user_id=user_id)
    # push to the queue using celery here 
    process_job.delay(job_id)
    return {"job_id": job_id, "status": "queued"}

@router.get("/job/{job_id}")
def get_job_api(job_id: UUID, db=Depends(get_db), user_id: str = Depends(get_user_id)):
    job = get_job(db, job_id)
    if job.user_id and job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    return job