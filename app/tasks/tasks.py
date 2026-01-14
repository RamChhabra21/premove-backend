import app.utils.constants as constants
import asyncio
import logging
from datetime import datetime
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.jobs import Job
from app.web.service import WebService
from app.core.exceptions import BrowserTaskFailedException
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("premove.tasks")

@celery_app.task(
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    time_limit=settings.CELERY_TASK_TIME_LIMIT
)
def process_job(self, job_id: str):
    """
    Process a job by executing the appropriate workflow based on job type.
    
    Args:
        self: Celery task instance (for retry functionality)
        job_id: UUID of the job to process
    """
    db = SessionLocal()
    try:
        from app.jobs.crud import get_job
        
        # Fetch job from database
        try:
            job = get_job(db, job_id)
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id}: {e}")
            return
        
        # Update job status to RUNNING and set started_at timestamp
        job.status = "RUNNING"
        job.started_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Job {job_id} processing started - Type: {job.workflow_type}, Goal: {job.goal}")

        # Process based on workflow type
        if job.workflow_type == "WEB":
            try:
                # Call web service to execute browser automation
                webService = WebService()
                web_automation_result = asyncio.run(
                    webService.run_web_automation(job, forceNewRun=False)
                )
                
                status = web_automation_result["status"]
                final_web_result = web_automation_result.get("result")
                
                job.status = status
                if job.status == "COMPLETED":
                    job.result = final_web_result
                    logger.info(f"Job {job_id} completed successfully")
                elif job.status == "FAILED":
                    job.error_message = final_web_result
                    logger.error(f"Job {job_id} failed: {final_web_result}")
                
                job.finished_at = datetime.utcnow()
                db.commit()
                
            except SoftTimeLimitExceeded:
                logger.warning(f"Job {job_id} exceeded soft time limit, attempting graceful shutdown")
                job.status = "FAILED"
                job.error_message = "Task exceeded time limit"
                job.finished_at = datetime.utcnow()
                db.commit()
                raise
                
            except BrowserTaskFailedException as e:
                logger.error(f"Browser task failed for job {job_id}: {e.message}")
                job.status = "FAILED"
                job.error_message = e.message
                job.finished_at = datetime.utcnow()
                db.commit()
                
            except Exception as e:
                logger.exception(f"Unexpected error processing job {job_id}: {e}")
                
                # Retry on transient errors
                if self.request.retries < self.max_retries:
                    logger.info(f"Retrying job {job_id} (attempt {self.request.retries + 1}/{self.max_retries})")
                    job.status = "PENDING"
                    db.commit()
                    raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))  # Exponential backoff
                else:
                    logger.error(f"Job {job_id} failed after {self.max_retries} retries")
                    job.status = "FAILED"
                    job.error_message = f"Failed after {self.max_retries} retries: {str(e)}"
                    job.finished_at = datetime.utcnow()
                    db.commit()
        else:
            logger.warning(f"Unknown workflow type for job {job_id}: {job.workflow_type}")
            job.status = "FAILED"
            job.error_message = f"Unknown workflow type: {job.workflow_type}"
            job.finished_at = datetime.utcnow()
            db.commit()
            
    except Exception as e:
        logger.exception(f"Critical error in process_job for {job_id}: {e}")
        # Try to update job status even if something went wrong
        try:
            if 'job' in locals():
                job.status = "FAILED"
                job.error_message = f"Critical error: {str(e)}"
                job.finished_at = datetime.utcnow()
                db.commit()
        except:
            logger.error(f"Failed to update job status for {job_id} after critical error")
    finally:
        db.close()
        logger.debug(f"Database session closed for job {job_id}")