# web/planner.py
"""
Web automation planner.

This module handles planning and preparation of browser automation tasks.
It converts high-level user goals into structured, executable instructions.
"""

from app.llm.client import get_llm_client
from app.llm.types import Message, Role
from app.prompts import PLANNING_PROMPT
from app.core.logging_config import logger
import logging
from typing import Optional


class WebPlanner:
    """
    Plans and structures web automation tasks.
    """
    
    def __init__(self):
        self.llm = get_llm_client()
        self.logger = logging.getLogger("premove.web_planner")
    
    async def plan_browser_task(self, user_goal: str) -> str:
        """
        Converts a user intent string into structured, executor-safe browser instructions.
        """
        self.logger.info(f"Planning browser task for goal: {user_goal}")
        
        prompt = PLANNING_PROMPT.format(user_goal=user_goal)
        messages = [Message(role=Role.USER, content=prompt)]
        
        try:
            instructions = await self.llm.complete(
                messages,
                provider="perplexity",
                temperature=0.2,
            )
            self.logger.info(f"Generated instructions: {instructions[:200]}...")
            return instructions
            
        except Exception as e:
            self.logger.error(f"Failed to plan browser task: {e}")
            return user_goal