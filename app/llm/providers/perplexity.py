# llm/providers/perplexity.py
from openai import AsyncOpenAI
from app.llm.providers.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse
from app.core.config import settings

class PerplexityProvider(BaseLLMProvider):
    name = "perplexity"

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.PERPLEXITY_API_KEY,
            base_url=settings.PERPLEXITY_BASE_URL
        )
        self.default_model = "sonar"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        resp = await self.client.chat.completions.create(
            model=request.model or self.default_model,
            messages=[m.model_dump() for m in request.messages],
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        return LLMResponse(
            content=resp.choices[0].message.content,
            model=resp.model,
            provider=self.name,
        )
