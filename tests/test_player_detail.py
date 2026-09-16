import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.army_list_import import import_army_list
from app.database import SessionLocal
from app.main import app
from app.models import Player, Round
from scripts.seed import seed_database
from tests.test_army_list_import import VALID_EXPORT


def test_player_detail_links_to_imported_army_list() -> None:
    seed_database()
    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.name == "Alys Emberfall"))
        round_item = db.scalar(select(Round).where(Round.number == 1))
        army_list = import_army_list(
            db,
            player_id=player.id,
            round_id=round_item.id,
            json_text=json.dumps(VALID_EXPORT),
        )
        player_id = player.id
        army_list_id = army_list.id
        army_list_name = army_list.name

    response = TestClient(app).get(f"/players/{player_id}")

    assert response.status_code == 200
    assert army_list_name in response.text
    assert f'href="/army-lists/{army_list_id}"' in response.text