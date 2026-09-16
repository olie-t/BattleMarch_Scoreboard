from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    players: Mapped[List["Player"]] = relationship(back_populates="league")
    rounds: Mapped[List["Round"]] = relationship(back_populates="league")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(100))

    league: Mapped[League] = relationship(back_populates="players")
    army_lists: Mapped[List["ArmyList"]] = relationship(back_populates="player")
    round_scores: Mapped[List["PlayerRoundScore"]] = relationship(back_populates="player")
    matches_as_player_one: Mapped[List["Match"]] = relationship(
        foreign_keys="Match.player_one_id",
        back_populates="player_one",
    )
    matches_as_player_two: Mapped[List["Match"]] = relationship(
        foreign_keys="Match.player_two_id",
        back_populates="player_two",
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    number: Mapped[int] = mapped_column(Integer)
    points_limit: Mapped[int] = mapped_column(Integer)

    league: Mapped[League] = relationship(back_populates="rounds")
    matches: Mapped[List["Match"]] = relationship(back_populates="round")
    army_lists: Mapped[List["ArmyList"]] = relationship(back_populates="round")
    player_scores: Mapped[List["PlayerRoundScore"]] = relationship(back_populates="round")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    player_one_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    player_two_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    player_one_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    player_two_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    round: Mapped[Round] = relationship(back_populates="matches")
    player_one: Mapped[Player] = relationship(
        foreign_keys=[player_one_id],
        back_populates="matches_as_player_one",
    )
    player_two: Mapped[Player] = relationship(
        foreign_keys=[player_two_id],
        back_populates="matches_as_player_two",
    )


class ArmyList(Base):
    __tablename__ = "army_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    name: Mapped[str] = mapped_column(String(100))
    points: Mapped[int] = mapped_column(Integer)
    faction: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    player: Mapped[Player] = relationship(back_populates="army_lists")
    round: Mapped[Round] = relationship(back_populates="army_lists")


class PlayerRoundScore(Base):
    __tablename__ = "player_round_scores"
    __table_args__ = (UniqueConstraint("player_id", "round_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    is_bye: Mapped[bool] = mapped_column(Boolean, default=False)
    painting_progress: Mapped[bool] = mapped_column(Boolean, default=False)
    fully_painted: Mapped[bool] = mapped_column(Boolean, default=False)

    player: Mapped[Player] = relationship(back_populates="round_scores")
    round: Mapped[Round] = relationship(back_populates="player_scores")
