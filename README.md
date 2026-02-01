# Project Shoku Egg

A Discord bot prototype that lays the groundwork for a shared, server-wide digital pet (think early Digimon/Tamagotchi) that anyone in the server can interact with.

## Features (Groundwork)
- One pet per server (guild).
- Slash commands for viewing status, feeding, playing, and renaming.
- Persistent storage with SQLite.
- Simple time-based decay for hunger and happiness.
- Evolution stages based on days lived (Egg + Day 1-6), then the pet resets to a new egg.
- Daily feeding checks; if unfed, the pet rests under a pixel gravestone for an hour.
- Visual embed thumbnail per day and care path (good/bad), with GIF-friendly URLs.
- Scheduled background ticks for hunger/happiness decay.
- Branching evolution paths based on daily love totals.
- Daily caretaker resets with a top-caretaker leaderboard.
- Automatic nudges that mention inactive caretakers after 7 days.

## Setup
### Discord server setup
1. In the [Discord Developer Portal](https://discord.com/developers/applications), create a new application.
2. Open **Bot** → **Add Bot**, then copy the bot token.
3. Under **OAuth2** → **URL Generator**, select:
   - **Scopes**: `bot`, `applications.commands`
   - **Bot Permissions**: `Send Messages`, `Embed Links`, `Read Message History`
4. Use the generated invite URL to add the bot to your server.
5. (Optional) Create a test server and note its server ID. Use it as `GUILD_ID` for faster slash-command syncs during development.
6. (Optional) If you want chat message triggers (secret phrases), enable **Message Content Intent** in the Developer Portal and set `DISCORD_MESSAGE_CONTENT=1`.

### Local setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and add your bot token. If you captured a test server ID, add it as `GUILD_ID` too.
3. Run the bot:
   ```bash
   python -m src.bot
   ```

Once the bot is running, use `/pet` commands in a server channel. Slash commands can take a few minutes to appear globally when `GUILD_ID` is not set.

### Windows + PowerShell quickstart
1. Create a virtual environment, activate it, and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Set the token for the current session:
   ```powershell
   $env:DISCORD_TOKEN="your-bot-token-here"
   ```
   Optional: persist it for future sessions:
   ```powershell
   setx DISCORD_TOKEN "your-bot-token-here"
   ```
3. (Optional) Enable message-content triggers:
   ```powershell
   $env:DISCORD_MESSAGE_CONTENT="1"
   ```
   If you do this, enable **Message Content Intent** in the Discord Developer Portal.
4. Run the bot:
   ```powershell
   python -m src.bot
   ```

### Using a .env file (optional)
1. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`.
2. Run the bot normally; `python-dotenv` loads `.env` automatically:
   ```bash
   python -m src.bot
   ```

## Commands
- `/pet status` — show the current mascot state.
- `/pet feed` — reduce hunger and add a small amount of daily love.
- `/pet play` — increase happiness and add daily love.
- `/pet rename <name>` — rename the mascot.
- `/pet leaderboard` — show top caretakers for today.

## Roadmap Ideas
- Add weekly or seasonal evolution cycles beyond Day 6.
- Inventory items and cooldowns.
- Replace placeholder sprite thumbnails with custom art.
- Weekly or seasonal leaderboard resets with rewards.
