from datetime import datetime, timezone
import atexit
import asyncio
import logging as log
yellow = "\x1b[33;20m"
red = "\x1b[31;20m"
reset = "\x1b[0m"
# log.basicConfig(
#     level=log.INFO,
#     format=f'{red}[{reset}{yellow}%(asctime)s{reset}{red}]{reset} %(levelname)s - %(message)s',
#     datefmt='%Y-%m-%d %H:%M:%S',
#     handlers=[log.StreamHandler()]
# )

import nextcord
from nextcord.ext import commands

from config import *
from utils.database import Database
from utils.queuemanager import QueueManager

def exit_cleanup(a: list):
    for b in a:
        del b

class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super(Bot, self).__init__(*args, **kwargs)
        self.store = Database()
        self.queue_manager = QueueManager(self)


def main():
    activity = nextcord.Activity(type=nextcord.ActivityType.custom, name=f"WIP")
    intents = nextcord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot: commands.Bot = Bot(command_prefix=BOT_PREFIX, intents=intents, activity=activity)

    for folder in os.listdir("src/cogs"):
        if os.path.exists(os.path.join("src/cogs", folder, "cog.py")):
            print(f"LOADING- cogs.{folder}")
            bot.load_extension(f"cogs.{folder}.cog")
    
    @bot.event
    async def on_ready():
        log.critical(f'==={bot.user.name} connected===\n\tat {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}UTC')

    atexit.register(exit_cleanup, a=[bot])
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
