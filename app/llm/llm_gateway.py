from llm.providers.openai import OpenAIProvider
from llm.types import LLMRequest, LLMResponse

class LLMGateway:
    def __init__(self):
        self.provider = OpenAIProvider()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self.provider.complete(request)