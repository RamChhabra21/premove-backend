from functools import lru_cache
from app.llm.llm_gateway import LLMGateway
from app.llm.types import Message, LLMRequest


class LLMClient:
    def __init__(self):
        self.gateway = LLMGateway()

    async def complete(
        self,
        messages: list[Message],
        provider: str | None = None,
        **kwargs,
    ) -> str:
        req = LLMRequest(
            messages=messages,
            provider=provider,
            **kwargs,
        )
        resp = await self.gateway.complete(req)
        return resp.content


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()
