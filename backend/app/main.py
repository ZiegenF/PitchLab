import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .photos import UPLOAD_DIR
from .routers import account, ingest, me, pitchers


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # swap for Alembic migrations once the schema settles
    yield


app = FastAPI(title="PitchLab API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,  # session cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(account.router)
app.include_router(me.router)
app.include_router(pitchers.router)
app.include_router(ingest.router)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
