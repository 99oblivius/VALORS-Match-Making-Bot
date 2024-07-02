import os
from dotenv import load_dotenv
load_dotenv()

SERVER_DM_MAP = "UGC2814848"

DATABASE_URL = os.getenv("DATABASE_URL", "")

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

BOT_PREFIX = ">"

GUILD_ID = 1217224187454685295

HOME_THEME = 0x0000a0
AWAY_THEME = 0x00a000

VALORS_THEME1 = 0xB20101
VALORS_THEME1_1 = 0x8B0201
VALORS_THEME1_2 = 0x150201
VALORS_THEME2 = 0xFFD700

LFG_PING_DELAY = 30*60
MATCH_PLAYER_COUNT = 10
STARTING_MMR = 800
BASE_MMR_CHANGE = 32