from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import random


class DecayResult(NamedTuple):
    died: bool
    hatched: bool


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
    poop_count: int
    last_words: str
    last_caretaker_id: int | None
    sleep_hours: int
    updated_at: datetime

    LOVE_THRESHOLD = 3
    FEED_THRESHOLD = 1

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def apply_decay(self, now: datetime | None = None) -> DecayResult:
        current = now or self.now()
        if self.is_dead(current):
            return DecayResult(False, False)
        if self.check_revive(current):
            return DecayResult(False, False)
        current_date = current.date().isoformat()
        if self.last_love_date != current_date or self.last_feed_date != current_date:
            died, hatched = self.advance_day(current_date)
            if died:
                self.updated_at = current
                return DecayResult(True, hatched)
            if hatched:
                self.updated_at = current
                return DecayResult(False, True)
        if self.day_index == 0:
            self.updated_at = current
            return DecayResult(False, False)
        elapsed_seconds = max(0, int((current - self.updated_at).total_seconds()))
        if elapsed_seconds == 0:
            return DecayResult(False, False)

        decay_multiplier = 2 if self._is_sleep_window(current) else 1
        hunger_decrease = elapsed_seconds // 300
        happiness_decrease = elapsed_seconds // 600
        poop_increase = elapsed_seconds // 1800
        if hunger_decrease:
            self.hunger = max(0, self.hunger - (hunger_decrease * decay_multiplier))
        if happiness_decrease:
            self.happiness = max(0, self.happiness - (happiness_decrease * decay_multiplier))
        if poop_increase:
            self.poop_count = min(5, self.poop_count + poop_increase)
        sleep_decrease = elapsed_seconds // 3600
        if sleep_decrease:
            self.sleep_hours = max(0, self.sleep_hours - (sleep_decrease * decay_multiplier))
        if self.poop_count > 0:
            poop_penalty = (elapsed_seconds // 120) * self.poop_count
            if poop_penalty:
                self.happiness = max(0, self.happiness - poop_penalty)
        if self.name.strip() == "" or self.name == "Unnamed Mascot":
            unnamed_penalty = elapsed_seconds // 900
            if unnamed_penalty:
                self.happiness = max(0, self.happiness - (unnamed_penalty * decay_multiplier))
        self.updated_at = current
        if self.hunger == 0 or self.happiness == 0 or self.sleep_hours == 0:
            self.dead_until = (self.now() + timedelta(hours=1)).isoformat()
            self.last_words = self.build_last_words()
            self.day_index = 0
            self.love_today = 0
            self.feeds_today = 0
            self.last_love_date = current_date
            self.last_feed_date = current_date
            return DecayResult(True, False)
        return DecayResult(False, False)

    def feed(self, amount: int = 15) -> None:
        self.hunger = min(100, self.hunger + amount)
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

    def advance_day(self, current_date: str) -> tuple[bool, bool]:
        if self.day_index != 0 and self.feeds_today < self.FEED_THRESHOLD:
            self.dead_until = (self.now() + timedelta(hours=1)).isoformat()
            self.last_words = self.build_last_words()
            self.day_index = 0
            self.love_today = 0
            self.feeds_today = 0
            self.last_love_date = current_date
            self.last_feed_date = current_date
            return True, False
        hatched = False
        if self.day_index < 6:
            self.day_index += 1
            if self.day_index == 1:
                hatched = True
        self.love_today = 0
        self.feeds_today = 0
        self.last_love_date = current_date
        self.last_feed_date = current_date
        return False, hatched

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
        self.poop_count = 0
        self.last_words = ""
        self.sleep_hours = 10
        current_date = current.date().isoformat()
        self.last_love_date = current_date
        self.last_feed_date = current_date
        return True

    def clean(self) -> None:
        if self.poop_count > 0:
            self.poop_count = 0
            self.happiness = min(100, self.happiness + 10)

    def build_last_words(self) -> str:
        stage = self.evolution_stage()
        poop_note = "surrounded by poop" if self.poop_count > 0 else "in a clean nest"
        return (
            f"I reached {stage}, felt {self.happiness}/100 happy, "
            f"had {self.hunger}/100 hunger, slept {self.sleep_hours}/10 hours, "
            f"and was {poop_note}."
        )

    @staticmethod
    def _is_sleep_window(now: datetime) -> bool:
        try:
            local = now.astimezone(ZoneInfo("America/Toronto"))
        except ZoneInfoNotFoundError:
            local = now.astimezone(timezone.utc)
        hour = local.hour
        return hour >= 22 or hour < 8

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
