# web/planner.py
from browser_use import ChatBrowserUse
import asyncio
from app.llm.client import get_llm_client

async def plan_browser_task(user_intent: str) -> str:
    """
    Converts a user intent string into structured, executor-safe browser instructions.
    
    Returns a string ready to feed into executor.run_browser_task()
    """
    # call to llm to generate prompt for input actions 