from openai import AsyncOpenAI
from app.llm.providers.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse
from app.core.config import settings


class CerebrasProvider(BaseLLMProvider):
    name = "cerebras"
    default_model = "gpt-oss-20b" # High performance default

    def __init__(self):
        # Cerebras is OpenAI compatible
        self.client = AsyncOpenAI(
            api_key=settings.CEREBRAS_API_KEY,
            base_url="https://api.cerebras.ai/v1"
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
            usage=resp.usage.model_dump() if resp.usage else None
        )
