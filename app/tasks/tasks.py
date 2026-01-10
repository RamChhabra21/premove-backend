import app.utils.constants as constants
import time
import asyncio
import json
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.jobs import Job
from app.web.service import WebService

@celery_app.task
def process_job(job_id : str):
    # pull job details from db and start job execution
    db = SessionLocal()
    try:
        from app.jobs.crud import get_job
        job = get_job(db,job_id)
        if not job:
            print(f"Job {job_id} not found")
            return

        # update job status
        job.status = "RUNNING"
        db.commit()    

        print("Job processing started:", job_id)

        # here is the entry point for whole application (job processing based off job types)  

        if(job.workflow_type == "WEB"): 
            # call web service here to do the actions
            webService = WebService()
            no_replay=True
            webService.run_web_automation(job,no_replay)
        # update job status after job completion
        job.status = "COMPLETED"
        db.commit()
    except Exception as e:
        print(" exeception occured : ",e)
    finally:
        db.close()