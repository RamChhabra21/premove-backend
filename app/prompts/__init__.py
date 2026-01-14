"""
Prompt templates package.

This package contains essential prompt templates used throughout the application.
"""

from app.prompts.browser_automation import (
    BROWSER_TASK_PROMPT,
    PLANNING_PROMPT,
    RESULT_SUMMARIZATION_PROMPT,
)

__all__ = [
    "BROWSER_TASK_PROMPT",
    "PLANNING_PROMPT",
    "RESULT_SUMMARIZATION_PROMPT",
]
