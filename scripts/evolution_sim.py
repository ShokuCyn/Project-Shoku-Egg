from datetime import datetime, timedelta, timezone

from src.pet import PetState


def simulate(days: int) -> PetState:
    now = datetime.now(timezone.utc)
    pet = PetState(
        guild_id=1,
        name="Unnamed Mascot",
        hunger=100,
        happiness=100,
        day_index=0,
        love_today=0,
        last_love_date=now.date().isoformat(),
        feeds_today=0,
        last_feed_date=now.date().isoformat(),
        dead_until=None,
        hygiene=100,
        last_words="",
        last_caretaker_id=None,
        sleep_hours=10,
        form="egg",
        born_at=now - timedelta(days=days),
        last_evolution_checkpoint=0,
        updated_at=now,
    )
    pet.maybe_evolve(now)
    return pet


def main() -> None:
    for days in (0, 1, 3, 6):
        pet = simulate(days)
        print(f"day {days}: form={pet.form} checkpoint={pet.last_evolution_checkpoint}")


if __name__ == "__main__":
    main()
