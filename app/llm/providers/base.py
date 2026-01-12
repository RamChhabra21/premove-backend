from abc import ABC, abstractmethod
from app.llm.types import LLMRequest, LLMResponse

class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        pass
