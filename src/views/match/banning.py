from config import GUILD_ID
from typing import List

import nextcord
from nextcord.ext import commands

from utils.utils import shifted_window

from utils.models import Phase, MMBotUserBans


class BanView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot = bot

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

        ban_counts = await instance.bot.store.get_ban_counts(match_id)
        settings = await instance.bot.store.get_settings(GUILD_ID)
        bans = shifted_window(ban_counts, settings.maps_phase, settings.maps_range)
        for n, (m, count) in enumerate(bans):
            button = nextcord.ui.Button(
                label=f"{m}: {count}", 
                style=nextcord.ButtonStyle.blurple, 
                custom_id=f"mm_match_bans:{n}")
            instance.add_item(button)
        return instance

    async def ban_callback(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        # what phase
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        if not match.phase in (Phase.A_BAN, Phase.B_BAN):
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        # what button
        maps = await self.bot.store.get_maps(match.id)
        settings = await self.bot.store.get_settings(GUILD_ID)
        ban_maps = shifted_window(maps, settings.maps_phase, settings.maps_range)
        slot_id = int(button.custom_id.split(':')[-1])
        # already voted this one
        user_bans = await self.bot.store.get_user_map_bans(match.id, interaction.user.id)
        if ban_maps[slot_id] in user_bans:
            await self.bot.store.remove(MMBotUserBans, 
                match_id=match.id, 
                user_id=interaction.user.id, 
                map=ban_maps[slot_id])
            return await interaction.response.pong()
        # already voted max times
        if len(user_bans) > 1:
            return await interaction.response.send_message("You already banned 2 maps", ephemeral=True)

        # vote this one
        if not match.phase in (Phase.A_BAN, Phase.B_BAN): return
        await self.bot.store.upsert(MMBotUserBans, 
            user_id=interaction.user.id, 
            match_id=match.id, 
            map=ban_maps[slot_id], 
            phase=match.phase)

class PicksView(nextcord.ui.View):
    def __init__(self, bans: List[str]):
        super().__init__(timeout=0)

        for ban in bans:
            self.add_item(
                nextcord.ui.Button(
                    label=f"{ban}", 
                    style=nextcord.ButtonStyle.red,
                    disabled=True))