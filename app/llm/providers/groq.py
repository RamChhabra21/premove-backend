# llm/providers/groq.py
from groq import AsyncGroq
from app.llm.providers.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse
from app.core.config import settings


class GroqProvider(BaseLLMProvider):
    name = "groq"
    default_model = "openai/gpt-oss-20b" 

    def __init__(self):
        self.client = AsyncGroq(
            api_key=settings.GROQ_API_KEY
        )

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
            usage=resp.usage.model_dump() if resp.usage else None  # Bonus: Track tokens
        )
