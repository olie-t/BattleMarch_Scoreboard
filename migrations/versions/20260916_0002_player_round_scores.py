"""add player round scores

Revision ID: 20260916_0002
Revises: 20260916_0001
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = "20260916_0002"
down_revision = "20260916_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_round_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("is_bye", sa.Boolean(), nullable=False),
        sa.Column("painting_progress", sa.Boolean(), nullable=False),
        sa.Column("fully_painted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "round_id"),
    )


def downgrade() -> None:
    op.drop_table("player_round_scores")