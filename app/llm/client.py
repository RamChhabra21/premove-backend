from llm.gateway import LLMGateway
from llm.types import Message, LLMRequest

class LLMClient:
    def __init__(self):
        self.gateway = LLMGateway()

    async def complete(self, messages: list[Message], **kwargs) -> str:
        req = LLMRequest(messages=messages, **kwargs)
        resp = await self.gateway.complete(req)
        return resp.content

@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()
