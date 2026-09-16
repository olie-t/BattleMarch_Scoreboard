from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import secure_cookies_enabled, session_secret
from app.database import Base, engine
from app.routes import admin, auth, public
from app.templating import BASE_DIR


def auto_create_tables_enabled() -> bool:
    if os.environ.get("BATTLE_MARCH_AUTO_CREATE_TABLES") is not None:
        return os.environ["BATTLE_MARCH_AUTO_CREATE_TABLES"].lower() in {"1", "true", "yes", "on"}
    return os.environ.get("BATTLE_MARCH_ENV") != "production"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if auto_create_tables_enabled():
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Battle March", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="battle_march_session",
    same_site="lax",
    https_only=secure_cookies_enabled(),
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(admin.router)
