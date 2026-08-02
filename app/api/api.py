from fastapi import APIRouter, Depends
from app.api.endpoints import jobs, web_automations, llm, auth
from app.api.endpoints.integrations import slack, gmail, router as integrations_router
from app.core.auth import get_current_user

# authenticated routes
api_router = APIRouter(dependencies=[Depends(get_current_user)])

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(web_automations.router, tags=["web_automations"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
api_router.include_router(integrations_router.router, prefix="/integrations", tags=["integrations"])

# public routes — no auth dependency
public_router = APIRouter()
public_router.include_router(slack.router, prefix="/slack", tags=["slack"])
public_router.include_router(gmail.router, prefix="/gmail", tags=["gmail"])