from enum import Enum
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: Role
    content: str


class LLMRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    provider: Optional[str] = None  
    metadata: Dict[str, Any] = {}


class LLMResponse(BaseModel):
    content: str
    raw: Optional[Any] = None
    provider: Optional[str] = None
    model: Optional[str] = None
