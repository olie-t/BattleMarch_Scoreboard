from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import League


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def nav_leagues() -> list[League]:
	try:
		with SessionLocal() as db:
			return list(db.scalars(select(League).order_by(League.name)))
	except SQLAlchemyError:
		return []


templates.env.globals["nav_leagues"] = nav_leagues
