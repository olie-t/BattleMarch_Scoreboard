import os

from app.database import Base, SessionLocal, engine
from app.models import League, Match, Player, Round


def reset_database() -> None:
    if os.environ.get("BATTLE_MARCH_ENV") == "production":
        raise RuntimeError("Refusing to reset the database when BATTLE_MARCH_ENV=production.")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_database() -> None:
    reset_database()

    with SessionLocal() as db:
        league = League(name="The March of Eight Banners")
        players = [
            Player(name="Alys Emberfall", league=league),
            Player(name="Borin Oakshield", league=league),
            Player(name="Celia Thorn", league=league),
            Player(name="Darius Vale", league=league),
            Player(name="Elara Moonbrook", league=league),
            Player(name="Finn Ironmark", league=league),
            Player(name="Gwen Hearthward", league=league),
            Player(name="Hugo Redwyne", league=league),
        ]
        rounds = [
            Round(number=1, points_limit=1000, league=league),
            Round(number=2, points_limit=1250, league=league),
            Round(number=3, points_limit=1500, league=league),
        ]

        db.add(league)
        db.flush()

        matches = [
            Match(
                round=rounds[0],
                player_one=players[0],
                player_two=players[1],
                player_one_score=15,
                player_two_score=5,
            ),
            Match(
                round=rounds[0],
                player_one=players[2],
                player_two=players[3],
                player_one_score=10,
                player_two_score=10,
            ),
            Match(
                round=rounds[0],
                player_one=players[4],
                player_two=players[5],
            ),
            Match(
                round=rounds[1],
                player_one=players[0],
                player_two=players[2],
                player_one_score=8,
                player_two_score=12,
            ),
            Match(
                round=rounds[1],
                player_one=players[1],
                player_two=players[4],
            ),
            Match(
                round=rounds[2],
                player_one=players[3],
                player_two=players[5],
                player_one_score=14,
                player_two_score=6,
            ),
        ]

        db.add_all(rounds + matches)
        db.commit()

        print("Seeded 1 league, 8 players, 3 rounds, and 6 matches.")
        print("Pending matches have NULL scores; no army lists were created.")


if __name__ == "__main__":
    seed_database()