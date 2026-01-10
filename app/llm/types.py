from typing import Literal, Optional
from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]

class Message(BaseModel):
    role: Role
    content: str

class LLMRequest(BaseModel):
    messages: list[Message]
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    timeout_s: float = 30.0

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
