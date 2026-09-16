from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ArmyList, League, Match, Player, Round


engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)

with Session(engine) as db:
    league = League(name="Battle March Test League")
    first_player = Player(name="Alys", league=league)
    second_player = Player(name="Borin", league=league)
    first_round = Round(number=1, points_limit=1000, league=league)
    army_list = ArmyList(
        player=first_player,
        round=first_round,
        name="Alys 1,000 Point List",
        points=1000,
        faction="Bretonnia",
        data={"source": "old-world-builder", "units": []},
    )
    match = Match(
        round=first_round,
        player_one=first_player,
        player_two=second_player,
        player_one_score=12,
        player_two_score=8,
    )

    db.add(league)
    db.commit()

    saved_league = db.scalar(
        select(League).where(League.name == "Battle March Test League")
    )
    assert saved_league is not None
    assert {player.name for player in saved_league.players} == {"Alys", "Borin"}
    assert saved_league.rounds[0].matches[0].player_one.name == "Alys"
    assert saved_league.rounds[0].matches[0].player_two.name == "Borin"
    assert saved_league.rounds[0].matches[0].player_one_score == 12
    assert saved_league.players[0].army_lists[0].data["source"] == "old-world-builder"

print("Relationship example passed")
