from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import League, Player, Round


client = TestClient(app)


def test_public_league_pages_filter_by_league() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        old_world = League(name="Old World Battle March")
        combat_patrol = League(name="40k Combat Patrol")
        db.add_all([old_world, combat_patrol])
        db.flush()
        old_world_id = old_world.id
        combat_patrol_id = combat_patrol.id
        db.add(Player(name="Alys Emberfall", league_id=old_world_id))
        db.add(Player(name="Brother Cassian", league_id=combat_patrol_id))
        db.add(Round(number=1, points_limit=1000, league_id=old_world_id))
        db.add(Round(number=1, points_limit=500, league_id=combat_patrol_id))
        db.commit()

    leagues_response = client.get("/leagues")
    assert leagues_response.status_code == 200
    assert "Old World Battle March" in leagues_response.text
    assert "40k Combat Patrol" in leagues_response.text
    assert f'href="/leagues/{old_world_id}/players"' in leagues_response.text
    assert f'href="/leagues/{old_world_id}/rounds"' in leagues_response.text
    assert f'href="/leagues/{combat_patrol_id}/players"' in leagues_response.text
    assert f'href="/leagues/{combat_patrol_id}/rounds"' in leagues_response.text

    old_world_response = client.get(f"/leagues/{old_world_id}/players")
    assert old_world_response.status_code == 200
    assert "Alys Emberfall" in old_world_response.text
    assert "Brother Cassian" not in old_world_response.text

    combat_patrol_response = client.get(f"/leagues/{combat_patrol_id}/rounds")
    assert combat_patrol_response.status_code == 200
    assert "500 points" in combat_patrol_response.text
    assert "1000 points" not in combat_patrol_response.text
