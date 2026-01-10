from app.core.database import SessionLocal
from app.web.executor import WebExecutor
from app.models.jobs import Job
from app.web.replay.extract import convert_history_to_playwright_format
from app.web.replay.playwright_engine import execute_model_actions
import app.utils.constants as constants
import asyncio

class WebService():
    def __init__(self):
        self.db = SessionLocal()
        self.webexecutor = WebExecutor() 

    def run_web_automation(self, job : Job, no_replay: bool = False):
        # web_automation = create_web_automation(
        #                     self.db,
        #                     WebAutomationCreate(
        #                         workflow_id=job.workflow_id,
        #                         node_id=job.node_id,
        #                         goal=job.goal,
        #                         actions={},  # empty initially
        #                     )
        #                 )
        if no_replay:
            # do new agentic task 
            new_history = asyncio.run(self.webexecutor.run_browser_task(job.goal, "", constants.BROWSER_USE_PREVIEW_MODEL, False))
            # extract actions to perform based on web automation
            extracted_actions = convert_history_to_playwright_format(
                    history_data=new_history, 
                    save_to_file=False,      # do not save to a file
                    verbose=True             # optional, prints debug info
                )
            # save this extracted_actions to db
        else:
            results = asyncio.run(execute_model_actions(
                        actions=extracted_actions,
                        headless=False,      # or False if you want to see the browser
                        verbose=True,       # logs all actions
                        keep_browser_open=False  # True to keep browser open after completion
                    ))