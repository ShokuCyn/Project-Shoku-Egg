from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import random


class DecayResult(NamedTuple):
    died: bool
    hatched: bool


EVOLUTION_CONFIG = {
    "checkpoints": (1, 3, 6),
    "day1_form": "day1",
    "day3_forms": {
        "good": "day3_good",
        "medium": "day3_medium",
        "bad": "day3_bad",
    },
    "day6_forms": {
        "very_good": "day6_very_good",
        "good": "day6_good",
        "medium": "day6_medium",
        "bad": "day6_bad",
        "very_bad": "day6_very_bad",
    },
    "tier_thresholds": [
        ("very_good", 90, 100),
        ("good", 70, 89),
        ("medium", 45, 69),
        ("bad", 20, 44),
        ("very_bad", 0, 19),
    ],
    "day3_clamp": {
        "very_good": "good",
        "very_bad": "bad",
    },
}


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
    hygiene: int
    last_words: str
    last_caretaker_id: int | None
    sleep_hours: int
    form: str
    born_at: datetime
    last_evolution_checkpoint: int
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
        hatched = self.maybe_evolve(current)
        if self.form == "egg":
            self.updated_at = current
            return DecayResult(False, hatched)
        if self.last_love_date != current_date or self.last_feed_date != current_date:
            if self.advance_day(current_date):
                self.updated_at = current
                return DecayResult(True, hatched)
        elapsed_seconds = max(0, int((current - self.updated_at).total_seconds()))
        if elapsed_seconds == 0:
            return DecayResult(False, hatched)

        decay_multiplier = 2 if self._is_sleep_window(current) else 1
        hunger_decrease = elapsed_seconds // 120
        happiness_decrease = elapsed_seconds // 240
        if hunger_decrease:
            self.hunger = max(0, self.hunger - (hunger_decrease * decay_multiplier))
        if happiness_decrease:
            self.happiness = max(0, self.happiness - (happiness_decrease * decay_multiplier))
        hygiene_decrease = elapsed_seconds // 600
        if hygiene_decrease:
            self.hygiene = max(0, self.hygiene - (hygiene_decrease * decay_multiplier))
        sleep_decrease = elapsed_seconds // 1800
        if sleep_decrease:
            self.sleep_hours = max(0, self.sleep_hours - (sleep_decrease * decay_multiplier))
        if self.name.strip() == "" or self.name == "Unnamed Mascot":
            unnamed_penalty = elapsed_seconds // 600
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
        return DecayResult(False, hatched)

    def feed(self, amount: int = 15) -> None:
        self.hunger = min(100, self.hunger + amount)
        self.add_love()
        self.add_feed()

    def play(self, amount: int = 10) -> None:
        self.happiness = min(100, self.happiness + amount)
        self.add_love()

    def evolution_stage(self) -> str:
        return self.form

    def sprite_key(self) -> str:
        return self.form

    def evolution_path(self) -> str:
        return "N/A"

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

    def advance_day(self, current_date: str) -> bool:
        if self.last_evolution_checkpoint > 1 and self.feeds_today < self.FEED_THRESHOLD:
            self.dead_until = (self.now() + timedelta(hours=1)).isoformat()
            self.last_words = self.build_last_words()
            self.day_index = 0
            self.love_today = 0
            self.feeds_today = 0
            self.last_love_date = current_date
            self.last_feed_date = current_date
            return True
        if self.day_index < 6:
            self.day_index += 1
        self.love_today = 0
        self.feeds_today = 0
        self.last_love_date = current_date
        self.last_feed_date = current_date
        return False

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
        self.hygiene = 100
        self.last_words = ""
        self.sleep_hours = 10
        current_date = current.date().isoformat()
        self.last_love_date = current_date
        self.last_feed_date = current_date
        return True

    def clean(self) -> None:
        self.hygiene = min(100, self.hygiene + 20)

    def build_last_words(self) -> str:
        return (
            f"I reached {self.form}, felt {self.happiness}/100 happy, "
            f"had {self.hunger}/100 hunger, slept {self.sleep_hours}/10 hours, "
            f"and had {self.hygiene}/100 hygiene."
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
        mood = self._current_mood()
        desire = self._current_desire()
        statements = [
            f"I'm feeling {mood} and {desire}.",
            f"Kind of {mood} today—{desire}.",
            f"{mood.capitalize()} vibes... {desire}.",
        ]
        return random.choice(statements)

    def _current_mood(self) -> str:
        moods = []
        if self.hunger < 30:
            moods.append("hungry")
        if self.sleep_hours < 4:
            moods.append("sleepy")
        if self.happiness < 30:
            moods.append("sad")
        if self.happiness > 80:
            moods.append("happy")
        if self.hygiene < 30:
            moods.append("irritated")
        if not moods:
            moods = ["content", "calm", "relaxed", "curious"]
        return random.choice(moods)

    def _current_desire(self) -> str:
        desires = []
        if self.hunger < 30:
            desires.append("wanting food")
        if self.sleep_hours < 4:
            desires.append("wanting rest")
        if self.happiness < 30:
            desires.append("needing attention")
        if self.happiness > 80:
            desires.append("feeling playful")
        if self.hygiene < 30:
            desires.append("seeking cleanup")
        if not desires:
            desires = ["curious", "wanting snuggles", "feeling independent"]
        return random.choice(desires)

    def maybe_evolve(self, now: datetime) -> bool:
        age_days = max(0, (now.date() - self.born_at.date()).days)
        checkpoints = EVOLUTION_CONFIG["checkpoints"]
        checkpoint = max((c for c in checkpoints if age_days >= c), default=0)
        if checkpoint <= self.last_evolution_checkpoint:
            return False
        if checkpoint == 1:
            self.form = EVOLUTION_CONFIG["day1_form"]
        elif checkpoint == 3:
            tier = self._score_tier()
            tier = EVOLUTION_CONFIG["day3_clamp"].get(tier, tier)
            self.form = EVOLUTION_CONFIG["day3_forms"][tier]
        elif checkpoint == 6:
            tier = self._score_tier()
            self.form = EVOLUTION_CONFIG["day6_forms"][tier]
        self.last_evolution_checkpoint = checkpoint
        self.day_index = checkpoint
        return checkpoint == 1

    def _score_tier(self) -> str:
        care_score = self._care_score()
        for tier, low, high in EVOLUTION_CONFIG["tier_thresholds"]:
            if low <= care_score <= high:
                return tier
        return "very_bad"

    def _care_score(self) -> int:
        hunger = self._normalize_stat(self.hunger)
        happiness = self._normalize_stat(self.happiness)
        sleep = self._normalize_stat(self.sleep_hours * 10)
        hygiene = self._normalize_stat(self.hygiene)
        return round(
            0.30 * hunger
            + 0.25 * happiness
            + 0.25 * sleep
            + 0.20 * hygiene
        )

    @staticmethod
    def _normalize_stat(value: int) -> int:
        return max(0, min(100, value))
