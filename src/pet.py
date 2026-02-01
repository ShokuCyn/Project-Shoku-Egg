from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random


@dataclass
class PetState:
    guild_id: int
    name: str
    hunger: int
    happiness: int
    day_index: int
    love_today: int
    last_love_date: str
    feeds_today: int
    last_feed_date: str
    dead_until: str | None
    updated_at: datetime

    LOVE_THRESHOLD = 3
    FEED_THRESHOLD = 1

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def apply_decay(self, now: datetime | None = None) -> None:
        current = now or self.now()
        if self.is_dead(current):
            return
        if self.check_revive(current):
            return
        current_date = current.date().isoformat()
        if self.last_love_date != current_date or self.last_feed_date != current_date:
            self.advance_day(current_date)
        elapsed_seconds = max(0, int((current - self.updated_at).total_seconds()))
        if elapsed_seconds == 0:
            return

        hunger_increase = elapsed_seconds // 300
        happiness_decrease = elapsed_seconds // 600
        if hunger_increase:
            self.hunger = min(100, self.hunger + hunger_increase)
        if happiness_decrease:
            self.happiness = max(0, self.happiness - happiness_decrease)
        self.updated_at = current

    def feed(self, amount: int = 15) -> None:
        self.hunger = max(0, self.hunger - amount)
        self.add_love()
        self.add_feed()

    def play(self, amount: int = 10) -> None:
        self.happiness = min(100, self.happiness + amount)
        self.add_love()

    def evolution_stage(self) -> str:
        if self.day_index == 0:
            return "Egg"
        return f"Day {self.day_index}"

    def sprite_key(self) -> str:
        if self.day_index == 0:
            return "egg"
        return f"day{self.day_index}_{self.evolution_path().lower()}"

    def evolution_path(self) -> str:
        if self.day_index == 0:
            return "N/A"
        return "Good" if self.love_today >= self.LOVE_THRESHOLD else "Bad"

    def evolution_title(self) -> str:
        if self.day_index == 0:
            return "Egg"
        return f"{self.evolution_stage()} ({self.evolution_path()})"

    def add_love(self, amount: int = 1) -> None:
        self.love_today += amount
        self.last_love_date = self.now().date().isoformat()

    def add_feed(self, amount: int = 1) -> None:
        self.feeds_today += amount
        self.last_feed_date = self.now().date().isoformat()

    def advance_day(self, current_date: str) -> None:
        if self.day_index != 0 and self.feeds_today < self.FEED_THRESHOLD:
            self.dead_until = (self.now() + timedelta(hours=1)).isoformat()
            self.day_index = 0
            self.love_today = 0
            self.feeds_today = 0
            self.last_love_date = current_date
            self.last_feed_date = current_date
            return
        if self.day_index >= 6:
            self.day_index = 0
        else:
            self.day_index += 1
        self.love_today = 0
        self.feeds_today = 0
        self.last_love_date = current_date
        self.last_feed_date = current_date

    def is_dead(self, now: datetime | None = None) -> bool:
        if not self.dead_until:
            return False
        current = now or self.now()
        return current < datetime.fromisoformat(self.dead_until)

    def check_revive(self, now: datetime | None = None) -> bool:
        if not self.dead_until:
            return False
        current = now or self.now()
        if current < datetime.fromisoformat(self.dead_until):
            return False
        self.dead_until = None
        self.day_index = 0
        self.love_today = 0
        self.feeds_today = 0
        current_date = current.date().isoformat()
        self.last_love_date = current_date
        self.last_feed_date = current_date
        return True

    def say_line(self) -> str:
        lines = [
            "Zzz... snuggly snooze mode!",
            "I found a shiny pebble!",
            "Do you think I can fly today?",
            "I love head pats.",
            "Beep boop! Snack please.",
            "Let's go on an adventure!",
            "I'm rooting for you!",
        ]
        return random.choice(lines)
