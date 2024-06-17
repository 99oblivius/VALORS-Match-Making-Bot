from config import GUILD_ID

import nextcord
from nextcord.ext import commands

class BanView(nextcord.ui.View):
    def __init__(self, bot, done, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot = bot
        self.done = done

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(10):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_match_bans:{slot_id}")
            button.callback = instance.ban_callback
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot, match_id: int):
        instance = cls(bot, timeout=None)
        instance.stop()

        map_bans = await instance.bot.store.get_map_bans(match_id)
        for n, (m, count) in enumerate(map_bans):
            button = nextcord.ui.Button(
                label=f"{m}: {count}", 
                style=nextcord.ButtonStyle.blurple, 
                custom_id=f"mm_match_bans:{n}")
            instance.add_item(button)
        return instance

    async def ban_callback(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        # what phase
        # what button
        # already voted this one
        # already voted max times
        # vote this one
        ...