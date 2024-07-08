# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# VALORS Match Making Bot is a discord based match making automation and management service #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# 
# Copyright (C) 2024  Julian von Virag, <projects@oblivius.dev>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
MATCH_PLAYER_COUNT = 4
STARTING_MMR = 800
BASE_MMR_CHANGE = 32