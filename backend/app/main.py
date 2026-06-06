import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import sessions, documents, ws
from app.lifecycle.sweeper import run_sweeper

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper_task = asyncio.create_task(run_sweeper())
    yield
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Talk to your PDF — API",
    description="Upload PDFs, ask questions, get cited answers.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
