"""
Browser automation task prompts.

This module contains essential prompt templates for browser automation.
"""

# Main browser task prompt template
BROWSER_TASK_PROMPT = """
{instructions}

RULES:
- Only visit intended websites
- No login/signup unless specified
- Extract only visible, relevant data
{additional_rules}
"""

# Planning prompt - refines user goal with details without listing actions
PLANNING_PROMPT = """
Refine this web automation goal with specific details for the browser agent:

GOAL: {user_goal}

Add details about:
- Target URLs
- Specific data fields to extract
- Constraints or success criteria

STRICT LIMIT: Max 100 words. Do NOT list browser actions.
"""

# Result summarization prompt
RESULT_SUMMARIZATION_PROMPT = """
Summarize this web automation result:

GOAL: {job_goal}
DATA: {raw_results}

STRICT LIMIT: Max 50 words. Extract only relevant info. No metadata.
"""
