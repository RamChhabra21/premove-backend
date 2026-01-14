from app.llm.providers.open_ai import OpenAIProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.perplexity import PerplexityProvider
from app.llm.types import LLMRequest, LLMResponse

class LLMGateway:
    def __init__(self):
        self._provider_classes = {
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "perplexity": PerplexityProvider,
        }
        self._instances = {}
        self.default_provider = "perplexity"

    def _get_provider(self, name: str):
        if name not in self._instances:
            if name not in self._provider_classes:
                raise ValueError(f"Unknown LLM provider: {name}")
            
            provider_class = self._provider_classes[name]
            self._instances[name] = provider_class()
        return self._instances[name]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        provider_name = request.provider or self.default_provider
        provider = self._get_provider(provider_name)
        return await provider.complete(request)
