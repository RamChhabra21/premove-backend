# web/executor.py
from browser_use import Agent, Browser, ChatBrowserUse, BrowserProfile, ChatGroq
import json
import logging
from app.web.replay.playwright_engine import execute_model_actions
from app.prompts import BROWSER_TASK_PROMPT

class WebExecutor():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def run_browser_task(self, instructions: str, rules: str, model: str, isCloud: bool):
        """
        Execute a browser automation task.
        
        Args:
            instructions: Structured instructions for the browser agent
            rules: Additional rules/constraints for the task
            model: LLM model to use
            isCloud: Whether to use cloud browser
        
        Returns:
            Tuple of (history_dict, final_result, is_task_done, is_task_successful, errors)
        """
        browser = Browser(
            use_cloud=isCloud,
            browser_profile=BrowserProfile(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        )
        try:
            # llm = ChatBrowserUse(model=model)

            llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct")


            # Use prompt template from prompts folder
            task_prompt = BROWSER_TASK_PROMPT.format(
                instructions=instructions,
                additional_rules=rules if rules else ""
            )

            agent = Agent(
                task=task_prompt,
                llm=llm,
                browser=browser
            )

            history = await agent.run()

            final_result = history.final_result()
            is_task_done = history.is_done()
            is_task_successful = history.is_successful()
            errors = history.errors()

            history_dict = json.loads(json.dumps(history.__dict__, default=str))

            return history_dict, final_result, is_task_done, is_task_successful, errors

        except Exception as e:
            self.logger.exception(f"Browser workflow failed with error: {e}")
            raise
        finally:
            # Ensure browser is closed
            try:
                await browser.close()
            except:
                pass
    
    async def replay_browser_task(self, extracted_actions: str):
        """
        Replay previously recorded browser actions.
        
        Args:
            extracted_actions: Previously extracted actions to replay
        
        Returns:
            Results from the replayed actions
        """
        return await execute_model_actions(
            actions=extracted_actions,
            headless=True,
            verbose=True,
            keep_browser_open=False
        )