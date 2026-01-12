from app.core.database import SessionLocal
from app.web.executor import WebExecutor
from app.models.jobs import Job
from app.web.replay.extract import convert_history_to_playwright_format
from app.web.replay.playwright_engine import execute_model_actions
import app.utils.constants as constants
import asyncio
from app.web.crud import get_by_workflow_and_node, create_web_automation
from app.web.schemas import WebAutomationCreate
from app.llm.client import get_llm_client

class WebService():
    def __init__(self):
        self.db = SessionLocal()
        self.webexecutor = WebExecutor() 
        self.llm = get_llm_client()

    def run_web_automation(self, job : Job, forceNewRun: bool = False):
        extracted_actions = None
        # check if web automation exists for this job
        web_automation = get_by_workflow_and_node(
            self.db,
            workflow_id=job.workflow_id,
            node_id=job.node_id,
        )
        if web_automation:
            extracted_actions = web_automation.actions
        else:
            # create new web automation entry
            web_automation = create_web_automation(
                            self.db,
                            WebAutomationCreate(
                                workflow_id=job.workflow_id,
                                node_id=job.node_id,
                                goal=job.goal,
                                actions={},  # empty initially
                            )
                        )
        if forceNewRun or (not extracted_actions) or len(extracted_actions) == 0:
            # do new agentic task 
            new_history, final_result, is_task_done, is_task_successful, errors = asyncio.run(self.webexecutor.run_browser_task(job.goal, "", constants.BROWSER_USE_PREVIEW_MODEL, False))
            if not is_task_done or not is_task_successful:
                print("Web automation task failed or incomplete. Errors:", errors)
                return {
                    "status": "FAILED",
                    "errors": errors
                }
            # extract actions to perform based on web automation
            extracted_actions = convert_history_to_playwright_format(
                    history_data=new_history, 
                    save_to_file=False,      # do not save to a file
                    verbose=True             # optional, prints debug info
                )
            # save this extracted_actions to db
            web_automation.actions = extracted_actions
            self.db.commit()
            return {
                "status": "COMPLETED",
                "result": final_result
            }
        else:
            results = asyncio.run(execute_model_actions(
                        actions=extracted_actions,
                        headless=False,      # or False if you want to see the browser
                        verbose=True,       # logs all actions
                        keep_browser_open=False  # True to keep browser open after completion
                    ))
            # an llm call with job goal and results to summarize final result 
            final_result = self.llm.summarize_results(job.goal, results)
            return results