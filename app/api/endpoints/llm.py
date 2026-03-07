from fastapi import APIRouter, HTTPException
from app.llm.llm_gateway import LLMGateway
from app.llm.types import LLMRequest, LLMResponse

router = APIRouter()
gateway = LLMGateway()

@router.post("/complete", response_model=LLMResponse)
async def complete_llm(request: LLMRequest):
    """
    Synchronous LLM completion endpoint.
    """
    try:
        return await gateway.complete(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
