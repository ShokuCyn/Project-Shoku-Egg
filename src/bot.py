from __future__ import annotations

import os
from dataclasses import asdict
import datetime

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

from .pet_store import PetStore


def build_sprite_urls() -> dict[str, str]:
    urls = {
        "egg": "https://placehold.co/256x256/gif?text=Egg",
        "gravestone": "https://placehold.co/256x256/gif?text=Gravestone",
    }
    for day in range(1, 7):
        for path in ("good", "bad"):
            text = f"Day {day} {path.title()}"
            urls[f"day{day}_{path}"] = (
                "https://placehold.co/256x256/gif?text="
                f"{text.replace(' ', '+')}"
            )
    return urls


SPRITE_URLS = build_sprite_urls()

POSITIVE_TRIGGERS = {
    "good egg",
    "best egg",
    "shoku",
    "so cute",
    "i love you",
    "great job",
}
NEGATIVE_TRIGGERS = {
    "bad egg",
    "stinky",
    "go away",
    "i hate you",
    "gross",
}


class PetBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
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
            previous_poop = pet.poop_count
            died = pet.apply_decay()
            self.store.save(pet)
            if pet.poop_count > previous_poop:
                await self._notify_poop(pet.guild_id, pet.poop_count - previous_poop)
            if died:
                self.store.record_death(pet.guild_id, pet.last_caretaker_id)
                await self._notify_death(pet.guild_id, pet.last_words)
        self.store.reset_daily_caretakers()

    @decay_loop.before_loop
    async def before_decay_loop(self) -> None:
        await self.wait_until_ready()

    async def _notify_poop(self, guild_id: int, count: int) -> None:
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
            await channel.send("💩" * max(1, count))

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
            await channel.send(f"☠️ {last_words}")


bot = PetBot()


@bot.event
async def on_ready() -> None:
    if bot.user:
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message) -> None:
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
            embed.add_field(name="Day", value="Egg", inline=True)
            embed.add_field(name="Path", value="N/A", inline=True)
            embed.add_field(name="Says", value="...zzz...", inline=False)
            sprite_url = SPRITE_URLS.get("gravestone")
            if sprite_url:
                embed.set_thumbnail(url=sprite_url)
            await interaction.response.send_message(embed=embed)
            return
        details = asdict(pet)
        embed = discord.Embed(title=f"{pet.name} the Mascot")
        embed.add_field(name="Day", value=pet.evolution_stage(), inline=True)
        embed.add_field(name="Path", value=pet.evolution_path(), inline=True)
        embed.add_field(name="Love Today", value=str(pet.love_today), inline=True)
        embed.add_field(name="Hunger (Fullness)", value=f"{pet.hunger}/100", inline=True)
        embed.add_field(name="Happiness", value=f"{pet.happiness}/100", inline=True)
        if pet.poop_count > 0:
            embed.add_field(
                name="Mess",
                value="💩" * min(5, pet.poop_count),
                inline=True,
            )
        else:
            embed.add_field(name="Mess", value="Clean", inline=True)
        embed.add_field(name="Says", value=pet.say_line(), inline=False)
        sprite_url = SPRITE_URLS.get(pet.sprite_key())
        if sprite_url:
            embed.set_thumbnail(url=sprite_url)
        embed.set_footer(text=f"Last updated: {details['updated_at']}")
        cutoff = pet.now() - datetime.timedelta(days=7)
        inactive = bot.store.inactive_caretakers(interaction.guild.id, cutoff=cutoff, limit=5)
        content = None
        if inactive:
            mentions = " ".join(f"<@{row['user_id']}>" for row in inactive)
            content = f"{mentions} {pet.name} misses you! Come check in."
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
        if pet.is_dead():
            await interaction.response.send_message(
                f"{pet.name} is resting under a pixel gravestone. Check back in an hour."
            )
            return
        if pet.poop_count == 0:
            await interaction.response.send_message(
                f"{pet.name}'s nest is already clean!"
            )
            return
        pet.clean()
        pet.last_caretaker_id = interaction.user.id
        bot.store.save(pet)
        await interaction.response.send_message(
            f"All clean! {pet.name} looks relieved."
        )

    @app_commands.command(name="rename", description="Rename the mascot")
    @app_commands.describe(name="The mascot's new name")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        pet = bot.store.get_or_create(interaction.guild.id)
        pet.name = name.strip()[:32] or pet.name
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
        pet.day_index = min(6, pet.day_index + increment)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on day {pet.day_index}.",
            ephemeral=True,
        )

    @app_commands.command(name="age-down", description="Reduce the mascot's day index")
    @app_commands.describe(steps="Number of days to roll back (default 1)")
    async def age_down(self, interaction: discord.Interaction, steps: int = 1) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        decrement = max(1, steps)
        pet.day_index = max(0, pet.day_index - decrement)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on day {pet.day_index}.",
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
        pet.day_index = min(6, pet.day_index + increment)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on day {pet.day_index}.",
            ephemeral=True,
        )

    @app_commands.command(name="age-down", description="Reduce the mascot's day index")
    @app_commands.describe(steps="Number of days to roll back (default 1)")
    async def age_down(self, interaction: discord.Interaction, steps: int = 1) -> None:
        if not await self._ensure_owner(interaction):
            return
        pet = bot.store.get_or_create(interaction.guild.id)
        decrement = max(1, steps)
        pet.day_index = max(0, pet.day_index - decrement)
        bot.store.save(pet)
        await interaction.response.send_message(
            f"{pet.name} is now on day {pet.day_index}.",
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
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(token)


if __name__ == "__main__":
    main()
