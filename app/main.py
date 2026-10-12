"""FastAPI entrypoint for HealthSense AI.

Run:  uvicorn app.main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.whatsapp.routes import router as whatsapp_router
from app.db.database import Base, engine
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: create tables if they don't exist (SQLite file appears here).
    Base.metadata.create_all(bind=engine)
    yield
    # (Nothing to clean up on shutdown yet.)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
app.include_router(whatsapp_router)


@app.get("/")
def root():
    return {"message": f"{settings.app_name} is running. See /docs."}
