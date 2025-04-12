# VALORS Match Making Bot - Discord based match making automation and management service
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
#
# This file is part of VALORS Match Making Bot.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from datetime import datetime, timezone
import atexit
import redis
from utils.logger import Logger as log
log.set_level(log.DEBUG)

import nextcord
from nextcord.ext import commands

from config import *
from utils.database import Database
from utils.queuemanager import QueueManager
from utils.pavlov import RCONManager
from utils.command_ids import CommandCache
from utils.settings import SettingsCache

def exit_cleanup(a: list):
    for b in a:
        del b


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super(Bot, self).__init__(*args, **kwargs)

        self.store: Database              = Database()
        self.cache: redis.StrictRedis     = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        self.queue_manager: QueueManager  = QueueManager(self)
        self.rcon_manager: RCONManager    = RCONManager(self)
        self.command_cache: CommandCache  = CommandCache(self)
        self.settings_cache:SettingsCache = SettingsCache(self)

        self.match_stages = {}
    
    def __del__(self):
        del self.store


def main():
    activity = nextcord.Activity(type=nextcord.ActivityType.custom, name=f"WIP")
    intents = nextcord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot: commands.Bot = Bot(command_prefix=BOT_PREFIX, intents=intents, activity=activity)

    for folder in os.listdir("src/cogs"):
        if os.path.exists(os.path.join("src/cogs", folder, "cog.py")):
            log.info(f"LOADING- cogs.{folder}")
            bot.load_extension(f"cogs.{folder}.cog")
    
    @bot.event
    async def on_ready():
        log.info(f'==={bot.user.name} connected===\n\tat {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}UTC')

    atexit.register(exit_cleanup, a=[bot])
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
