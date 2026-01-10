from fastapi import APIRouter
from app.api.endpoints import jobs, web_automations

api_router = APIRouter()

api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(web_automations.router, tags=["web_automations"])