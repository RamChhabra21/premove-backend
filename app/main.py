from fastapi import FastAPI
from app.api.api import api_router
import time

app = FastAPI(title="Premove Backend")

app.include_router(api_router, prefix="/api") 

@app.get("/")
async def root():
    return {"status": "healthy"}