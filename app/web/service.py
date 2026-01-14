from app.core.database import SessionLocal
from app.web.executor import WebExecutor
from app.web.planner import WebPlanner
from app.models.jobs import Job
from app.web.replay.extract import convert_history_to_playwright_format
import app.utils.constants as constants
from app.web.crud import get_by_workflow_and_node, create_web_automation
from app.web.schemas import WebAutomationCreate
from app.llm.client import get_llm_client
from app.llm.types import Message, Role
from app.core.exceptions import BrowserTaskFailedException, LLMAPIException
from app.core.logging_config import logger
from app.prompts import RESULT_SUMMARIZATION_PROMPT
import logging

class WebService():
    """
    Web automation service.
    
    Orchestrates browser automation tasks including planning, execution,
    caching, and result summarization.
    """
    
    def __init__(self):
        self.webexecutor = WebExecutor() 
        self.planner = WebPlanner()
        self.llm = get_llm_client()
        self.logger = logging.getLogger("premove.web_service")

    async def run_web_automation(self, job: Job, forceNewRun: bool = False):
        """
        Run web automation for a job.
        
        Args:
            job: Job instance to process
            forceNewRun: Force a new agentic run even if cached actions exist
            
        Returns:
            dict with status and result/error
        """
        db = SessionLocal()
        try:
            extracted_actions = None
            
            # Check if web automation exists for this job
            web_automation = get_by_workflow_and_node(
                db,
                workflow_id=job.workflow_id,
                node_id=job.node_id,
            )
            
            if web_automation:
                extracted_actions = web_automation.actions
                self.logger.info(f"Found existing web automation for workflow {job.workflow_id}, node {job.node_id}")
            else:
                # Create new web automation entry
                self.logger.info(f"Creating new web automation for workflow {job.workflow_id}, node {job.node_id}")
                web_automation = create_web_automation(
                    db,
                    WebAutomationCreate(
                        workflow_id=job.workflow_id,
                        node_id=job.node_id,
                        goal=job.goal,
                        actions={},  # empty initially
                    )
                )
            
            # Determine if we need to run a new agentic task
            if forceNewRun or (not extracted_actions) or len(extracted_actions) == 0 or job.goal != web_automation.goal:
                self.logger.info(f"Running new agentic browser task for goal: {job.goal}")
                
                try:
                    # Use planner to convert goal into structured instructions
                    self.logger.info("Using planner to generate structured instructions")
                    planned_instructions = await self.planner.plan_browser_task(
                        user_goal=job.goal
                    )
                    
                    # Do new agentic task with planned instructions
                    new_history, final_result, is_task_done, is_task_successful, errors = await self.webexecutor.run_browser_task(
                        planned_instructions,  # Use planned instructions instead of raw goal
                        "", 
                        constants.BROWSER_USE_PREVIEW_MODEL, 
                        False
                    )
                    
                    if not is_task_done or not is_task_successful:
                        error_msg = f"Web automation task failed or incomplete. Errors: {errors}"
                        self.logger.error(error_msg)
                        raise BrowserTaskFailedException(job.goal, errors)
                    
                    # Extract actions to perform based on web automation
                    self.logger.info("Extracting actions from browser history")
                    extracted_actions = convert_history_to_playwright_format(
                        history_data=new_history, 
                        save_to_file=False,
                        verbose=True
                    )
                    
                    # Save the updated goal and actions
                    web_automation.goal = job.goal 
                    web_automation.actions = extracted_actions
                    db.commit()
                    
                    self.logger.info(f"Successfully completed new automation and saved {len(extracted_actions)} actions")
                    
                    return {
                        "status": "COMPLETED",
                        "result": final_result
                    }
                    
                except BrowserTaskFailedException:
                    raise
                except Exception as e:
                    self.logger.exception(f"Error during browser task execution: {e}")
                    raise BrowserTaskFailedException(job.goal, [str(e)])
            else:
                # Reuse existing extracted actions
                self.logger.info(f"Reusing existing {len(extracted_actions)} actions for web automation")
                
                try:
                    results = await self.webexecutor.replay_browser_task(extracted_actions)
                    
                    # Use LLM to summarize the results with prompt template
                    self.logger.info("Calling LLM to summarize results")
                    
                    # Use prompt template for summarization
                    summarization_prompt = RESULT_SUMMARIZATION_PROMPT.format(
                        job_goal=job.goal,
                        raw_results=results
                    )
                    
                    messages = [
                        Message(role=Role.SYSTEM, content="You are an expert at extracting and summarizing web automation results."),
                        Message(role=Role.USER, content=summarization_prompt),
                    ]
                    
                    try:
                        retrieved_result = await self.llm.complete(
                            messages,
                            provider="openai",
                            temperature=0.1,
                        )
                        self.logger.info(f"Final summarized result: {retrieved_result}")
                        
                        return {
                            "status": "COMPLETED",
                            "result": retrieved_result
                        }
                    except Exception as e:
                        self.logger.error(f"LLM API error during summarization: {e}")
                        raise LLMAPIException("openai", str(e))
                        
                except Exception as e:
                    self.logger.exception(f"Error during browser task replay: {e}")
                    raise BrowserTaskFailedException(job.goal, [str(e)])
                    
        except (BrowserTaskFailedException, LLMAPIException):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in run_web_automation: {e}")
            raise
        finally:
            db.close()