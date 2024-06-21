from functools import partial
from typing import List

import nextcord
from nextcord.ext import commands

from utils.utils import shifted_window
from utils.models import Phase, MMBotMatches, MMBotUserMapPicks


class MapPickView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot: commands.Bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(10):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_match_picks:{slot_id}")
            button.callback = partial(instance.pick_callback, button)
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot, guild_id: int, match: MMBotMatches):
        instance = cls(bot, timeout=None)
        instance.stop()

        banned_maps = await instance.bot.store.get_bans(match.id)
        maps = await instance.bot.store.get_map_vote_count(guild_id, match.id)
        picks = shifted_window(maps, match.maps_phase, match.maps_range)
        for n, (m, count) in enumerate(picks):
            if m in banned_maps:
                continue
            button = nextcord.ui.Button(
                label=f"{m}: {count}", 
                style=nextcord.ButtonStyle.green, 
                custom_id=f"mm_match_picks:{n}")
            button.callback = partial(instance.pick_callback, button)
            instance.add_item(button)
        return instance

    async def pick_callback(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        # what phase
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        if match.phase != Phase.A_PICK:
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        # what button
        maps = await self.bot.store.get_maps(interaction.guild.id)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        pick_maps = shifted_window([m.map for m in maps], settings.mm_maps_phase, settings.mm_maps_range)
        slot_id = int(button.custom_id.split(':')[-1])
        
        user_picks = await self.bot.store.get_user_map_pick(match.id, interaction.user.id)
        if pick_maps[slot_id] in user_picks:
            # already voted this one
            await self.bot.store.remove(MMBotUserMapPicks, 
                match_id=match.id, 
                user_id=interaction.user.id, 
                map=pick_maps[slot_id])
            await interaction.response.pong()
        else:
            # vote this one
            await self.bot.store.remove(MMBotUserMapPicks, 
                match_id=match.id, 
                user_id=interaction.user.id)
            await self.bot.store.upsert(MMBotUserMapPicks, 
                guild_id=interaction.guild.id, 
                user_id=interaction.user.id, 
                match_id=match.id, 
                map=pick_maps[slot_id])
        view = await self.create_showable(self.bot, interaction.guild.id, match)
        await interaction.edit(view=view)

class ChosenMapView(nextcord.ui.View):
    def __init__(self, pick: str):
        super().__init__(timeout=0)

        self.add_item(
            nextcord.ui.Button(
                label=f"{pick}", 
                style=nextcord.ButtonStyle.green,
                disabled=True))
