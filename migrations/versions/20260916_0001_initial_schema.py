"""initial schema

Revision ID: 20260916_0001
Revises:
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = "20260916_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("points_limit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "army_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("faction", sa.String(length=100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("player_one_id", sa.Integer(), nullable=False),
        sa.Column("player_two_id", sa.Integer(), nullable=False),
        sa.Column("player_one_score", sa.Integer(), nullable=True),
        sa.Column("player_two_score", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["player_one_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["player_two_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("army_lists")
    op.drop_table("rounds")
    op.drop_table("players")
    op.drop_table("leagues")
