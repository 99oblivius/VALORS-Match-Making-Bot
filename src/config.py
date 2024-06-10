import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

BOT_PREFIX = ">"

GUILD_ID = 1242575090433130496

VALOR_RED1 = 0xB20101
VALOR_RED2 = 0x8B0201
VALOR_RED3 = 0x150201
VALOR_YELLOW = 0xFFD700