import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.chat import router as chat_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LLM Guard Chat",
    description="A small interactive LLM chat app with a prompt-injection defense layer.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.get("/")
async def root():
    return {"name": "LLM Guard Chat API", "docs": "/docs"}
