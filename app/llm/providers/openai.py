# llm/providers/openai.py
from openai import AsyncOpenAI   

from llm.providers.base import BaseLLMProvider
from llm.types import LLMRequest, LLMResponse

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self):
        self.client = AsyncOpenAI()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        resp = await self.client.chat.completions.create(
            model=request.model,
            messages=[m.model_dump() for m in request.messages],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout=request.timeout_s,
        )

        return LLMResponse(
            content=resp.choices[0].message.content,
            model=resp.model,
            provider=self.name,
        )
