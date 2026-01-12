from app.llm.providers.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse, Message, Role

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Convert messages → Anthropic format
        prompt = "\n".join(
            f"{m.role.value.upper()}: {m.content}"
            for m in request.messages
        )

        content = "Response from Anthropic"

        return LLMResponse(
            content=content,
            provider=self.name,
            model=request.model,
        )
