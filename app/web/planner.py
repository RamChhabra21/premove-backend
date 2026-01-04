# web/planner.py
from browser_use import ChatBrowserUse
import asyncio

async def plan_browser_task(user_intent: str, max_steps: int = 12) -> str:
    """
    Converts a user intent string into structured, executor-safe browser instructions.
    
    Returns a string ready to feed into executor.run_browser_task()
    """
    llm = ChatBrowserUse()  # Using browser-use LLM (bu-1-0 internally)

    # Construct the planning prompt
    planning_prompt = f"""
You are a web automation planner.

User Intent:
{user_intent}

Rules for generating the instructions:
1. Break the task into numbered, browser-executable steps.
2. Maximum steps: {max_steps}.
3. Include explicit stop conditions (e.g., max scrolls, clicks, or "stop if no progress").
4. Include output format instructions (e.g., strict JSON).
5. Do NOT invent extra steps or navigate outside the target domain.
6. Avoid repeating actions.
7. Return ONLY the structured steps in text (no explanations, no reasoning).

Example output format:
1. Open https://shop.amul.com
2. Enter pincode 110032 if prompted
3. Search for "Protein"
4. Open Protein listing page
5. Scroll max 3 times until no new products load
6. Extract visible product data
7. Stop
"""

    # Run the LLM
    task_agent = await llm.chat(planning_prompt)
    return task_agent.content  # this is the executor-ready instructions


# Optional helper function for sync calls
def plan_browser_task_sync(user_intent: str, max_steps: int = 12) -> str:
    return asyncio.run(plan_browser_task(user_intent, max_steps))
