from datetime import datetime, timezone
import atexit

import pytz
import nextcord
from nextcord.ext import commands

from config import *

def exit_cleanup(a: list):
    for b in a:
        del b

class bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super(bot, self).__init__(*args, **kwargs)


def main():
    activity = nextcord.Activity(type=nextcord.ActivityType.custom, name=f"WIP")
    intents = nextcord.Intents.default()
    intents.guilds = True
    intents.message_content = True
    bot = bot(command_prefix=BOT_PREFIX, intents=intents, activity=activity)
    
    @bot.event
    async def on_ready():
        print(f'==={bot.user.name} connected\n\tat UTC{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}')

    atexit.register(exit_cleanup, a=[bot])
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
