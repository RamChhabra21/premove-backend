from openai import AsyncOpenAI
from app.llm.types import LLMRequest, LLMResponse
from app.llm.providers.base import BaseLLMProvider
from dotenv import load_dotenv
import os
load_dotenv() 

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = AsyncOpenAI()

        response = await client.chat.completions.create(
            model=request.model or "gpt-4o",
            messages=[{"role": m.role.value, "content": m.content} for m in request.messages],
            temperature=request.temperature,
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            provider=self.name,
            model=response.model,
            raw=response,
        )
