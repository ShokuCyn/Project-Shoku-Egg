from __future__ import annotations

import os
from dataclasses import asdict
import datetime
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv

from .pet_store import PetStore


def _message_content_enabled() -> bool:
    return os.getenv("DISCORD_MESSAGE_CONTENT", "0").strip() in {"1", "true", "True", "yes"}


def build_sprite_urls() -> dict[str, str]:
    return {
        "egg": "https://placehold.co/256x256/gif?text=Egg",
        "day1": "https://placehold.co/256x256/gif?text=Day+1",
        "day3_good": "https://placehold.co/256x256/gif?text=Day+3+Good",
        "day3_medium": "https://placehold.co/256x256/gif?text=Day+3+Medium",
        "day3_bad": "https://placehold.co/256x256/gif?text=Day+3+Bad",
        "day6_very_good": "https://placehold.co/256x256/gif?text=Day+6+Very+Good",
        "day6_good": "https://placehold.co/256x256/gif?text=Day+6+Good",
        "day6_medium": "https://placehold.co/256x256/gif?text=Day+6+Medium",
        "day6_bad": "https://placehold.co/256x256/gif?text=Day+6+Bad",
        "day6_very_bad": "https://placehold.co/256x256/gif?text=Day+6+Very+Bad",
        "gravestone": "https://placehold.co/256x256/gif?text=Gravestone",
    }


SPRITE_URLS = build_sprite_urls()
SPRITE_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites"

POSITIVE_TRIGGERS = {
    "good egg",
    "best egg",
    "shoku",
    "so cute",
    "i love you",
    "great job",
}
NEGATIVE_TRIGGERS = {
    "accountability",
    "actionable",
    "actually",
    "aesthetic",
    "alignment",
    "announcement",
    "assume",
    "authentic",
    "bad egg",
    "bandwidth",
    "based",
    "basically",
    "bestie",
    "boundary",
    "capacity",
    "circleback",
    "coded",
    "codedly",
    "consent",
    "context",
    "cope",
    "cringe",
    "delusional",
    "deliverable",
    "discourse",
    "disruptive",
    "energy",
    "era",
    "era-coded",
    "everyone",
    "feedback",
    "feral",
    "framework",
    "gaslighting",
    "genuinely",
    "girlboss",
    "grind",
    "gross",
    "healing",
    "highkey",
    "holistic",
    "honestly",
    "hotfix",
    "hustle",
    "i hate you",
    "iconic",
    "impactful",
    "innovative",
    "intention",
    "invalid",
    "journey",
    "leverage",
    "literally",
    "lowkey",
    "manifest",
    "mid",
    "mindset",
    "modular",
    "narrative",
    "normalize",
    "nuance",
    "objectively",
    "online",
    "optimize",
    "parasocial",
    "patch",
    "period",
    "perspective",
    "ping",
    "pivot",
    "problematic",
    "process",
    "projection",
    "ratio",
    "reminder",
    "roadmap",
    "scalable",
    "season",
    "selfcare",
    "seethe",
    "simply",
    "slay",
    "stakeholder",
    "streamline",
    "subjectively",
    "sustainable",
    "synergy",
    "touchgrass",
    "toxic",
    "trauma",
    "transparent",
    "trigger",
    "unironically",
    "unpack",
    "unserious",
    "update",
    "valid",
    "vibes",
    "vibes-based",
    "wholesome",
    "yikes",
    "stinky",
    "go away",
}


class PetBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = _message_content_enabled()
        super().__init__(command_prefix="!", intents=intents)
        self.store = PetStore()

    async def setup_hook(self) -> None:
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.decay_loop.start()

    @tasks.loop(minutes=5)
    async def decay_loop(self) -> None:
        pets = self.store.list_all()
        if not pets:
            self.store.reset_daily_caretakers()
            return
        for pet in pets:
            previous_hygiene = pet.hygiene
            result = pet.apply_decay()
            just_pooped = pet.maybe_poop()
            self.store.save(pet)
            if just_pooped:
                await self._notify_mess(pet.guild_id)
            if previous_hygiene >= 60 > pet.hygiene:
                await self._notify_mess(pet.guild_id)
            if result.nap_started:
                await self._notify_nap(pet.guild_id, pet.name)
            if result.hatched:
                await self._notify_hatch(pet.guild_id, pet.name)
            if result.died:
                self.store.record_death(pet.guild_id, pet.last_caretaker_id)
                await self._notify_death(pet.guild_id, pet.last_words)
        self.store.reset_daily_caretakers()

    @decay_loop.before_loop
    async def before_decay_loop(self) -> None:
        await self.wait_until_ready()

    async def _notify_death(self, guild_id: int, last_words: str) -> None:
        guild = self.get_guild(guild_id)
        if not guild or not last_words:
            return
        channel = guild.system_channel
        if not channel:
            me = guild.me or guild.get_member(self.user.id) if self.user else None
            for candidate in guild.text_channels:
                if me and candidate.permissions_for(me).send_messages:
                    channel = candidate
                    break
        if channel:
            await channel.send(
                f"@everyone ☠️ {last_words}",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )

    async def _notify_mess(self, guild_id: int) -> None:
        guild = self.get_guild(guild_id)
        if not guild:
            return
        channel = guild.system_channel
        if not channel:
            me = guild.me or guild.get_member(self.user.id) if self.user else None
            for candidate in guild.text_channels:
                if me and candidate.permissions_for(me).send_messages:
                    channel = candidate
                    break
        if channel:
            await channel.send("💩 The nest needs cleaning!")

    def _cooldown_remaining(self, guild_id: int, user_id: int) -> datetime.timedelta:
        last_seen = self.store.last_interaction(guild_id, user_id)
        if not last_seen:
            return datetime.timedelta(0)
        elapsed = datetime.datetime.now(datetime.timezone.utc) - last_seen
        cooldown = datetime.timedelta(minutes=10)
        if elapsed >= cooldown:
            return datetime.timedelta(0)
        return cooldown - elapsed
    async def _notify_hatch(self, guild_id: int, name: str) -> None:
        guild = self.get_guild(guild_id)
        if not guild:
            return
        channel = guild.system_channel
        if not channel:
            me = guild.me or guild.get_member(self.user.id) if self.user else None
            for candidate in guild.text_channels:
                if me and candidate.permissions_for(me).send_messages:
                    channel = candidate
                    break
        if channel:
            await channel.send(
                f"🥚➡️✨ I just hatched! I'm {name}. Use `/pet rename <name>` to name me."
            )

    async def _notify_nap(self, guild_id: int, name: str) -> None:
        guild = self.get_guild(guild_id)
        if not guild:
            return
        channel = guild.system_channel
        if not channel:
            me = guild.me or guild.get_member(self.user.id) if self.user else None
            for candidate in guild.text_channels:
                if me and candidate.permissions_for(me).send_messages:
                    channel = candidate
                    break
        if channel:
            await channel.send(f"😴 {name} is taking a 1-hour nap.")

    def _sprite_file(self, form: str) -> Path | None:
        candidates = [
            SPRITE_DIR / f"{form}@1.5x.gif",
            SPRITE_DIR / f"{form}.gif",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        for pattern in (f"{form}@1.5x.gif", f"{form}.gif"):
            for match in SPRITE_DIR.rglob(pattern):
                return match
        return None


bot = PetBot()


@bot.event
async def on_ready() -> None:
    if bot.user:
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message) -> None:
    if not bot.intents.message_content:
        return
    if message.author.bot or not message.guild:
        return
    if message.content.startswith("/"):
        return
    content = message.content.lower()
    delta = 0
    if any(phrase in content for phrase in POSITIVE_TRIGGERS):
        delta += 5
    if any(phrase in content for phrase in NEGATIVE_TRIGGERS):
        delta -= 5
    if delta != 0:
        pet = bot.store.get_or_create(message.guild.id)
        pet.happiness = max(0, min(100, pet.happiness + delta))
        pet.last_caretaker_id = message.author.id
        bot.store.save(pet)
    await bot.process_commands(message)


class PetGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(name="pet", description="Interact with the server mascot")
        self.add_command(DevGroup())

    @app_commands.command(name="status", description="Check the mascot's status")
    async def status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.is_dead():
            embed = discord.Embed(title=f"{pet.name} is resting...")
            embed.description = "A pixel gravestone marks the spot. Check back in an hour."
            if pet.last_words:
                embed.add_field(name="Last Words", value=pet.last_words, inline=False)
            embed.add_field(name="Says", value="Zzz... zzz...", inline=False)
            sprite_path = bot._sprite_file("gravestone")
            if sprite_path:
                embed.set_image(url=f"attachment://{sprite_path.name}")
                await interaction.response.send_message(
                    embed=embed,
                    file=discord.File(sprite_path),
                )
            else:
                sprite_url = SPRITE_URLS.get("gravestone")
                if sprite_url:
                    embed.set_image(url=sprite_url)
                await interaction.response.send_message(embed=embed)
            return
        details = asdict(pet)
        embed = discord.Embed(title=pet.name)
        embed.add_field(name="Hunger (Fullness)", value=f"{pet.hunger}/100", inline=True)
        embed.add_field(name="Happiness", value=f"{pet.happiness}/100", inline=True)
        asleep = "Asleep" if pet.is_asleep(pet.now()) else "Awake"
        embed.add_field(name="Sleep", value=f"{pet.sleep_hours}/10 hours ({asleep})", inline=True)
        hygiene_display = f"{pet.hygiene}/100"
        if pet.pooped:
            hygiene_display = f"{hygiene_display} 💩"
        embed.add_field(name="Hygiene", value=hygiene_display, inline=True)
        name_candidates = [
            member.display_name
            for member in interaction.guild.members
            if not member.bot and member.display_name
        ][:12]
        says = pet.say_line(names=name_candidates)
        if says:
            embed.add_field(
                name="Says",
                value=says,
                inline=False,
            )
        sprite_path = bot._sprite_file(pet.sprite_key())
        if sprite_path:
            embed.set_image(url=f"attachment://{sprite_path.name}")
        else:
            sprite_url = SPRITE_URLS.get(pet.sprite_key())
            if sprite_url:
                embed.set_image(url=sprite_url)
        embed.set_footer(text=f"Last updated: {details['updated_at']}")
        cutoff = pet.now() - datetime.timedelta(days=7)
        inactive = bot.store.inactive_caretakers(interaction.guild.id, cutoff=cutoff, limit=5)
        content = None
        if inactive:
            mentions = " ".join(f"<@{row['user_id']}>" for row in inactive)
            content = f"{mentions} {pet.name} misses you! Come check in."
        if sprite_path:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                file=discord.File(sprite_path),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        else:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
            )

    @app_commands.command(name="feed", description="Feed the mascot")
    async def feed(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.is_asleep(pet.now()):
            pet.wake_for(30, pet.now())
            bot.store.save(pet)
        remaining = bot._cooldown_remaining(interaction.guild.id, interaction.user.id)
        if remaining:
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            await interaction.response.send_message(
                f"You're on cooldown. Try again in {minutes}m {seconds}s."
            )
            return
        if pet.is_dead():
            await interaction.response.send_message(
                f"{pet.name} is resting under a pixel gravestone. Check back in an hour."
            )
            return
        pet.feed()
        pet.last_caretaker_id = interaction.user.id
        bot.store.save(pet)
        bot.store.record_care_action(interaction.guild.id, interaction.user.id, "feed")
        await interaction.response.send_message(
            f"{pet.name} happily munches! Hunger is now {pet.hunger}/100."
        )

    @app_commands.command(name="play", description="Play with the mascot")
    async def play(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.is_asleep(pet.now()):
            pet.wake_for(30, pet.now())
            bot.store.save(pet)
        remaining = bot._cooldown_remaining(interaction.guild.id, interaction.user.id)
        if remaining:
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            await interaction.response.send_message(
                f"You're on cooldown. Try again in {minutes}m {seconds}s."
            )
            return
        if pet.is_dead():
            await interaction.response.send_message(
                f"{pet.name} is resting under a pixel gravestone. Check back in an hour."
            )
            return
        pet.play()
        pet.last_caretaker_id = interaction.user.id
        bot.store.save(pet)
        bot.store.record_care_action(interaction.guild.id, interaction.user.id, "play")
        await interaction.response.send_message(
            f"{pet.name} plays along! Happiness is now {pet.happiness}/100."
        )

    @app_commands.command(name="clean", description="Clean up after the mascot")
    async def clean(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.is_asleep(pet.now()):
            pet.wake_for(30, pet.now())
            bot.store.save(pet)
        remaining = bot._cooldown_remaining(interaction.guild.id, interaction.user.id)
        if remaining:
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            await interaction.response.send_message(
                f"You're on cooldown. Try again in {minutes}m {seconds}s."
            )
            return
        if pet.is_dead():
            await interaction.response.send_message(
                f"{pet.name} is resting under a pixel gravestone. Check back in an hour."
            )
            return
        pet.clean()
        pet.last_caretaker_id = interaction.user.id
        bot.store.save(pet)
        bot.store.record_care_action(interaction.guild.id, interaction.user.id, "clean")
        await interaction.response.send_message(
            f"All clean! {pet.name} looks refreshed."
        )

    @app_commands.command(name="rename", description="Rename the mascot")
    @app_commands.describe(name="The mascot's new name")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.name not in {"", "Unnamed Mascot"}:
            await interaction.response.send_message(
                "This mascot has already been named and cannot be renamed."
            )
            return
        cleaned = name.strip()[:32]
        if not cleaned:
            await interaction.response.send_message(
                "The mascot can stay unnamed, but a non-empty name is needed to rename it."
            )
            return
        pet.name = cleaned
        bot.store.save(pet)
        await interaction.response.send_message(f"Mascot renamed to {pet.name}.")

    @app_commands.command(name="leaderboard", description="Top caretakers for today")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        entries = bot.store.top_caretakers(interaction.guild.id, limit=5)
        if not entries:
            await interaction.response.send_message("No caretakers yet today.")
            return

        lines: list[str] = []
        for index, row in enumerate(entries, start=1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"<@{row['user_id']}>"
            lines.append(f"{index}. {name} — {row['total']} care actions")

        embed = discord.Embed(title="Top Caretakers (Today)")
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="killers", description="Who has ended the mascot's runs")
    async def killers(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        entries = bot.store.top_killers(interaction.guild.id, limit=5)
        if not entries:
            await interaction.response.send_message("No deaths recorded yet.")
            return

        lines: list[str] = []
        for index, row in enumerate(entries, start=1):
            member = interaction.guild.get_member(row["user_id"])
            if row["user_id"] == 0:
                name = "Unknown"
            else:
                name = member.display_name if member else f"<@{row['user_id']}>"
            lines.append(f"{index}. {name} — {row['deaths']} deaths")

        embed = discord.Embed(title="Death Scoreboard")
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


class DevGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(name="dev", description="Owner-only testing commands")

    async def _ensure_owner(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message(
                "Dev commands only work in servers.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "Only the server owner can use dev commands.",
                ephemeral=True,
            )
            return False
        return True

    @app_commands.command(name="age-up", description="Advance the mascot's day index")
    @app_commands.describe(steps="Number of days to advance (default 1)")
    async def age_up(self, interaction: discord.Interaction, steps: int = 1) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        increment = max(1, steps)
        pet.born_at -= datetime.timedelta(days=increment)
        pet.maybe_evolve(pet.now())
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on checkpoint {pet.last_evolution_checkpoint}.",
            ephemeral=True,
        )

    @app_commands.command(name="age-down", description="Reduce the mascot's day index")
    @app_commands.describe(steps="Number of days to roll back (default 1)")
    async def age_down(self, interaction: discord.Interaction, steps: int = 1) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        decrement = max(1, steps)
        pet.born_at += datetime.timedelta(days=decrement)
        pet.last_evolution_checkpoint = 0
        pet.form = "egg"
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on checkpoint {pet.last_evolution_checkpoint}.",
            ephemeral=True,
        )

    @app_commands.command(name="hunger-up", description="Increase hunger")
    @app_commands.describe(amount="Points to add (default 10)")
    async def hunger_up(self, interaction: discord.Interaction, amount: int = 10) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        delta = max(1, amount)
        pet.hunger = min(100, pet.hunger + delta)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name}'s hunger is now {pet.hunger}/100.",
            ephemeral=True,
        )

    @app_commands.command(name="hunger-down", description="Decrease hunger")
    @app_commands.describe(amount="Points to remove (default 10)")
    async def hunger_down(self, interaction: discord.Interaction, amount: int = 10) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        delta = max(1, amount)
        pet.hunger = max(0, pet.hunger - delta)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name}'s hunger is now {pet.hunger}/100.",
            ephemeral=True,
        )

    @app_commands.command(name="happiness-up", description="Increase happiness")
    @app_commands.describe(amount="Points to add (default 10)")
    async def happiness_up(self, interaction: discord.Interaction, amount: int = 10) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        delta = max(1, amount)
        pet.happiness = min(100, pet.happiness + delta)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name}'s happiness is now {pet.happiness}/100.",
            ephemeral=True,
        )

    @app_commands.command(name="happiness-down", description="Decrease happiness")
    @app_commands.describe(amount="Points to remove (default 10)")
    async def happiness_down(self, interaction: discord.Interaction, amount: int = 10) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        delta = max(1, amount)
        pet.happiness = max(0, pet.happiness - delta)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name}'s happiness is now {pet.happiness}/100.",
            ephemeral=True,
        )


bot.tree.add_command(PetGroup())


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is not set.", file=sys.stderr)
        print(
            "PowerShell (session): $env:DISCORD_TOKEN=\"your-token-here\"",
            file=sys.stderr,
        )
        print(
            "PowerShell (persistent): setx DISCORD_TOKEN \"your-token-here\"",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print_intents(bot.intents)
    bot.run(token)


def print_intents(intents: discord.Intents) -> None:
    enabled = []
    if intents.message_content:
        enabled.append("message_content")
    if intents.guilds:
        enabled.append("guilds")
    if intents.guild_messages:
        enabled.append("guild_messages")
    print(f"Intents enabled: {', '.join(enabled) if enabled else 'none'}")


if __name__ == "__main__":
    main()
