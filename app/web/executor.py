# web/executor.py
from browser_use import Agent, Browser, ChatBrowserUse
import asyncio
import json
import logging

class WebExecutor():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        pass
    
    async def run_browser_task(self, instructions: str, rules: str, model: str, isCloud: bool):
        browser = Browser(use_cloud=isCloud)
        try:
            llm = ChatBrowserUse(model=model)

            agent = Agent(
                task=f""" 
                    INSTRUCTIONS:
                    {instructions}

                    RULES:
                    - Only perform actions on the intended website(s)
                    - Do not login/sign up unless explicitly allowed
                    - Do not navigate outside target domain
                    {rules}
                    - Extract only relevant visible information
                """,
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
            self.logger.exception(f"Browser workflow failed with error : {e}")
            raise
    
    async def replay_browser_task(extracted_actions: str):
        pass