from app.llm.providers.open_ai import OpenAIProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.types import LLMRequest, LLMResponse

class LLMGateway:
    def __init__(self):
        self.providers = {
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
        }

        self.default_provider = "openai"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        provider_name = request.provider or self.default_provider

        if provider_name not in self.providers:
            raise ValueError(f"Unknown LLM provider: {provider_name}")

        provider = self.providers[provider_name]
        return await provider.complete(request)
