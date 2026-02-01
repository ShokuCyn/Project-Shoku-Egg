from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .pet import PetState


class PetStore:
    def __init__(self, db_path: str | Path = "pet_store.sqlite") -> None:
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pets (
                guild_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                exp INTEGER NOT NULL,
                hunger INTEGER NOT NULL,
                happiness INTEGER NOT NULL,
                day_index INTEGER NOT NULL,
                love_today INTEGER NOT NULL,
                last_love_date TEXT NOT NULL,
                feeds_today INTEGER NOT NULL,
                last_feed_date TEXT NOT NULL,
                dead_until TEXT,
                poop_count INTEGER NOT NULL,
                last_words TEXT NOT NULL,
                last_caretaker_id INTEGER,
                sleep_hours INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS caretaker_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                feeds INTEGER NOT NULL,
                plays INTEGER NOT NULL,
                last_reset TEXT NOT NULL,
                last_interaction TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS death_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                deaths INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        self.connection.commit()
        self._ensure_pet_columns()

    def _ensure_pet_columns(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(pets)")
        existing = {row["name"] for row in cursor.fetchall()}
        columns = {
            "day_index": "INTEGER NOT NULL DEFAULT 0",
            "love_today": "INTEGER NOT NULL DEFAULT 0",
            "last_love_date": "TEXT NOT NULL DEFAULT ''",
            "feeds_today": "INTEGER NOT NULL DEFAULT 0",
            "last_feed_date": "TEXT NOT NULL DEFAULT ''",
            "dead_until": "TEXT",
            "poop_count": "INTEGER NOT NULL DEFAULT 0",
            "last_words": "TEXT NOT NULL DEFAULT ''",
            "last_caretaker_id": "INTEGER",
            "sleep_hours": "INTEGER NOT NULL DEFAULT 10",
        }
        for column, definition in columns.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE pets ADD COLUMN {column} {definition}")
        self.connection.commit()
        cursor.execute("PRAGMA table_info(caretaker_stats)")
        existing_caretakers = {row["name"] for row in cursor.fetchall()}
        if "last_interaction" not in existing_caretakers:
            cursor.execute(
                "ALTER TABLE caretaker_stats ADD COLUMN last_interaction TEXT NOT NULL DEFAULT ''"
            )
        self.connection.commit()

    def get_or_create(self, guild_id: int) -> PetState:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM pets WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        if row:
            pet = self._row_to_pet(row)
            result = pet.apply_decay()
            if result.died:
                self.record_death(guild_id, pet.last_caretaker_id)
            self.save(pet)
            return pet

        pet = PetState(
            guild_id=guild_id,
            name="Unnamed Mascot",
            hunger=100,
            happiness=80,
            day_index=0,
            love_today=0,
            last_love_date=self._today(),
            feeds_today=0,
            last_feed_date=self._today(),
            dead_until=None,
            poop_count=0,
            last_words="",
            last_caretaker_id=None,
            sleep_hours=10,
            updated_at=self._now(),
        )
        self.save(pet)
        return pet

    def save(self, pet: PetState) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO pets (
                guild_id,
                name,
                level,
                exp,
                hunger,
                happiness,
                day_index,
                love_today,
                last_love_date,
                feeds_today,
                last_feed_date,
                dead_until,
                poop_count,
                last_words,
                last_caretaker_id,
                sleep_hours,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                name=excluded.name,
                level=excluded.level,
                exp=excluded.exp,
                hunger=excluded.hunger,
                happiness=excluded.happiness,
                day_index=excluded.day_index,
                love_today=excluded.love_today,
                last_love_date=excluded.last_love_date,
                feeds_today=excluded.feeds_today,
                last_feed_date=excluded.last_feed_date,
                dead_until=excluded.dead_until,
                poop_count=excluded.poop_count,
                last_words=excluded.last_words,
                last_caretaker_id=excluded.last_caretaker_id,
                sleep_hours=excluded.sleep_hours,
                updated_at=excluded.updated_at
            """,
            (
                pet.guild_id,
                pet.name,
                pet.day_index,
                0,
                pet.hunger,
                pet.happiness,
                pet.day_index,
                pet.love_today,
                pet.last_love_date,
                pet.feeds_today,
                pet.last_feed_date,
                pet.dead_until,
                pet.poop_count,
                pet.last_words,
                pet.last_caretaker_id,
                pet.sleep_hours,
                pet.updated_at.isoformat(),
            ),
        )
        self.connection.commit()

    def list_all(self) -> list[PetState]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM pets")
        rows = cursor.fetchall()
        return [self._row_to_pet(row) for row in rows]

    def record_care_action(self, guild_id: int, user_id: int, action: str) -> None:
        if action not in {"feed", "play"}:
            raise ValueError("action must be 'feed' or 'play'")
        today = self._today()
        now = self._now().isoformat()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT feeds, plays, last_reset, last_interaction
            FROM caretaker_stats
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        row = cursor.fetchone()
        if row:
            feeds = row["feeds"]
            plays = row["plays"]
            last_reset = row["last_reset"]
            last_interaction = row["last_interaction"]
        else:
            feeds = 0
            plays = 0
            last_reset = today
            last_interaction = now

        if last_reset != today:
            feeds = 0
            plays = 0
            last_reset = today

        if action == "feed":
            feeds += 1
        else:
            plays += 1

        cursor.execute(
            """
            INSERT INTO caretaker_stats (
                guild_id,
                user_id,
                feeds,
                plays,
                last_reset,
                last_interaction
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                feeds=excluded.feeds,
                plays=excluded.plays,
                last_reset=excluded.last_reset,
                last_interaction=excluded.last_interaction
            """,
            (guild_id, user_id, feeds, plays, last_reset, now),
        )
        self.connection.commit()

    def reset_daily_caretakers(self) -> None:
        today = self._today()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE caretaker_stats
            SET feeds = 0, plays = 0, last_reset = ?
            WHERE last_reset != ?
            """,
            (today, today),
        )
        self.connection.commit()

    def top_caretakers(self, guild_id: int, limit: int = 5) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT user_id, feeds, plays, (feeds + plays) AS total
            FROM caretaker_stats
            WHERE guild_id = ?
            ORDER BY total DESC, feeds DESC, plays DESC, user_id ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return cursor.fetchall()

    def record_death(self, guild_id: int, user_id: int | None) -> None:
        killer_id = user_id or 0
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO death_stats (guild_id, user_id, deaths)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                deaths = deaths + 1
            """,
            (guild_id, killer_id),
        )
        self.connection.commit()

    def top_killers(self, guild_id: int, limit: int = 5) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT user_id, deaths
            FROM death_stats
            WHERE guild_id = ?
            ORDER BY deaths DESC, user_id ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return cursor.fetchall()

    def inactive_caretakers(
        self, guild_id: int, cutoff: datetime, limit: int = 5
    ) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT user_id, last_interaction
            FROM caretaker_stats
            WHERE guild_id = ? AND last_interaction != '' AND last_interaction < ?
            ORDER BY last_interaction ASC
            LIMIT ?
            """,
            (guild_id, cutoff.isoformat(), limit),
        )
        return cursor.fetchall()

    def _row_to_pet(self, row: sqlite3.Row) -> PetState:
        return PetState(
            guild_id=row["guild_id"],
            name=row["name"],
            hunger=row["hunger"],
            happiness=row["happiness"],
            day_index=row["day_index"],
            love_today=row["love_today"],
            last_love_date=row["last_love_date"],
            feeds_today=row["feeds_today"],
            last_feed_date=row["last_feed_date"],
            dead_until=row["dead_until"],
            poop_count=row["poop_count"],
            last_words=row["last_words"],
            last_caretaker_id=row["last_caretaker_id"],
            sleep_hours=row["sleep_hours"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()
