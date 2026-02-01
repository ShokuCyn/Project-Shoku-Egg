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


class PetBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
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
            pet.apply_decay()
            self.store.save(pet)
        self.store.reset_daily_caretakers()

    @decay_loop.before_loop
    async def before_decay_loop(self) -> None:
        await self.wait_until_ready()


bot = PetBot()


@bot.event
async def on_ready() -> None:
    if bot.user:
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")


class PetGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(name="pet", description="Interact with the server mascot")

    @app_commands.command(name="status", description="Check the mascot's status")
    async def status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Pets only live in servers.")
            return

        pet = bot.store.get_or_create(interaction.guild.id)
        if pet.is_dead():
            embed = discord.Embed(title=f"{pet.name} is resting...")
            embed.description = "A pixel gravestone marks the spot. Check back in an hour."
            embed.add_field(name="Day", value="Egg", inline=True)
            embed.add_field(name="Path", value="N/A", inline=True)
            embed.add_field(name="Says", value="...zzz...", inline=False)
            embed.set_thumbnail(url=SPRITE_URLS["gravestone"])
            await interaction.response.send_message(embed=embed)
            return
        details = asdict(pet)
        embed = discord.Embed(title=f"{pet.name} the Mascot")
        embed.add_field(name="Day", value=pet.evolution_stage(), inline=True)
        embed.add_field(name="Path", value=pet.evolution_path(), inline=True)
        embed.add_field(name="Love Today", value=str(pet.love_today), inline=True)
        embed.add_field(name="Hunger", value=f"{pet.hunger}/100", inline=True)
        embed.add_field(name="Happiness", value=f"{pet.happiness}/100", inline=True)
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
        bot.store.save(pet)
        bot.store.record_care_action(interaction.guild.id, interaction.user.id, "play")
        await interaction.response.send_message(
            f"{pet.name} plays along! Happiness is now {pet.happiness}/100."
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


bot.tree.add_command(PetGroup())


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(token)


if __name__ == "__main__":
    main()
