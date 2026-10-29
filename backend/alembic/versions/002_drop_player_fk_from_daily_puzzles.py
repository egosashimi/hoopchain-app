"""Drop FK constraints from daily_puzzles to players table

The players table is not populated from ETL data; player info comes from
the graph. Keeping FKs on start/end_player_id blocks the seeder from
inserting puzzles.

Revision ID: 002_drop_player_fk_from_daily_puzzles
Revises: 001_initial_schema
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op

revision = "002"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop ALL FK constraints on daily_puzzles by querying the catalog —
    # avoids hardcoding auto-generated constraint names that vary by DB.
    op.execute("""
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'daily_puzzles'
                  AND constraint_type = 'FOREIGN KEY'
            LOOP
                EXECUTE 'ALTER TABLE daily_puzzles DROP CONSTRAINT ' || quote_ident(r.constraint_name);
            END LOOP;
        END $$
    """)


def downgrade() -> None:
    op.create_foreign_key(
        None,
        "daily_puzzles",
        "players",
        ["start_player_id"],
        ["id"],
    )
    op.create_foreign_key(
        None,
        "daily_puzzles",
        "players",
        ["end_player_id"],
        ["id"],
    )
