import app.utils.constants as constants
import time
import asyncio
import json
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.jobs.models import Job
from app.web.executor import run_browser_task
from app.web.replay.extract import convert_history_to_playwright_format
from app.web.replay.playwright_engine import execute_model_actions

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

        if(job.workflow_type == "WEB_QUERY"): 
            goal = job.goal
            history = asyncio.run(run_browser_task("go to google.com and get title", "", constants.BROWSER_USE_PREVIEW_MODEL, False))
            history_str = json.dumps(history, indent=2)
            print(history_str[:500])
            extracted_actions = convert_history_to_playwright_format(
                                history_data=history, 
                                save_to_file=False,      # do not save to a file
                                verbose=True             # optional, prints debug info
                            )
            print(extracted_actions)
            results = asyncio.run(execute_model_actions(
                        actions=extracted_actions,
                        headless=False,      # or False if you want to see the browser
                        verbose=True,       # logs all actions
                        keep_browser_open=False  # True to keep browser open after completion
                    ))
            print(results)
        # update job status after job completion
        job.status = "COMPLETED"
        db.commit()
    except Exception as e:
        print(" exeception occured : ",e)
    finally:
        db.close()
    # print(" job processing started ", job_id)