import os
from dotenv import load_dotenv
load_dotenv()

POSTGRESQL_URL = os.getenv("POSTGRESQL_URL")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")


BOT_PREFIX = ">"

GUILD_ID = 1242575090433130496
