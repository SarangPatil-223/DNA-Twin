"""FastAPI entry point. DNA Twin is a simulation: nothing here touches real DNA."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core import __version__
from app.db.session import init_db
from app.settings import get_settings

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="DNA Twin", version=__version__, lifespan=lifespan,
              description="Software-only digital twin of DNA data storage with an LLM knowledge base. Simulation only.")
app.add_middleware(CORSMiddleware, allow_origins=[o for o in get_settings().cors_origins if o] or ["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(router, prefix="/api")  # same routes behind /api for the Next.js proxy
