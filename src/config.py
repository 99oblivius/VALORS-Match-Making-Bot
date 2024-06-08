import os
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
BOT_PREFIX = ">"


GUILD_ID = 1242575090433130496
